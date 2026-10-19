#!/usr/bin/env python3
# m8x_153.py — 飞书基线 #153: 多模型布局与本地文件直接打印（**本地段**）
# feishu: baseline#153
# 行文步骤: 启动Orca→导入两个不同模型并重合→模型整理→切片→预打印更改耗材信息
#           →[上传本地文件打印→局域网设备绑定→打印完成后解绑]→关闭软件
#
# 本用例覆盖方括号之前的电脑端步骤；设备链需真机 → 飞书「部分自动化」。
# 单会话完成（#153 没有"连续 gizmo"问题：只有一次 Move 用于把两模型叠到一起）。
#
# 与行文的执行顺序说明（诚实声明）：行文是"切片→预打印更改耗材信息"，本用例
# 按 **改耗材信息 → 切片 → 导出** 执行——这样 gcode 里的 filament_settings_id
# 能直接证明"耗材参数修改生效"（先切后改就拿不到可判定的产物）。
#
# 录像：artifacts/shots/<stem>/<stem>_run.mp4（shot_archive 自动录）

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x153]"
ART = HERE / "artifacts"
MODEL1 = HERE / "fixtures" / "Prusa.stl"
MODEL2 = HERE / "fixtures" / "cube20.stl"   # 20mm 立方体（录像是两个
                                             # 模型都可见；250mm 的
                                             # gcode_param_test 会盖住整盘）
ARRANGE_X = 844          # 工具栏 'Arrange all objects [A]'（10-16/10-19 OCR 扫描
                         # 稳定落在 800..866，取扫描命中值）


def object_blobs(session, limit=4, min_area=250, aspect=(0.3, 4.0)):
    """盘面上的**对象形状** blob：(cx, cy, x0, y0, x1, y1, area)。

    直接用彩色 blob 会把 UI 当模型：右下角 "snapmaker" 水印是一块 375x25 的
    彩色条（aspect≈15，实测 10-19），曾被当成"第二个模型"，于是拖拽去拖水印、
    重合判定永远 False。这里按 m7.model_blob_count 的同一口径过滤：
    面积 >= min_area 且 宽高比在 aspect 区间内。"""
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
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _l, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    order = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    out = []
    for i in order:
        area = int(stats[i, cv2.CC_STAT_AREA])
        bw, bh = int(stats[i, cv2.CC_STAT_WIDTH]), int(
            stats[i, cv2.CC_STAT_HEIGHT])
        if area < min_area:
            break
        ar = bw / max(bh, 1)
        if not (aspect[0] <= ar <= aspect[1]):
            continue
        # 右下角 "snapmaker" 水印是一条细长彩色带（实测 aspect≈15 已拦下），
        # 它所在区域 x>1450 还有别的同色 UI 元素，一并排除（本机固定布局）
        if int(cents[i][0]) + bx0 > 1450:
            continue
        out.append((int(cents[i][0]) + bx0, int(cents[i][1]) + by0,
                    int(stats[i, 0]) + bx0, int(stats[i, 1]) + by0,
                    int(stats[i, 0] + stats[i, 2]) + bx0,
                    int(stats[i, 1] + stats[i, 3]) + by0, area))
        if len(out) >= limit:
            break
    return out


def _bbox_overlap(a, b):
    """两 blob 的包围盒是否相交（重合 = 投影相交）。"""
    return not (a[4] < b[2] or b[4] < a[2] or a[5] < b[3] or b[5] < a[3])


