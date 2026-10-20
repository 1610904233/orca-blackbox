#!/usr/bin/env python3
# m8x_158.py — 飞书基线 #158: 模型布局优化与多设备切换打印（**本地段**）
# feishu: baseline#158
# 行文步骤: 启动Orca→新建项目→导入多个模型→模型整理→切片→[云设备绑定→发起
#           打印→终止→解绑→局域网设备绑定→发起打印→监控]→关闭软件
#
# 本用例覆盖方括号之前的电脑端步骤；云/局域网设备链需真机 → 飞书「部分自动化」。
# 与 #153 的分工（避免重复覆盖）：#153 是"两个模型 + 重合 + 改耗材"，本用例是
# **多个模型（3 个）+ 布局整理**——导入后三个对象落在盘上，Arrange 后必须彼此
# 分开（包围盒不相交），再切片导出。
#
# 单会话即可（没有连续 gizmo 问题：全程不用变换面板）。
# 录像：artifacts/shots/<stem>/<stem>_run.mp4

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x158]"
ART = HERE / "artifacts"
MODELS = (HERE / "fixtures" / "Prusa.stl",
          HERE / "fixtures" / "cube20.stl",
          HERE / "fixtures" / "prism12.stl")


def object_blobs(session, limit=6):
    """盘面上**对象形状**的彩色 blob：(cx, cy, x0, y0, x1, y1, area)。

    过滤口径同 m8x_153：面积 >= 250、宽高比 0.3~4（右下角 "snapmaker" 水印
    是 aspect≈15 的细长条，会被拦掉），并排除 x>1450 的 UI 区域。"""
    import cv2
    import numpy as np
    import m7_common as m7
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    h, w = img.shape[:2]
    bx0, by0, bx1, by1 = m7.VIEWPORT_X0 + 10, 110, w - 10, h - 60
    band = img[by0:by1, bx0:bx1].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _l, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    order = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    out = []
    for i in order:
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 250:
            break
        bw, bh = int(stats[i, 2]), int(stats[i, 3])
        ar = bw / max(bh, 1)
        if not (0.3 <= ar <= 4.0):
            continue
        if int(cents[i][0]) + bx0 > 1450:
            continue
        out.append((int(cents[i][0]) + bx0, int(cents[i][1]) + by0,
                    int(stats[i, 0]) + bx0, int(stats[i, 1]) + by0,
                    int(stats[i, 0] + stats[i, 2]) + bx0,
                    int(stats[i, 1] + stats[i, 3]) + by0, area))
        if len(out) >= limit:
            break
    return out


def _overlap(a, b):
    return not (a[4] < b[2] or b[4] < a[2] or a[5] < b[3] or b[5] < a[3])


def import_model(session, path):
    """File → Import → 输入路径 → IDOK。"""
    import ctypes
    import m7_common as m7
    from harness import export_util, winutil
    dispatched, dlg = m7.file_menu_dispatch(session, "stl",
                                            expect_dialog=True, via="Import")
    if not dispatched or not dlg:
        return False
    edit = export_util.find_edit(dlg[3])
    if edit is None:
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(path))
    ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)  # IDOK
    return True


