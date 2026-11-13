#!/usr/bin/env python3
# probe_242_pa222b.py — correct owner-drawn checkbox oracle for PA methods.
#
# My teal-pixel oracle only recognizes the ENABLED checked box (PA Line is
# teal). A DISABLED checked box draws a gray/dark tick (user screenshot,
# 11-13), so teal=0 misread PA Pattern as unchecked. This probe zooms the
# checkbox crop per method and counts dark interior pixels vs teal pixels.
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import cv2
import numpy as np

import m7_common as m7
from m3_common import add_common_args, boot_session
from harness import export_util, topbar_util, winutil

LOG = "[p242pa222b]"
ART = HERE / "artifacts"


def real_click(x, y):
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def pa_dialog(session):
    for cls, t, r, h in m7._visible_toplevels(session.pid):
        if cls == "#32770" and "pa calibration" in (t or "").lower():
            return (cls, t, r, h)
    return None


def open_pa(session):
    menu = topbar_util.open_calibration_menu(session)
    if not menu:
        return None
    rect, _m, hm = menu
    idx = topbar_util.find_item(hm, "pressure advance")
    cx = (rect[0] + rect[2]) // 2
    for y in topbar_util.submenu_row_candidates(rect, len(topbar_util.menu_items(hm)), idx):
        real_click(cx, y)
        time.sleep(1.5)
        d = pa_dialog(session)
        if d:
            return d
    return None


def kids(dlg):
    return export_util._children_texts(dlg[3])


def label_rect(dlg, text):
    return next((r for t, r, h in kids(dlg) if t.strip() == text), None)


def radio_click(dlg, label):
    lab = label_rect(dlg, label)
    if not lab:
        return False
    ly = (lab[1] + lab[3]) // 2
    circles = [r for t, r, h in kids(dlg)
               if not t.strip()
               and winutil.window_class(h) in ("Static", "Button")
               and abs(((r[1] + r[3]) // 2) - ly) <= 12
               and lab[0] - 40 < r[0] < lab[0]
               and (r[2] - r[0]) <= 30]
    if circles:
        r = circles[0]
        real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    else:
        real_click((lab[0] + lab[2]) // 2, ly)
    time.sleep(1.5)
    return True


def pn_btn(dlg):
    lab = label_rect(dlg, "Print numbers")
    if not lab:
        return None
    ly = (lab[1] + lab[3]) // 2
    return next(((r, h) for t, r, h in kids(dlg)
                 if winutil.window_class(h) == "Button"
                 and abs(((r[1] + r[3]) // 2) - ly) <= 14
                 and winutil.user32.IsWindowVisible(h)), None)


def box_stats(dlg, tag):
    btn = pn_btn(dlg)
    if not btn:
        print(f"{LOG} {tag}: no button")
        return
    br, bh = btn
    cx0, cy0 = winutil.client_to_screen(dlg[3], 0, 0)
    w, h, bgra = winutil.capture_window(dlg[3])
    img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
    x0, y0 = max(0, br[0] - cx0), max(0, br[1] - cy0)
    x1, y1 = min(w, br[2] - cx0), min(h, br[3] - cy0)
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        print(f"{LOG} {tag}: empty crop local=({x0},{y0},{x1},{y1})")
        return
    inner = crop[3:-3, 3:-3]
    gray = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY)
    dark = int((gray < 190).sum())
    teal = int(((inner[:, :, 0] > 100) & (inner[:, :, 1] > 100)
                & (inner[:, :, 2] < 120)).sum())
    en = bool(winutil.user32.IsWindowEnabled(bh))
    zoom = cv2.resize(crop, None, fx=10, fy=10,
                      interpolation=cv2.INTER_NEAREST)
    p = ART / f"p242_pa222_box_{tag}.png"
    cv2.imwrite(str(p), zoom)
    print(f"{LOG} {tag}: shape={crop.shape} dark={dark} teal={teal} "
          f"enabled={en} -> {p.name}")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        dlg = open_pa(session)
        print(f"{LOG} dialog={bool(dlg)}")
        if not dlg:
            return 1
        radio_click(dlg, "PA Tower")
        box_stats(dlg, "tower")
        radio_click(dlg, "PA Line")
        box_stats(dlg, "line")
        radio_click(dlg, "PA Pattern")
        box_stats(dlg, "pattern")
        winutil.user32.SetForegroundWindow(dlg[3])
        time.sleep(0.3)
        winutil.user32.keybd_event(0x1B, 0, 0, 0)
        winutil.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.5)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
