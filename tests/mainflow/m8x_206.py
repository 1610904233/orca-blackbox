#!/usr/bin/env python3
# m8x_206.py — 飞书基线 #206: 【菜单存在性】准备页「校准」菜单完整展示
# feishu: baseline#206
# 行文: 准备页点顶部「校准」→ 一级条目齐全 → 三个子菜单内容齐全 → 无灰置
#
# 入口 = BBLTopbar 自绘「Calibration」工具（File 右侧；probe_242_calibmenu2
# 标定 offset 250，popup rect=(243,29,443,233)）。菜单是原生 HMENU：
# MN_GETHMENU 取根，GetSubMenu 直读子菜单；随后再按飞书步骤 3 实际悬停
# 流量/转弯/输入整形三条父条目，让子菜单在录屏里可见（2.4.2 不 hover 读与
# 视觉展开两条证据都留）。
# 判定 = 「包含」口径：飞书列出的条目/子菜单行均需存在；GetMenuState 的
# MF_GRAYED/MF_DISABLED 必须全为 0（等价于「各条目可点击、无灰置」）。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x206]"

# 飞书 #206 一级条目（中文口径 -> 英文 UI 关键字）
TOP_REQUIRED = [
    ("温度", "temperature"),
    ("流量", "flow rate"),
    ("压力提前", "pressure advance"),
    ("回抽测试", "retraction test"),
    ("最大体积流量", "max flowrate"),
    ("转弯", "cornering"),
    ("输入整形", "input shaping"),
    ("VFA", "vfa"),
]
# 子菜单行（「粗调/细调」= UI 的 Pass 1 / Pass 2）
SUB_REQUIRED = [
    ("流量", "flow rate", [
        ("粗调", "pass 1"),
        ("细调", "pass 2"),
        ("YOLO（推荐）", "yolo (recommended"),
        ("YOLO（完美主义者版本）", "yolo (perfectionist"),
    ]),
    ("转弯", "cornering", [("节点偏差", "junction deviation")]),
    ("输入整形", "input shaping", [
        ("输入整形频率", "input shaping frequency"),
        ("输入整形阻尼/阻尼系数", "damping"),
    ]),
]
MF_GRAYED = 0x00000001
MF_DISABLED = 0x00000002
MF_SEPARATOR = 0x00000800


def main() -> int:
    import argparse
    import m7_common as m7
    from m3_common import add_common_args, boot_session
    from harness import topbar_util, winutil

    ap = add_common_args(argparse.ArgumentParser())  # 空床：不载模型
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        menu = topbar_util.open_calibration_menu(session)
        results["「校准」菜单可展开"] = "PASS" if menu else "FAIL (no popup)"
        if not menu:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)
        _rect, _mhwnd, hm = menu

        rows = [(i, lbl, st) for i, lbl, st in topbar_util.menu_items(hm)
                if lbl.strip() and not (st & MF_SEPARATOR)]
        labels = [lbl.lower() for _i, lbl, _st in rows]
        print(f"{LOG} top rows={[lbl for _i, lbl, _st in rows]}")
        missing = [cn for cn, needle in TOP_REQUIRED
                   if not any(needle in lbl for lbl in labels)]
        results["一级条目齐全（8 项）"] = (
            "PASS" if not missing else f"FAIL (missing={missing})")

        for cn, needle, wanted in SUB_REQUIRED:
            idx = topbar_util.find_item(hm, needle)
            sub = None
            if idx is not None:
                _oid, sub = topbar_util.item_info(hm, idx)
            if not sub:
                results[f"{cn}子菜单"] = "FAIL (no submenu)"
                continue
            sub_labels = [lbl.lower() for _i, lbl, _st
                          in topbar_util.menu_items(sub) if lbl.strip()]
            print(f"{LOG} {cn} submenu rows={sub_labels}")
            miss = [wcn for wcn, wneedle in wanted
                    if not any(wneedle in lb for lb in sub_labels)]
            results[f"{cn}子菜单"] = (
                "PASS" if not miss else f"FAIL (missing={miss})")

        grayed = []
        submenus = []
        for i, lbl, st in rows:
            if st & (MF_GRAYED | MF_DISABLED):
                grayed.append(lbl)
            _oid, sub = topbar_util.item_info(hm, i)
            if sub:
                submenus.append((sub, lbl + " > "))
        for sub, prefix in submenus:
            for _i, lbl, st in topbar_util.menu_items(sub):
                if lbl.strip() and (st & (MF_GRAYED | MF_DISABLED)):
                    grayed.append(prefix + lbl)
        print(f"{LOG} grayed={grayed}")
        results["各条目可点击（无灰置）"] = (
            "PASS" if not grayed else f"FAIL (grayed={grayed})")

        # ---- 视觉展开（飞书步骤 3「依次悬停/观察含子菜单的条目」）----
        # HMENU 直读已证明子菜单内容；这里再把三条父条目逐个悬停打开，
        # 让录屏里能看到子菜单本体（视频是全屏 5fps 采样，停留 1.6s）。
        # 行高实测 ~22px；候选 y 从公式点向下/向上探（2.4.2 行位有偏移）。
        n_items = len(topbar_util.menu_items(hm))
        cx = (_rect[0] + _rect[2]) // 2
        known = {_mhwnd}
        visual = []
        for cn, needle, wanted in SUB_REQUIRED:
            idx = topbar_util.find_item(hm, needle)
            found = None
            if idx is not None:
                visible = {m[4] for m in
                           topbar_util._enum_menu_windows(session.pid)}
                known = (known & visible) | {_mhwnd}
                for y in topbar_util.submenu_row_candidates(_rect, n_items, idx):
                    winutil.user32.SetCursorPos(cx, y)
                    time.sleep(0.7)
                    for m in topbar_util._enum_menu_windows(session.pid):
                        if m[4] in known:
                            continue
                        known.add(m[4])
                        sub_rows = [lb.lower() for _i, lb, _st in
                                    topbar_util.menu_items(
                                        topbar_util.menu_hmenu(m[4]))]
                        if all(any(w in lb for lb in sub_rows)
                               for _wcn, w in wanted):
                            found = (m[:4], sub_rows)
                            break
                    if found:
                        break
            if found:
                print(f"{LOG} {cn} visual submenu rect={found[0]} rows={found[1]}")
                visual.append((cn, True, ""))
                time.sleep(1.6)      # 录屏停留，让子菜单清晰可见
            else:
                print(f"{LOG} {cn} visual submenu NOT opened")
                visual.append((cn, False, "no submenu popup"))
            # 收拢：光标移回一级行 0（Temperature），子菜单随即关闭
            topbar_util.hover_row(_rect, n_items, 0)
            time.sleep(0.7)
        bad_visual = [f"{cn}:{why}" for cn, ok, why in visual if not ok]
        results["子菜单视觉展开（流量/转弯/输入整形）"] = (
            "PASS" if not bad_visual else f"FAIL ({', '.join(bad_visual)})")

        results["检查期间菜单保持展开"] = (
            "PASS" if topbar_util._enum_menu_windows(session.pid)
            else "FAIL (closed early)")
        # 2.4.2 dismissal facts: WM_CANCELMODE ignored, m7.dismiss_menus's
        # right-click fallback opens a canvas CONTEXT menu; the working
        # channel is foreground + real ESC x2 (probe_242_calibdismiss{,2}).
        results["菜单可关闭（前台 ESC）"] = (
            "PASS" if topbar_util.close_calibration_menu(session)
            else "FAIL (still open)")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
