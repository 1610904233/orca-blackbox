#!/usr/bin/env python3
# probe_241_plate11.py — 盘侧图标列标定 v6：右向 tooltip OCR + 盘心右键
#
# plate10 教训：m7.tooltip_text 只 OCR 光标**正下方** (cy+14..cy+96)，而盘侧
# 图标的 tooltip 渲染在**右侧**（react64 实证：光标 (1456,290)、tip 在
# x1500-1585/y292-310）→ 全部漏读。v6 用右向裁剪 (cx+8..cx+190, cy-10..cy+45)
# 重扫；右键点位改用盘 02 菱形中心 (1590,545) 一带。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPlate11]"
STL = HERE / "fixtures" / "Prusa.stl"


def tooltip_right(session, cx, cy, dwell_s=1.2):
    """OCR 光标**右侧**的 GL tooltip（盘侧图标专用，m7.tooltip_text 裁剪
    在正下方会全漏——plate10 实测 169 点 0 命中）。"""
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
        print(f"{LOG} add-plate try{i + 1}: {w0} -> {w1}")
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
        print(f"{LOG} arrived={ok} frac={frac:.4%}")
        m7.ensure_maximized(session)
        if not add_plate_verified(session):
            print(f"{LOG} add-plate FAILED — abort")
            return 1
        print(f"{LOG} LABEL-TWO-PLATES")

        found = {}
        pts = [(x, y) for y in range(206, 326, 9) for x in range(1390, 1481, 7)]
        print(f"{LOG} hover grid={len(pts)}")
        for i, (x, y) in enumerate(pts):
            tip = tooltip_right(session, x, y)
            if tip:
                key = tip.lower()
                if key not in found:
                    found[key] = (x, y, tip)
                    print(f"{LOG} TOOLTIP @({x},{y}): {tip!r}")
            if i % 26 == 0:
                print(f"{LOG} hover {i}/{len(pts)} found={len(found)}")
        print(f"{LOG} ICON-MAP: {[(v[0], v[1], v[2]) for v in found.values()]}")

        for (bx, by) in ((1590, 545), (1600, 560), (1570, 530)):
            sx, sy = m7.client(session, bx, by)
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            wu.real_click_screen(sx, sy)
            time.sleep(0.5)
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