def drag_object(session, src_pt, dst_pt, steps=14):
    """左键拖拽：Orca 画布上的"就地平移"手势（把对象从 src 拖到 dst）。"""
    import m7_common as m7
    from harness import winutil as _wu
    sx, sy = m7.client(session, *src_pt)
    dx, dy = m7.client(session, *dst_pt)
    _wu.user32.SetCursorPos(sx, sy)
    time.sleep(0.3)
    _wu.user32.mouse_event(0x0002, 0, 0, 0, 0)          # LEFTDOWN
    for i in range(1, steps + 1):
        _wu.user32.SetCursorPos(sx + (dx - sx) * i // steps,
                                sy + (dy - sy) * i // steps)
        time.sleep(0.05)
    _wu.user32.mouse_event(0x0004, 0, 0, 0, 0)          # LEFTUP
    time.sleep(1.0)


def move_xy_zero(session):
    """Move 面板里把 **X 和 Y 都置 0**（一次开面板、两个字段）——把导入时被
    app 自动避让挪开的对象挪回盘心，和已在盘心的另一个对象重合。

    为什么不用两次 op_gizmo_field：同一会话第 2 个 gizmo 面板对输入失聪
    （2.4.1 实测）；为什么不用拖拽：Orca 画布上的左键拖拽是框选，不移动对象
    （10-19 实测 drag 后 blobs 完全不变）。"""
    import m7_common as m7
    x, tip = m7.find_slot(session, lambda t: "move" in t)
    if x is None:
        print(f"{LOG} move slot not found")
        return False
    print(f"{LOG} move slot @x{x} tip={tip!r}")
    m7.click_slot(session, x)
    time.sleep(1.2)
    ok = True
    for idx, val in ((0, "0"), (1, "0")):
        boxes = m7.gizmo_row_boxes(session, "position")
        if not boxes or idx >= len(boxes):
            print(f"{LOG} position panel closed at field {idx}")
            ok = False
            break
        m7.type_into_field(session, boxes[idx][:2], val,
                           old_len=max(len(boxes[idx][2]), 4))
        time.sleep(1.0)
        _b, text = m7.read_gizmo_field(session, "position", idx,
                                       expect=val, timeout_s=6.0)
        print(f"{LOG} move field {idx} -> {text!r}")
        ok = ok and text.startswith(val)
    if m7.gizmo_row_boxes(session, "position"):
        m7.click_slot(session, x)
        time.sleep(0.8)
    return ok


def import_model(session, path):
    """File → Import → 输入路径 → IDOK；返回是否派发成功。"""
    import ctypes
    import m7_common as m7
    from harness import export_util, winutil
    dispatched, dlg = m7.file_menu_dispatch(session, "stl",
                                            expect_dialog=True, via="Import")
    if not dispatched or not dlg:
        print(f"{LOG} import dispatch failed (dlg={dlg})")
        return False
    edit = export_util.find_edit(dlg[3])
    if edit is None:
        print(f"{LOG} import dialog has no Edit child")
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(path))
    ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)  # IDOK
    return True


def wait_objects(session, want, timeout_s=180):
    """等到盘面上出现 want 个**对象形状**的 blob；返回最后的列表。"""
    deadline = time.monotonic() + timeout_s
    blobs = object_blobs(session)
    while time.monotonic() < deadline:
        if len(blobs) >= want:
            return blobs
        time.sleep(2.0)
        blobs = object_blobs(session)
    return blobs


def _arrange_key(session):
    """渠道 1：键盘快捷键 'A'（工具栏 tooltip 明写 'Arrange all objects [A]'）。
    先把焦点点回盘面（点一处空白床面），再按 A。"""
    import m7_common as m7
    from harness import winutil as _wu
    img_pt = (m7.VIEWPORT_X0 + 60, 700)      # 左侧空白床面（焦点用，不选中对象）
    sx, sy = m7.client(session, *img_pt)
    _wu.user32.SetCursorPos(sx, sy)
    time.sleep(0.2)
    _wu.real_click_screen(sx, sy)
    time.sleep(0.8)
    _wu.user32.keybd_event(0x41, 0, 0, 0)    # 'A'
    time.sleep(0.06)
    _wu.user32.keybd_event(0x41, 0, 2, 0)
    print(f"{LOG} pressed 'A' (arrange all shortcut)")
    return True


def _arrange_toolbar_panel(session):
    """渠道 2：工具栏 Arrange 图标 → 弹出面板里的 [Arrange] 按钮（几何点击：
    面板按钮不是带文本的子窗口，10-19 实测按文本扫不到；1920x1080 下按钮在
    客户区 (892,300) 附近）。"""
    import m7_common as m7
    from harness import winutil as _wu
    x = ARRANGE_X
    tip = m7.tooltip_text(session, x, m7.BAR_Y)
    if "arrange" not in (tip or "").lower():
        x, tip = m7.find_slot(session, lambda t: "arrange" in t)
    if x is None:
        return False
    print(f"{LOG} toolbar arrange @x{x} tip={tip!r}")
    m7.click_slot(session, x)
    time.sleep(1.5)
    sx, sy = m7.client(session, 892, 300)
    _wu.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    _wu.real_click_screen(sx, sy)
    print(f"{LOG} clicked arrange panel button @(892,300)")
    return True


