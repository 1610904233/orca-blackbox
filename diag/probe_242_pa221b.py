#!/usr/bin/env python3
# probe_242_pa221b.py — Print numbers default per PA method (#221/#222).
#
# m8x_221: switching to PA Line turned Print numbers enabled (False->True)
# but BM_GETCHECK stayed 0, while Feishu #221 says "勾选且可编辑". This probe
# records: initial (PA Tower), after PA Line, after manually clicking the
# checkbox, after back to PA Tower, PA Line again, and PA Pattern.
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

LOG = "[p242pa221b]"
BM_GETCHECK = 0x00F0
BM_CLICK = 0x00F5


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


def pn_state(dlg):
    lab = label_rect(dlg, "Print numbers")
    if not lab:
        return None
    ly = (lab[1] + lab[3]) // 2
    h = next((h for t, r, h in kids(dlg)
              if winutil.window_class(h) == "Button"
              and abs(((r[1] + r[3]) // 2) - ly) <= 14
              and winutil.user32.IsWindowVisible(h)), None)
    if not h:
        return None
    return (winutil.user32.SendMessageW(h, BM_GETCHECK, 0, 0),
            bool(winutil.user32.IsWindowEnabled(h)))


def pn_click(dlg):
    lab = label_rect(dlg, "Print numbers")
    ly = (lab[1] + lab[3]) // 2
    for t, r, h in kids(dlg):
        if winutil.window_class(h) == "Button" and \
                abs(((r[1] + r[3]) // 2) - ly) <= 14 and \
                winutil.user32.IsWindowVisible(h):
            real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            time.sleep(0.8)
            return


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
        print(f"{LOG} initial (PA Tower) pn={pn_state(dlg)}")
        radio_click(dlg, "PA Line")
        print(f"{LOG} after PA Line pn={pn_state(dlg)}")
        pn_click(dlg)
        print(f"{LOG} after manual click pn={pn_state(dlg)}")
        radio_click(dlg, "PA Tower")
        print(f"{LOG} back PA Tower pn={pn_state(dlg)}")
        radio_click(dlg, "PA Line")
        print(f"{LOG} PA Line again pn={pn_state(dlg)}")
        radio_click(dlg, "PA Pattern")
        print(f"{LOG} PA Pattern pn={pn_state(dlg)}")
        radio_click(dlg, "PA Tower")
        print(f"{LOG} final PA Tower pn={pn_state(dlg)}")
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
