#!/usr/bin/env python3
# probe_242_calibdismiss2.py — which channel closes the Calibration popup?
#
# probe_242_calibdismiss showed m7.dismiss_menus leaves a #32768 window at
# the right-click point (a canvas context menu opened by its fallback), not
# the Calibration menu. This probe tries the individual channels in order and
# reports the first one that leaves zero #32768 windows:
#   1) WM_CANCELMODE to the menu's own hwnd
#   2) real click on the Calibration topbar tool (toggle)
#   3) focus the frame, then real ESC x2
#   4) real left-click far outside the menu (empty canvas)
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7  # noqa: F401  (boot_session's shot archive hooks stdout)
from m3_common import add_common_args, boot_session
from harness import topbar_util, winutil

LOG = "[p242cd2]"
WM_CANCELMODE = 0x001F


def wins(session):
    return [m[:5] for m in topbar_util._enum_menu_windows(session.pid)]


def poll(session, label, seconds=2.5):
    end = time.monotonic() + seconds
    while True:
        w = wins(session)
        print(f"{LOG} {label}: wins={w}")
        if not w or time.monotonic() >= end:
            return w
        time.sleep(0.5)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        menu = topbar_util.open_calibration_menu(session)
        print(f"{LOG} opened={bool(menu)} wins={wins(session)}")
        if not menu:
            return 1
        _rect, mhwnd, _hm = menu

        print(f"{LOG} channel 1: WM_CANCELMODE -> menu hwnd")
        winutil.user32.SendMessageW(mhwnd, WM_CANCELMODE, 0, 0)
        remaining = poll(session, "after CANCELMODE")
        if remaining:
            tb = topbar_util._topbar(session.hwnd)
            if tb:
                _t, rect, _ch = tb
                x = rect[0] + 250
                cy = (rect[1] + rect[3]) // 2
                print(f"{LOG} channel 2: click Calibration tool again @({x},{cy})")
                winutil.user32.SetCursorPos(x, cy)
                time.sleep(0.3)
                winutil.real_click_screen(x, cy)
                remaining = poll(session, "after tool click")
        if remaining:
            print(f"{LOG} channel 3: focus frame + real ESC x2")
            winutil.user32.SetForegroundWindow(session.hwnd)
            time.sleep(0.5)
            for _ in range(2):
                winutil.user32.keybd_event(0x1B, 0, 0, 0)
                winutil.user32.keybd_event(0x1B, 0, 2, 0)
                time.sleep(0.25)
            remaining = poll(session, "after ESC")
        if remaining:
            print(f"{LOG} channel 4: real left-click far outside menu")
            winutil.user32.SetCursorPos(900, 600)
            time.sleep(0.2)
            winutil.real_click_screen(900, 600)
            remaining = poll(session, "after outside click")
        print(f"{LOG} final remaining={bool(remaining)}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