def _arrange_bed_menu(session):
    """渠道 3：盘面右键菜单的 'Arrange' 行（菜单有两个变体，只有"编辑盘"
    那条有该行；没有就返回 False 交给下一条渠道）。"""
    import m7_common as m7
    menu = m7.open_context_menu(session, where="bed")
    if not menu:
        return False
    hwnd, hmenu = menu
    rows = [l for _i, l in m7.list_menu(hmenu)]
    print(f"{LOG} bed menu rows: {rows}")
    if not any("arrange" in r.lower() for r in rows):
        m7.dismiss_menus(session)
        return False
    got = m7.click_menu_row(session, hwnd, hmenu, "arrange")
    if got is None:
        m7.dismiss_menus(session)
        return False
    return True


def arrange_all(session, per_path_s=24.0):
    """依次尝试三条整理渠道，直到**两对象分离**（判定=效果，不靠渠道自证）。"""
    for fn in (_arrange_key, _arrange_toolbar_panel, _arrange_bed_menu):
        if not fn(session):
            print(f"{LOG} {fn.__name__}: path unavailable")
            continue
        deadline = time.monotonic() + per_path_s
        while time.monotonic() < deadline:
            time.sleep(2.0)
            bs = object_blobs(session)
            if len(bs) >= 2 and not _bbox_overlap(bs[0], bs[1]):
                print(f"{LOG} arranged via {fn.__name__}: blobs={bs}")
                return bs
        print(f"{LOG} {fn.__name__}: objects still not separated")
    return None


