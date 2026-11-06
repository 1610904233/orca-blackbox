#!/usr/bin/env python3
# probe_241_plate6.py — 盘侧图标列标定（#194–#198 共同前置，plate2..5 之后的第 4 次尝试）
#
# 老探针败因：固定猜坐标 + 无截图差分 + 只单击。本探针两条路并走：
#   A. 顶栏下拉菜单全清单（文字可读 = 最稳入口；#204 已实证子菜单可真点）
#   B. 图标列 hover 差分网格扫描：悬停高亮是图标命中区的客观像素信号，
#      双帧噪底对照（idle-idle vs idle-hover），命中簇再做单击/双击取证
#      （盘宽 / 彩色占比 / #32770 标题+按钮 / Edit 控件），最后存项目数盘。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPlate6]"
STL = HERE / "fixtures" / "Prusa.stl"
PROJ = HERE / "artifacts" / "probe_241_plate6.3mf"


def crop_diff(a, b, x, y, r=22):
    """(x,y) 为中心的 2r×2r 窗口平均绝对差。"""
    h, w = a.shape[:2]
    x0, x1 = max(0, x - r), min(w, x + r)
    y0, y1 = max(0, y - r), min(h, y + r)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    d = abs(a[y0:y1, x0:x1].astype(int) - b[y0:y1, x0:x1].astype(int))
    return float(d.mean())


def snap(session):
    import cv2
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def plate_width(session):
    import cv2
    import numpy as np
    import m7_common as m7
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    h, w = img.shape[:2]
    x0, y0 = m7.VIEWPORT_X0 + 10, 110
    roi = img[y0:h - 60, x0:w - 10]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    dark = ((hsv[:, :, 2] < 130) & (hsv[:, :, 1] < 90)).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, _l, stats, _c = cv2.connectedComponentsWithStats(dark, 8)
    if n <= 1:
        return 0
    i = max(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA])
    return int(stats[i, cv2.CC_STAT_WIDTH])


def dialog_state(session):
    import m7_common as m7
    from harness import export_util
    out = []
    dlg = m7.wait_dialog(session.pid, timeout_s=0.4)
    if dlg:
        kids = [t.strip() for t, _r, _h in
                export_util._children_texts(dlg[3]) if t.strip()]
        out.append(f"dlg title={dlg[1]!r} kids={kids[:8]}")
    edits = [t for t, _r, _h in
             export_util._children_texts(session.hwnd) if t.strip()]
    if edits:
        out.append(f"main-kids={edits[:6]}")
    return " ".join(out)


def part_a_menus(session):
    """下拉菜单全清单（含子菜单行）。"""
    import m7_common as m7
    from harness import topbar_util
    menu = topbar_util.open_dropdown_menu(session)
    if not menu:
        print(f"{LOG} A: dropdown menu did not open")
        return
    mrect, mhwnd, mhmenu = menu
    items = m7.list_menu(mhmenu)
    print(f"{LOG} A dropdown rows: {[l for _i, l in items]}")
    for idx, label in items:
        if not label:
            continue
        topbar_util.hover_row(mrect, len(items), idx)
        sub = topbar_util.wait_submenu(session.pid, {mhwnd}, timeout_s=2.0)
        if sub:
            shmenu = sub[2]
            sub_items = m7.list_menu(shmenu)
            print(f"{LOG} A submenu {label!r}: {[l for _i, l in sub_items]}")
            topbar_util.close_menu_windows(session.pid)
            menu = topbar_util.open_dropdown_menu(session)
            if not menu:
                return
            mrect, mhwnd, mhmenu = menu
            items = m7.list_menu(mhmenu)
    m7.dismiss_menus(session)


