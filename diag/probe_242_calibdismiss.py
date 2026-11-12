#!/usr/bin/env python3
# probe_242_calibdismiss.py — why does the Calibration popup survive dismiss?
#
# m8x_206 failed only on its own cleanup check ("菜单可关闭"), while every
# Feishu step passed. This probe opens the Calibration menu, runs the standard
# m7.dismiss_menus, then reports the remaining #32768 windows and tries the
# individual dismissal channels (real ESC, real right-click, WM_CANCELMODE,
# real left-click on the canvas) so the case can use the one that works.
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
from harness import topbar_util, winutil

LOG = "[p242cd]"


def wins(session):
    return [m[:5] for m in topbar_util._enum_menu_windows(session.pid)]


def poll(session, label, seconds=4.0):
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
        m7.dismiss_menus(session)
        remaining = poll(session, "after m7.dismiss_menus")
        if remaining:
            print(f"{LOG} channel: real ESC x2")
            for _ in range(2):
                winutil.user32.keybd_event(0x1B, 0, 0, 0)
                winutil.user32.keybd_event(0x1B, 0, 2, 0)
                time.sleep(0.2)
            remaining = poll(session, "after ESC")
        if remaining:
            img = m7.capture_bgr(session)
            sx, sy = m7.client(session, m7.VIEWPORT_X0 + 60, img.shape[0] - 160)
            print(f"{LOG} channel: real right-click @({sx},{sy})")
            winutil.real_right_click_screen(sx, sy)
            remaining = poll(session, "after right-click")
        if remaining:
            print(f"{LOG} channel: WM_CANCELMODE")
            topbar_util.close_menu_windows(session.pid)
            remaining = poll(session, "after CANCELMODE")
        if remaining:
            img = m7.capture_bgr(session)
            sx, sy = m7.client(session, m7.VIEWPORT_X0 + 60, img.shape[0] - 160)
            print(f"{LOG} channel: real left-click @({sx},{sy})")
            winutil.real_click_screen(sx, sy)
            remaining = poll(session, "after left-click")
        print(f"{LOG} final remaining={bool(remaining)}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