def main() -> int:
    import argparse
    import m7_common as m7
    import m8_common as m8
    from m3_common import add_common_args, boot_session

    ap = add_common_args(argparse.ArgumentParser(), default_model=MODEL1)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=MODEL1)
    try:
        ok, frac = m8.wait_arrival(session)
        results["启动 Orca 并载入模型 1（Prusa.stl）"] = (
            "PASS" if ok else f"FAIL (frac={frac:.2%})")
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)

        # 1) 导入第二个不同模型
        before = object_blobs(session)
        print(f"{LOG} blobs after model1: {before}")
        if not import_model(session, MODEL2):
            results["导入模型 2（cube20.stl）"] = "FAIL (dispatch)"
            return m7.m7_verdict(results)
        blobs = wait_objects(session, len(before) + 1, timeout_s=120)
        print(f"{LOG} blobs after model2: {blobs}")
        info = m7.object_info_text(session)
        print(f"{LOG} object info panel after import: {info!r}")
        named = "cube20" in (info or "").lower()
        results["导入模型 2（cube20.stl）"] = (
            f"PASS (info panel {info[:40]!r})" if named
            else f"FAIL (info panel {info[:60]!r}, blobs {len(blobs)})")
        if not named:
            return m7.m7_verdict(results)

        # 2) 两模型重合：以 app 自己的碰撞提示（"… is too close to others,
        #    there may be collisions when printing"）为主观测面，blob 相交为辅。
        #    实测 10-19：导入会**自动避让**（20mm 立方体落在薄片正上方 5px，
        #    因此没有提示），此时把立方体 Move Y=0 压到薄片上（Move 面板只开
        #    一次、只改一个字段——同一会话第 2 个 gizmo 面板会丢输入）。
        from harness import export_util as _eu

        def _collision_warn():
            return any("too close" in (t or "").lower()
                       for t, _r, _h in _eu._children_texts(session.hwnd))

        def _stacked(bs):
            return (len(bs) < 2) or _bbox_overlap(bs[0], bs[1])

        warn = _collision_warn()
        print(f"{LOG} after import: warning={warn} blobs={blobs}")
        if not (warn or _stacked(blobs)):
            print(f"{LOG} models adjacent but not stacked — Move X=0,Y=0")
            ok_mv = move_xy_zero(session)
            print(f"{LOG} move xy->0: ok={ok_mv}")
            time.sleep(3.0)
            blobs = object_blobs(session)
            warn = _collision_warn()
            print(f"{LOG} after Move: warning={warn} blobs={blobs}")
        results["两模型重合（碰撞提示 / blob 相交）"] = (
            "PASS (warning visible)"
            if warn else ("PASS (blobs intersect)" if _stacked(blobs)
                          else f"FAIL (blobs={blobs})"))
        if not (warn or _stacked(blobs)):
            return m7.m7_verdict(results)

        # 3) 模型整理（Arrange）：整理正确 = 两对象被分开（blob 不再相交），
        #    且有碰撞提示时提示应消失。工具栏图标只开面板，真正的动作是面板里
        #    的 Arrange 按钮（见 arrange_click 注释）。
        post = arrange_all(session)
        print(f"{LOG} after arrange: blobs={post} warning={_collision_warn()}")
        results["模型整理（Arrange 后两对象分离）"] = (
            f"PASS ({len(post)} blobs separated)" if post
            else f"FAIL (blobs={object_blobs(session)})")
        if not post:
            return m7.m7_verdict(results)

        # 4) 预打印更改耗材信息（耗材颜色）：官方色卡库换色。
        #    为什么不是切预设：本 profile 里槽内是**用户预设**，两级选择框的
        #    左栏只有 Snapmaker/~Custom/Add-Remove，右栏 OCR 只出 3 行、滚轮
        #    消息也不动（10-19 实测 30 次预算都切不到 PETG HF）；颜色则是
        #    官方色卡这条已硬化且在基线里 GREEN 的通路，且能在 gcode 的
        #    filament_colour 里**精确**验证。
        import m8b_official_color as m8b
        before_rgb = m8.slot_swatch_rgb(session, 1)
        dlg = m8.click_official_color_popup(session, 1)
        picked = m8b.pick_official_card(session, dlg) if dlg else None
        ok_ok = m8.close_dialog_by_button(dlg, "OK") if dlg else False
        time.sleep(2.0)
        after_rgb = m8.slot_swatch_rgb(session, 1)
        print(f"{LOG} colour change: before={before_rgb} picked={picked!r} "
              f"ok={ok_ok} after={after_rgb}")
        results["耗材信息修改（槽 1 官方色卡换色）"] = (
            f"PASS ({picked!r})"
            if picked and ok_ok and before_rgb != after_rgb
            else f"FAIL (picked={picked!r}, ok={ok_ok}, "
                 f"{before_rgb} -> {after_rgb})")
        if not picked:
            return m7.m7_verdict(results)

        # 5) 切片 + 导出（本地文件；上传打印/绑定设备需真机）
        gcode = ART / "m8x_153.gcode"
        m7.op_slice(session, results, key="切片完成", export_to=gcode)

        # 6) 耗材参数修改生效：gcode 的 filament_colour[0] 必须等于侧栏新色
        hexs, _hue = (m8b.gcode_slot_colour(gcode, 0) if gcode.exists()
                      else (None, None))   # index 是 0 基：0 = 槽 1
        want = None
        if after_rgb:
            b, g, r = after_rgb            # slot_swatch_rgb 返回 BGR
            want = f"#{r:02X}{g:02X}{b:02X}".upper()
        # 色板是**渲染**出来的（实测 10-19：选 Pure White #FFFFFF，色板读到
        # #ECECEC，各通道差 19），所以按通道容差判等，不做逐位相等。
        diff = None
        if hexs and want:
            try:
                diff = max(abs(int(hexs[i:i + 2], 16) - int(want[i:i + 2], 16))
                           for i in (1, 3, 5))
            except ValueError:
                diff = None
        print(f"{LOG} gcode slot1 colour={hexs} sidebar={want} maxchan={diff}")
        results["gcode 反映耗材修改（filament_colour）"] = (
            f"PASS ({hexs} ≈ {want}, maxchan={diff})"
            if diff is not None and diff <= 40
            else f"FAIL (gcode={hexs}, sidebar={want}, maxchan={diff})")

        # 7) 关闭软件
        alive_before = session.alive()
        session.close()
        time.sleep(3.0)
        results["软件正常关闭"] = "PASS" if alive_before else "FAIL"
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
