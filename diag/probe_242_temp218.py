#!/usr/bin/env python3
# probe_242_temp218.py — Temperature dialog radio switching for #218.
#
# #218: switching Filament type must update Start/End defaults (ABS/ASA
# 270->230, PETG 250->230, PCTG 280->240, TPU 240->210, PA-CF/PET-CF
# 320->280, PLA/Custom 230->190; step fixed 5). This probe clicks each
# radio circle and reads the three fields.
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7
from m3_common import add_common_args, boot_session
from harness import export_util, topbar_util, winutil

LOG = "[p242t218]"
TYPES = ["PLA", "ABS/ASA", "PETG", "PCTG", "TPU", "PA-CF", "PET-CF",
         "Custom"]


def real_click(x, y):
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def temp_dialog(session):
    for cls, t, r, h in m7._visible_toplevels(session.pid):
        if cls == "#32770" and "temperature calibration" in (t or "").lower():
            return (cls, t, r, h)
    return None


def open_temp(session):
    menu = topbar_util.open_calibration_menu(session)
    if not menu:
        return None
    rect, _m, hm = menu
    idx = topbar_util.find_item(hm, "temperature")
    cx = (rect[0] + rect[2]) // 2
    for y in topbar_util.submenu_row_candidates(rect, len(topbar_util.menu_items(hm)), idx):
        real_click(cx, y)
        time.sleep(1.5)
        d = temp_dialog(session)
        if d:
            return d
    return None


def field(dlg, label):
    kids = export_util._children_texts(dlg[3])
    lab = next(((t, r) for t, r, h in kids
                if t.strip().lower().startswith(label)), None)
    if not lab:
        return None
    ly = (lab[1][1] + lab[1][3]) // 2
    for t, r, h in kids:
        if winutil.window_class(h) == "Edit" and \
                abs(((r[1] + r[3]) // 2) - ly) <= 14 and \
                winutil.user32.IsWindowVisible(h):
            return h
    return None


def radio_click(dlg, label):
    """Click the circle (empty Static) left of the label on the same row."""
    kids = export_util._children_texts(dlg[3])
    lab = next(((t, r) for t, r, h in kids
                if t.strip() == label), None)
    if not lab:
        return None
    ly = (lab[1][1] + lab[1][3]) // 2
    circles = [(r, h) for t, r, h in kids
               if not t.strip() and winutil.window_class(h) in ("Static", "Button")
               and abs(((r[1] + r[3]) // 2) - ly) <= 12
               and r[0] < lab[1][0] and r[0] > lab[1][0] - 40
               and (r[2] - r[0]) <= 30]
    if circles:
        r = circles[0][0]
        real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
        return "circle"
    # fallback: click the label itself
    real_click((lab[1][0] + lab[1][2]) // 2, ly)
    return "label"


def read_vals(dlg):
    s = field(dlg, "start temp")
    e = field(dlg, "end temp")
    t = field(dlg, "temp step")
    if not (s and e and t):
        return None
    return (winutil.edit_text(s).strip(), winutil.edit_text(e).strip(),
            winutil.edit_text(t).strip(),
            bool(winutil.user32.IsWindowEnabled(t)))


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        dlg = open_temp(session)
        print(f"{LOG} dialog={bool(dlg)}")
        if not dlg:
            return 1
        for name in TYPES:
            how = radio_click(dlg, name)
            time.sleep(1.5)
            vals = read_vals(dlg)
            print(f"{LOG} {name:8s} click={how} vals={vals}")
        # back to PLA
        how = radio_click(dlg, "PLA")
        time.sleep(1.5)
        print(f"{LOG} back PLA click={how} vals={read_vals(dlg)}")
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