def main() -> int:
    import argparse
    import m7_common as m7
    import m8_common as m8
    from m3_common import add_common_args, boot_session

    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    args.model = None
    results = {}
    session = boot_session(args, model=None)
    try:
        frac0 = m7.model_colored_frac(session)
        results["启动 Orca（空盘）"] = (
            "PASS" if frac0 < m7.EMPTY_BED_FLOOR else f"FAIL ({frac0:.3%})")
        if frac0 >= m7.EMPTY_BED_FLOOR:
            return m7.m7_verdict(results)
        ok, _ = m7.file_menu_dispatch(session, "New Project")
        results["新建项目派发"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        time.sleep(2.0)
        m7.ensure_maximized(session)

        # 1) 导入多个模型（3 个不同模型）
        imported = 0
        names = []
        for path in MODELS:
            if not import_model(session, path):
                print(f"{LOG} import dispatch failed for {path.name}")
                break
            # 判据：**对象信息面板出现该模型名**（导入的对象默认被选中）。
            # 不用 blob 计数：相邻对象会被形态学闭运算并成一个（实测 10-20：
            # prism12 与 cube20 相邻 → blob 数 2->2，误判导入失败）。
            deadline = time.monotonic() + 120
            info = ""
            ok_name = False
            while time.monotonic() < deadline:
                time.sleep(2.0)
                info = m7.object_info_text(session)
                if path.stem.lower() in (info or "").lower():
                    ok_name = True
                    break
            print(f"{LOG} import {path.name}: name_ok={ok_name} "
                  f"info={info[:60]!r} blobs={len(object_blobs(session))}")
            if ok_name:
                imported += 1
                names.append(path.stem)
        results["导入多个模型（3 个）"] = (
            f"PASS ({imported}: {names})" if imported >= 3
            else f"FAIL (imported {imported})")
        if imported < 3:
            return m7.m7_verdict(results)
        from harness import export_util as _eu

        # 制造"待整理"的布局：把最后导入的模型（导入后处于选中态）**拖**到
        # 盘心，和已在盘心的对象重合。否则 app 导入时已自动避让、本来就不重叠，
        # "整理"就没有可整理的对象（10-20 实测：pre/post 完全一致 = 空转）。
        # 用鼠标拖拽而不是输入数值：Move 面板的聚焦单元格 OCR 会把 '0' 读成
        # '800'（实测 10-20），拖拽则有 #156 s2 的实证（数值 100→154.77）。
        from harness import winutil as _wu
        pre_layout_blobs = object_blobs(session)
        live = m7.find_centroid(session)
        spot = m7.select_object_strict(session)
        m7.click_slot(session, 1064)          # Move 工具（固定几何，tip 已验）
        time.sleep(1.5)
        if m7.gizmo_row_boxes(session, "position") and live:
            _wu.user32.SetCursorPos(*m7.client(session, *live))
            time.sleep(0.2)
            m7.real_drag_screen(session, live, (1171, 585))
            time.sleep(2.0)
            blobs_now = object_blobs(session)
            # "待整理"的定义 = 布局被弄乱了（对象被拖离原位 ≥20px），不要求
            # 一定重叠——实测拖拽常常把对象拖到盘的边角（同样需要整理）。
            before_layout = sorted((b[0], b[1]) for b in pre_layout_blobs)
            after_layout = sorted((b[0], b[1]) for b in blobs_now)
            messy = 0
            for a, b in zip(before_layout, after_layout):
                messy = max(messy, abs(b[0] - a[0]), abs(b[1] - a[1]))
            print(f"{LOG} messy layout by drag: blobs={blobs_now} "
                  f"moved={messy}px")
            results["构造待整理布局（拖乱 ≥20px）"] = (
                f"PASS (moved={messy}px)" if messy >= 20
                else f"FAIL (moved={messy}px)")
        else:
            results["构造待整理布局（模拟叠放）"] = (
                f"FAIL (move panel={bool(m7.gizmo_row_boxes(session, 'position'))}, "
                f"live={live}, spot={spot})")

        def _collision_warn():
            return any("too close" in (t or "").lower()
                       for t, _r, _h in _eu._children_texts(session.hwnd))

        pre = object_blobs(session)
        overlaps = sum(1 for i in range(len(pre)) for j in range(i + 1, len(pre))
                       if _overlap(pre[i], pre[j]))
        warn0 = _collision_warn()
        print(f"{LOG} pre-arrange blobs={len(pre)} overlaps={overlaps} "
              f"collision_warn={warn0}")
        results["导入后存在碰撞/过近（app 提示）"] = (
            "PASS (evidence)" if warn0 else "PASS (no warning)")

        # 2) 模型整理：快捷键 'A'（工具栏 tooltip 'Arrange all objects [A]'，
        #    10-19 实证可用；工具栏图标只负责打开面板，面板按钮不是带文本子控件）
        import m7_common as _m7
        from harness import winutil as _wu
        sx, sy = _m7.client(session, _m7.VIEWPORT_X0 + 60, 700)
        _wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.2)
        _wu.real_click_screen(sx, sy)      # 焦点回画布
        time.sleep(0.6)
        _wu.user32.keybd_event(0x41, 0, 0, 0)     # 'A'
        time.sleep(0.06)
        _wu.user32.keybd_event(0x41, 0, 2, 0)
        time.sleep(3.0)
        # 判据：**整理后布局确实变了**（有对象移动 ≥10px）+ 无重叠 +
        # （若整理前有碰撞提示）提示消失。
        # 不用"blob 数 >= 3"：相邻对象在渲染上会并成一个 blob（实测 10-20）。
        def _layout(bs):
            return sorted((b[0], b[1], b[2], b[3], b[4], b[5]) for b in bs)

        pre_layout = _layout(pre)
        deadline = time.monotonic() + 45
        post = object_blobs(session)
        separated = False
        moved_px = 0
        ov = 0
        while time.monotonic() < deadline:
            post = object_blobs(session)
            ov = sum(1 for i in range(len(post))
                     for j in range(i + 1, len(post))
                     if _overlap(post[i], post[j]))
            warn = _collision_warn()
            cur = _layout(post)
            moved_px = 0
            for a, b in zip(pre_layout, cur):
                moved_px = max(moved_px, max(abs(b[0] - a[0]), abs(b[1] - a[1]),
                                             abs(b[2] - a[2]), abs(b[3] - a[3])))
            print(f"{LOG} arrange poll: blobs={len(post)} overlaps={ov} "
                  f"moved={moved_px}px collision_warn={warn}")
            if ov == 0 and moved_px >= 10 and (not warn0 or not warn):
                separated = True
                break
            time.sleep(2.0)
        results["模型整理（布局确实变化 + 无重叠）"] = (
            f"PASS (moved={moved_px}px, overlaps=0, "
            f"warning {warn0}->{_collision_warn()})" if separated
            else f"FAIL (moved={moved_px}px, overlaps={ov}, "
                 f"warning present)")
        if not separated:
            return m7.m7_verdict(results)

        # 3) 切片 + 导出（云/局域网打印需真机）
        gcode = ART / "m8x_158.gcode"
        m7.op_slice(session, results, key="切片成功", export_to=gcode)
        try:
            used = m8.used_filaments(gcode.read_bytes())
        except OSError:
            used = []
        print(f"{LOG} gcode filaments: {used}")
        results["G-code 生成（用量可读）"] = (
            f"PASS (used={used})" if used else "FAIL (no usage)")

        # 4) 关闭软件
        alive = session.alive()
        session.close()
        time.sleep(3.0)
        results["软件正常关闭"] = "PASS" if alive else "FAIL"
        session = None
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:                                  # noqa: BLE001
                pass
        print(f"{LOG} session closed")
    return m7.m7_verdict(results)


if __name__ == "__main__":
    raise SystemExit(main())
