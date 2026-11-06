#!/usr/bin/env python3
# probe_241_plate12.py — #194 删盘入口搜索：条带左上延伸带 + 盘号标签右键
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPlate12]"
STL = HERE / "fixtures" / "Prusa.stl"


def tooltip_right(session, cx, cy, dwell_s=1.2):
    import m7_common as m7
    from harness import mix_dialog_util as mdu
    sx, sy = m7.client(session, cx, cy)
    m7.winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    deadline = time.monotonic() + dwell_s
    while time.monotonic() < deadline:
        img = m7.capture_bgr(session)
        crop = img[max(0, cy - 12):cy + 48, cx + 8:cx + 200]
        if crop.size:
            words = mdu.ocr_words_img(crop, scale=3)
            text = " ".join(w for w, *_ in words)
            if len(text) >= 4:
                return text.strip()
        time.sleep(0.3)
    return ""


def plate_width(session):
    import cv2
    import numpy as np
    import m7_common as m7
    img = m7.capture_bgr(session)
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
        if w0 and w1 and w1 >= w0 * 1.25:
            return True
    return False


def main() -> int:
    import m7_common as m7
    import m8_common as m8
    from m3_common import add_common_args, boot_session
    from harness import topbar_util, winutil as wu

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        m7.ensure_maximized(session)
        if not add_plate_verified(session):
            print(f"{LOG} add-plate FAILED")
            return 1
        print(f"{LOG} LABEL-TWO-PLATES")
        # 条带左上延伸带（沿对角趋势：Auto orient (1390,242) 往上 ~(-25,+15)/步）
        pts = [(x, y) for y in range(168, 243, 9) for x in range(1330, 1401, 8)]
        print(f"{LOG} ext grid={len(pts)}")
        found = {}
        for i, (x, y) in enumerate(pts):
            tip = tooltip_right(session, x, y)
            if tip and tip.lower() not in found:
                found[tip.lower()] = (x, y, tip)
                print(f"{LOG} EXT-TOOLTIP @({x},{y}): {tip!r}")
        # 盘号标签区右键（02 标签在盘右上角一带）
        for (bx, by) in ((1520, 330), (1540, 350), (1500, 310)):
            sx, sy = m7.client(session, bx, by)
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            wu.real_click_screen(sx, sy)
            time.sleep(0.4)
            wu.real_right_click_screen(sx, sy)
            time.sleep(1.0)
            got = None
            for rect, hwnd in [(m[:4], m[4]) for m in
                               topbar_util._enum_menu_windows(session.pid)]:
                if rect[0] - 60 <= sx <= rect[2] + 60 and \
                        rect[1] - 60 <= sy <= rect[3] + 60:
                    got = hwnd
                    break
            if got:
                items = m7.list_menu(topbar_util.menu_hmenu(got))
                print(f"{LOG} LABEL-RIGHT-CLICK @({bx},{by}) menu: "
                      f"{[l for _i, l in items]}")
                m7.dismiss_menus(session)
            else:
                print(f"{LOG} LABEL-RIGHT-CLICK @({bx},{by}) no menu")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
