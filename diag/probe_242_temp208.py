#!/usr/bin/env python3
# probe_242_temp208.py — characterize Calibration > Temperature for #208.
#
# #208 needs: dialog defaults (Start 230 / End 190 / step 5 disabled), OK
# generates the preset 9-section temperature tower, then slice+gcode shows
# 9 temperature steps. This probe only dumps the dialog and its enabled
# states; it does not click OK (the case will).
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

LOG = "[p242t208]"


def real_click(x, y):
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def new_dialogs(session, known):
    return [(c, t, r, h) for c, t, r, h in m7._visible_toplevels(session.pid)
            if c == "#32770" and h not in known]


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        print(f"{LOG} base frac={m7.model_colored_frac(session):.4%}")
        menu = topbar_util.open_calibration_menu(session)
        print(f"{LOG} menu={bool(menu)}")
        if not menu:
            return 1
        rect, _mhwnd, hm = menu
        items = topbar_util.menu_items(hm)
        idx = topbar_util.find_item(hm, "temperature")
        print(f"{LOG} temperature idx={idx} rows={[l for _i, l, _s in items]}")
        known = {h for _c, _t, _r, h in m7._visible_toplevels(session.pid)}
        cx = (rect[0] + rect[2]) // 2
        dlg = None
        for y in topbar_util.submenu_row_candidates(rect, len(items), idx):
            print(f"{LOG} click y={y}")
            real_click(cx, y)
            time.sleep(1.5)
            wins = new_dialogs(session, known)
            print(f"{LOG} new dialogs={[(c, t, r) for c, t, r, h in wins]}")
            if wins:
                dlg = wins[0]
                break
        if not dlg:
            return 1
        print(f"{LOG} dialog {dlg[0]} {dlg[1]!r} rect={dlg[2]}")
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
        print(f"{LOG} PA-like frac={m7.model_colored_frac(session):.4%}")
        user32 = winutil.user32
        user32.SetForegroundWindow(dlg[3])
        time.sleep(0.3)
        user32.keybd_event(0x1B, 0, 0, 0)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.5)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
