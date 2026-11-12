#!/usr/bin/env python3
# probe_242_submenu.py — 2.4.2 用 HMENU 直接枚举子菜单（绕开 hover）
# 2.4.2 上工具条 tooltip 完全取不到（jump/nudge/slide-in 三种都无 tooltip 窗口），
# 菜单 hover 也不稳定。但菜单是原生 HMENU：MN_GETHMENU + GetSubMenu 可以
# 不 hover 直接列出子菜单行并按其命令 id 派发（同 m3g 的 activate_menu_item）。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import ctypes
import m7_common as m7
import m8_common as m8
from harness import topbar_util
from m3_common import add_common_args, boot_session

LOG = "[p242s]"
user32 = ctypes.WinDLL("user32")


def dump_menu(hmenu, indent="  "):
    rows = m7.list_menu(hmenu)
    for idx, label in rows:
        info = topbar_util.item_info(hmenu, idx)
        oid = info[0] if info else None
        sub = info[1] if info else None
        print(f"{LOG}{indent}[{idx}] {label!r} id={oid} submenu={bool(sub)}")
        if sub:
            dump_menu(sub, indent + "    ")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(),
                         default_model=HERE / "fixtures" / "Prusa.stl")
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, _ = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        for name, opener in (("FILE", topbar_util.open_file_menu),
                             ("DROPDOWN", topbar_util.open_dropdown_menu)):
            menu = opener(session)
            if not menu:
                print(f"{LOG} {name} did not open")
                continue
            _rect, mhwnd, mhmenu = menu
            print(f"{LOG} ==== {name} ====")
            dump_menu(mhmenu)
            m7.dismiss_menus(session)
            time.sleep(1.0)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
