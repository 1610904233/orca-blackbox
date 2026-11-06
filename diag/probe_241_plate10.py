#!/usr/bin/env python3
# probe_241_plate10.py — 盘侧图标列标定 v5：hover tooltip 全读 + 盘面右键菜单
#
# plate9 破局：react64 截图显示 (1456,290) 旁有 tooltip「Lock current plate」
# —— 图标带 tooltip，只是老探针坐标全偏。v5 用已验证的 m7.tooltip_text 机制
# 沿条带精细 hover 扫描，把每个图标的语义读全（无点击、无副作用）；
# 再右键盘面找「移除当前板」的上下文菜单（#194 尚缺入口）。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPlate10]"
STL = HERE / "fixtures" / "Prusa.stl"


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


def add_plate_verified(session):
    import m7_common as m7
    w0 = plate_width(session)
    for i in range(3):
        m7.click_slot(session, 756)
        time.sleep(4.0)
        w1 = plate_width(session)
        print(f"{LOG} add-plate try{i + 1}: {w0} -> {w1}")
        if w0 and w1 and w1 >= w0 * 1.25:
            return True
    return False


def main() -> int:
    import m7_common as m7
    import m8_common as m8
    from m3_common import add_common_args, boot_session
    from harness import winutil as wu

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4%}")
        m7.ensure_maximized(session)
        if not add_plate_verified(session):
            print(f"{LOG} add-plate FAILED — abort")
            return 1
        print(f"{LOG} LABEL-TWO-PLATES")

        # 1) hover tooltip 扫描（plate9 命中带 + 周边余量）
        found = {}
        pts = [(x, y) for y in range(205, 326, 10) for x in range(1390, 1491, 8)]
        print(f"{LOG} hover grid={len(pts)}")
        for i, (x, y) in enumerate(pts):
            tip = m7.tooltip_text(session, x, y, dwell_s=1.1)
            if tip and len(tip.strip()) > 3:
                key = tip.strip().lower()
                if key not in found:
                    found[key] = (x, y, tip.strip())
                    print(f"{LOG} TOOLTIP @({x},{y}): {tip.strip()!r}")
            if i % 26 == 0:
                print(f"{LOG} hover {i}/{len(pts)} found={len(found)}")
        print(f"{LOG} icon map: {found}")

        # 2) 盘面右键（02 盘空床区）→ 上下文菜单行
        from harness import topbar_util
        for (bx, by) in ((1560, 600), (1650, 650), (1500, 520)):
            sx, sy = m7.client(session, bx, by)
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            wu.real_click_screen(sx, sy)      # 先左键激活画布（m7t 实证首击常被吞）
            time.sleep(0.5)
            wu.real_right_click_screen(sx, sy)
            got = None
            for rect, hwnd in [(m[:4], m[4]) for m in
                               topbar_util._enum_menu_windows(session.pid)]:
                if rect[0] - 4 <= sx <= rect[2] + 4 and \
                        rect[1] - 4 <= sy <= rect[3] + 4:
                    got = hwnd
                    break
            if got:
                items = m7.list_menu(topbar_util.menu_hmenu(got))
                print(f"{LOG} RIGHT-CLICK @({bx},{by}) menu: "
                      f"{[l for _i, l in items]}")
                m7.dismiss_menus(session)
                break
            print(f"{LOG} RIGHT-CLICK @({bx},{by}) no menu")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