def part_b_icons(session):
    """hover 差分网格扫描 + 命中簇点击取证。"""
    import m7_common as m7
    import m8_common as m8
    from harness import winutil as wu

    ok, frac = m8.wait_arrival(session)
    print(f"{LOG} B arrived={ok}")
    m7.ensure_maximized(session)
    print(f"{LOG} B state0 plate_w={plate_width(session)}")
    m7.click_slot(session, 756)
    time.sleep(4.0)
    print(f"{LOG} B state1(2 plates) plate_w={plate_width(session)}")
    print(f"{LOG} LABEL-TWO-PLATES")

    # 网格：plate4 证据的列带 x 1345..1445、y 260..500
    grid = [(x, y) for y in range(262, 500, 13) for x in range(1345, 1446, 10)]
    print(f"{LOG} B grid={len(grid)} points")
    hits = []
    for i, (x, y) in enumerate(grid):
        sx, sy = m7.client(session, x, y)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.30)
        idle1 = snap(session)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.25)
        idle2 = snap(session)
        time.sleep(0.45)                       # 悬停高亮时间
        hov = snap(session)
        noise = crop_diff(idle1, idle2, x, y)
        signal = crop_diff(idle2, hov, x, y)
        if noise < 1.0 and signal > 3.0 and signal > 3 * max(noise, 0.5):
            hits.append((x, y, round(signal, 1)))
            print(f"{LOG} B HIT @({x},{y}) signal={signal:.1f} noise={noise:.1f}")
        if i % 24 == 0:
            print(f"{LOG} B scan {i}/{len(grid)} hits={len(hits)}")
    # 簇合并（x/y 各 15px 内归一簇，取信号峰值点）
    clusters = []
    for x, y, s in hits:
        for c in clusters:
            if abs(c[0] - x) <= 15 and abs(c[1] - y) <= 15:
                if s > c[2]:
                    c[0], c[1], c[2] = x, y, s
                break
        else:
            clusters.append([x, y, s])
    clusters.sort(key=lambda c: c[1])
    print(f"{LOG} B clusters(top->bottom)={clusters}")
    print(f"{LOG} LABEL-CLUSTERS-DONE")

    # 点击取证（自上而下；每次点击后记录状态并清理弹窗）
    for j, (x, y, s) in enumerate(clusters):
        sx, sy = m7.client(session, x, y)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(2.2)
        st = (f"plate_w={plate_width(session)} "
              f"frac={m7.model_colored_frac(session):.3%} {dialog_state(session)}")
        print(f"{LOG} B CLICK{j} @({x},{y}) -> {st}")
        print(f"{LOG} LABEL-CLICK{j}-AFTER")
        dlg = m7.wait_dialog(session.pid, timeout_s=0.4)
        if dlg:
            m7.click_dialog_button(dlg[3], "cancel", fallback_first=False)
            time.sleep(1.0)
    # 双击取证（编辑盘名称假设）
    for j, (x, y, s) in enumerate(clusters[:4]):
        sx, sy = m7.client(session, x, y)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(0.12)
        wu.real_click_screen(sx, sy)
        time.sleep(2.2)
        print(f"{LOG} B DBLCLICK{j} @({x},{y}) -> {dialog_state(session)}")
        print(f"{LOG} LABEL-DBLCLICK{j}-AFTER")
        dlg = m7.wait_dialog(session.pid, timeout_s=0.4)
        if dlg:
            m7.click_dialog_button(dlg[3], "cancel", fallback_first=False)
            time.sleep(1.0)
    # 真值：存项目数盘
    if m7.save_project_as(session, PROJ):
        import zipfile
        import re
        with zipfile.ZipFile(PROJ) as z:
            cfg = z.read("Metadata/model_settings.config").decode(
                "utf-8", "replace")
        plates = re.findall(r'key="plater_id" value="(\d+)"', cfg)
        print(f"{LOG} B final plate count={len(plates)} ids={plates}")
    else:
        print(f"{LOG} B final save FAILED")


def main() -> int:
    import m8x_152 as base
    from m3_common import add_common_args

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = base.m7_boot(args, model=STL)
    try:
        part_a_menus(session)
        part_b_icons(session)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
