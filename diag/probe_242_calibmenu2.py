#!/usr/bin/env python3
# probe_242_calibmenu2.py — open the 2.4.2 topbar "Calibration" tool and dump
# its menu tree (items + command ids + submenus) without hovering anything.
#
# Context: the top-band screenshot (artifacts/p242cm_top.png) shows the
# Calibration label right of File/icons; the old topbar probes only tried
# offsets 10-60 (File) and 70-130 (dropdown), which is why it was missed.
# Here we probe offsets 250-420 (step 10) and stop at the first popup.
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
from harness import topbar_util, winutil as wu

LOG = "[p242cm2]"


def dump(hmenu, indent="  "):
    for idx, label in m7.list_menu(hmenu):
        info = topbar_util.item_info(hmenu, idx)
        oid, sub = (info[0], info[1]) if info else (None, None)
        print(f"{LOG}{indent}[{idx}] {label!r} id={oid} sub={bool(sub)}")
        if sub:
            dump(sub, indent + "    ")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        tb = topbar_util._topbar(session.hwnd)
        print(f"{LOG} topbar={tb}")
        if not tb:
            return 1
        _text, rect, _ch = tb
        cy = (rect[1] + rect[3]) // 2
        for off in range(250, 430, 10):
            x = rect[0] + off
            wu.user32.SetCursorPos(x, cy)
            time.sleep(0.15)
            wu.msg_click_screen(x, cy, session.hwnd)
            time.sleep(0.75)
            menus = topbar_util._enum_menu_windows(session.pid)
            if not menus:
                continue
            print(f"{LOG} popup at offset {off}")
            for m in menus:
                hm = topbar_util.menu_hmenu(m[4])
                rows = [l for _i, l in m7.list_menu(hm)]
                print(f"{LOG} menu rect={m[:4]} rows={rows}")
                dump(hm)
            m7.dismiss_menus(session)
            time.sleep(0.5)
            print(f"{LOG} done")
            return 0
        print(f"{LOG} no popup in 250..420")
        # last resort: File + dropdown confirm (for the record)
        menu = topbar_util.open_dropdown_menu(session)
        if menu:
            print(f"{LOG} DROPDOWN rows={[l for _i, l in m7.list_menu(menu[2])]}")
            m7.dismiss_menus(session)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
