#!/usr/bin/env python3
# probe_242_pa221.py — which control switches Method to PA Line?
#
# m8x_221: clicking the empty Static circle left of 'PA Line' left
# Print numbers unchecked (state=0), so the method may not have switched.
# This probe tries circle / label / row-area clicks and reads BM_GETCHECK
# (PA Tower unchecked, PA Line checked+editable, PA Pattern checked+disabled).
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

LOG = "[p242pa221]"
BM_GETCHECK = 0x00F0


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


def checkbox_by_label(dlg, label):
    kids = export_util._children_texts(dlg[3])
    lab = next(((t, r) for t, r, h in kids
                if t.strip().lower() == label), None)
    if not lab:
        return None
    ly = (lab[1][1] + lab[1][3]) // 2
    for t, r, h in kids:
        if winutil.window_class(h) == "Button" and \
                abs(((r[1] + r[3]) // 2) - ly) <= 14 and \
                winutil.user32.IsWindowVisible(h):
            return h
    return None


def state(dlg):
    pn = checkbox_by_label(dlg, "print numbers")
    if not pn:
        return None
    return (winutil.user32.SendMessageW(pn, BM_GETCHECK, 0, 0),
            bool(winutil.user32.IsWindowEnabled(pn)))


def method_row(dlg):
    kids = export_util._children_texts(dlg[3])
    lab = next(((t, r) for t, r, h in kids if t.strip() == "PA Line"), None)
    print(f"{LOG} method row children:")
    for t, r, h in kids:
        cls = winutil.window_class(h)
        if lab and abs(((r[1] + r[3]) // 2) - ((lab[1][1] + lab[1][3]) // 2)) <= 25:
            print(f"{LOG}   {cls:10s} {t!r} rect={r} "
                  f"en={winutil.user32.IsWindowEnabled(h)}")
    return lab


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
        lab = method_row(dlg)
        print(f"{LOG} initial pn={state(dlg)}")
        # 1) circle left of label
        kids = export_util._children_texts(dlg[3])
        ly = (lab[1][1] + lab[1][3]) // 2
        circles = [(r, h) for t, r, h in kids
                   if not t.strip()
                   and winutil.window_class(h) in ("Static", "Button")
                   and abs(((r[1] + r[3]) // 2) - ly) <= 12
                   and lab[1][0] - 40 < r[0] < lab[1][0]
                   and (r[2] - r[0]) <= 30]
        print(f"{LOG} circles={[(r, winutil.window_class(h)) for r, h in circles]}")
        if circles:
            r, _h = circles[0]
            real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            time.sleep(1.5)
            print(f"{LOG} after circle click pn={state(dlg)}")
        # 2) label click
        if state(dlg) != (1, True):
            real_click((lab[1][0] + lab[1][2]) // 2, ly)
            time.sleep(1.5)
            print(f"{LOG} after label click pn={state(dlg)}")
        # 3) small offset inside the label's left edge
        if state(dlg) != (1, True):
            real_click(lab[1][0] + 4, ly)
            time.sleep(1.5)
            print(f"{LOG} after label-left click pn={state(dlg)}")
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
