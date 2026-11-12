#!/usr/bin/env python3
# probe_242_inputshaping214.py — Calibration > Input Shaping > Frequency (#214).
#
# #214 needs the frequency dialog's defaults: X/Y 15~110 Hz, damping 0.15,
# and the two test-model choices (ringing tower / quick tower). This probe
# opens the submenu row and dumps the dialog (no OK click).
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

LOG = "[p242is214]"


def real_click(x, y):
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def dialogs(session):
    return [(c, t, r, h) for c, t, r, h in m7._visible_toplevels(session.pid)
            if c == "#32770"]


def open_submenu(session, parent_substr, row_substr):
    menu = topbar_util.open_calibration_menu(session)
    if not menu:
        return None
    rect, mhwnd, hm = menu
    n = len(topbar_util.menu_items(hm))
    idx = topbar_util.find_item(hm, parent_substr)
    known = {mhwnd}
    cx = (rect[0] + rect[2]) // 2
    for y in topbar_util.submenu_row_candidates(rect, n, idx):
        winutil.user32.SetCursorPos(cx, y)
        time.sleep(0.7)
        for m in topbar_util._enum_menu_windows(session.pid):
            if m[4] in known:
                continue
            known.add(m[4])
            shm = topbar_util.menu_hmenu(m[4])
            labels = [l.lower() for _i, l, _s in topbar_util.menu_items(shm)]
            if any(row_substr.lower() in l for l in labels):
                print(f"{LOG} submenu rect={m[:4]} rows={labels}")
                return (m[:4], m[4], shm)
    return None


def click_submenu_row(session, sub_rect, shm, want_substr):
    items = topbar_util.menu_items(shm)
    idx = next((i for i, l, _s in items
                if want_substr.lower() in l.lower()), None)
    if idx is None:
        return False
    n = len(items)
    x = (sub_rect[0] + sub_rect[2]) // 2
    for y in topbar_util.submenu_row_candidates(sub_rect, n, idx):
        for attempt in (1, 2):
            print(f"{LOG} click {want_substr!r} y={y} attempt={attempt}")
            real_click(x, y)
            time.sleep(1.5)
            if any(t for c, t, r, h in dialogs(session)):
                return True
    return False


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        print(f"{LOG} base frac={m7.model_colored_frac(session):.4%}")
        sub = open_submenu(session, "input shaping", "input shaping frequency")
        if not sub:
            print(f"{LOG} no input shaping submenu")
            return 1
        if not click_submenu_row(session, sub[0], sub[2],
                                 "input shaping frequency"):
            print(f"{LOG} frequency row did not open a dialog")
            return 1
        dlg = next((d for d in dialogs(session)
                    if "input shaping" in (d[1] or "").lower()), None)
        print(f"{LOG} dialogs={[(c, t, r) for c, t, r, h in dialogs(session)]}")
        if not dlg:
            return 1
        print(f"{LOG} dialog {dlg[1]!r} rect={dlg[2]}")
        for t, r, h in export_util._children_texts(dlg[3]):
            cls = winutil.window_class(h)
            vis = bool(winutil.user32.IsWindowVisible(h))
            en = bool(winutil.user32.IsWindowEnabled(h))
            if vis or t.strip():
                val = ""
                if cls == "Edit":
                    val = f" text={winutil.edit_text(h)!r}"
                print(f"{LOG}   {cls:12s} vis={vis} en={en} {t!r} "
                      f"rect={r}{val}")
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
