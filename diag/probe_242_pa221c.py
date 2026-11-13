#!/usr/bin/env python3
# probe_242_pa221c.py — visual state of Print numbers per PA method.
#
# BM_GETCHECK reads 0 for PA Line / PA Pattern and a manual real click did
# not change it. This probe saves the Print-numbers row crop per method and
# after BM_SETCHECK(1), so we can tell whether the checkbox is actually
# unchecked or the API reading is wrong. Also prints the button style.
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

LOG = "[p242pa221c]"
BM_GETCHECK = 0x00F0
BM_SETCHECK = 0x00F1
BM_CLICK = 0x00F5
GWL_STYLE = -16
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
    ly = (lab[1] + lab[3]) // 2
    return next(((t, r, h) for t, r, h in kids(dlg)
                 if winutil.window_class(h) == "Button"
                 and abs(((r[1] + r[3]) // 2) - ly) <= 14
                 and winutil.user32.IsWindowVisible(h)), None)


def shot(dlg, tag):
    w, h, bgra = winutil.capture_window(dlg[3])
    img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
    p = ART / f"p242_pa221_{tag}.png"
    cv2.imwrite(str(p), img)
    print(f"{LOG} shot {tag} -> {p.name} shape={img.shape}")


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
        b = pn_btn(dlg)
        style = winutil.user32.GetWindowLongW(b[2], GWL_STYLE) if b else None
        print(f"{LOG} print-numbers button rect={b and b[1]} style=0x{style:x}"
              if b else f"{LOG} print-numbers button missing")

        radio_click(dlg, "PA Line")
        b = pn_btn(dlg)
        print(f"{LOG} PA Line state={winutil.user32.SendMessageW(b[2], BM_GETCHECK, 0, 0)} "
              f"en={bool(winutil.user32.IsWindowEnabled(b[2]))}")
        shot(dlg, "line")
        winutil.user32.SendMessageW(b[2], BM_CLICK, 0, 0)
        time.sleep(0.8)
        print(f"{LOG} after BM_CLICK state={winutil.user32.SendMessageW(b[2], BM_GETCHECK, 0, 0)}")
        shot(dlg, "line_bmclick")
        winutil.user32.SendMessageW(b[2], BM_SETCHECK, 1, 0)
        time.sleep(0.5)
        print(f"{LOG} after BM_SETCHECK(1) state={winutil.user32.SendMessageW(b[2], BM_GETCHECK, 0, 0)}")
        shot(dlg, "line_forced")

        radio_click(dlg, "PA Pattern")
        b = pn_btn(dlg)
        print(f"{LOG} PA Pattern state={winutil.user32.SendMessageW(b[2], BM_GETCHECK, 0, 0)} "
              f"en={bool(winutil.user32.IsWindowEnabled(b[2]))}")
        shot(dlg, "pattern")
        winutil.user32.SendMessageW(b[2], BM_SETCHECK, 1, 0)
        time.sleep(0.5)
        shot(dlg, "pattern_forced")

        radio_click(dlg, "PA Tower")
        b = pn_btn(dlg)
        print(f"{LOG} PA Tower state={winutil.user32.SendMessageW(b[2], BM_GETCHECK, 0, 0)} "
              f"en={bool(winutil.user32.IsWindowEnabled(b[2]))}")
        shot(dlg, "tower")

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
