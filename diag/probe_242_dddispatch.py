#!/usr/bin/env python3
# probe_242_dddispatch.py — 242d 上 dropdown 菜单 WM_COMMAND 的路由实证
#
# 现象（j833 冒烟）：File>Import 子菜单行 WM_COMMAND 到框架窗口有效
# （m7c GREEN），但 dropdown>Edit>Delete All / View>Top 的 WM_COMMAND
# completed=True 却无动作（m3b/m3i RED）。假设：dropdown 的
# TrackPopupMenu owner 是 BBLTopbar 子窗口，命令需发给 owner 而非框架。
# 本探针：
#   1) dump 242d 的 FILE/DROPDOWN 菜单树（含 id/子菜单）
#   2) Edit>Delete All：分别向 框架 / topbar 子窗口 发 WM_COMMAND，
#      以「彩色占比 < 空床线」为可观察量，各自判定
#   3) View>Top：同样双目标对照（视口差分为可观察量）
import argparse
import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7
import m8_common as m8
from harness import topbar_util
from m3_common import MIXED_3MF, add_common_args, boot_session

LOG = "[p242dd]"
WM_COMMAND = 0x0111
user32 = ctypes.WinDLL("user32")


def dump_menu(hmenu, indent="  "):
    for idx, label in m7.list_menu(hmenu):
        wid, sub = topbar_util.item_info(hmenu, idx)
        print(f"{LOG}{indent}[{idx}] {label!r} id={wid} submenu={bool(sub)}")
        if sub:
            dump_menu(sub, indent + "    ")


def locate(session, top_opener, via, row):
    menu = top_opener(session)
    if not menu:
        return None, None, None
    _rect, _hwnd, hmenu = menu
    via_idx = topbar_util.find_item(hmenu, via)
    if via_idx is None:
        print(f"{LOG} no {via!r} row; rows={[l for _i, l in m7.list_menu(hmenu)]}")
        topbar_util.close_menu_windows(pid)
        return None, None, None
    _vid, sub = topbar_util.item_info(hmenu, via_idx)
    if not sub:
        print(f"{LOG} {via!r} has no submenu")
        topbar_util.close_menu_windows(pid)
        return None, None, None
    rows = m7.list_menu(sub)
    print(f"{LOG} {via} submenu rows: {rows}")
    row_idx = topbar_util.find_item(sub, row)
    if row_idx is None:
        topbar_util.close_menu_windows(pid)
        return None, None, None
    wid, _s = topbar_util.item_info(sub, row_idx)
    return sub, row_idx, wid


def send_cmd(hwnd, wid):
    res = ctypes.c_ulong()
    ok = user32.SendMessageTimeoutW(hwnd, WM_COMMAND, wid, 0,
                                    0x0000 | 0x0002, 3000,
                                    ctypes.byref(res))
    print(f"{LOG} WM_COMMAND(id={wid}) -> hwnd={hex(hwnd)} completed={bool(ok)}")


def main() -> int:
    global pid
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    pid = session.pid
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.3%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)

        tb = topbar_util._topbar(session.hwnd)
        tb_hwnd = tb[2] if tb else None
        print(f"{LOG} frame={hex(session.hwnd)} topbar={hex(tb_hwnd) if tb_hwnd else None}")

        for name, opener in (("FILE", topbar_util.open_file_menu),
                             ("DROPDOWN", topbar_util.open_dropdown_menu)):
            menu = opener(session)
            if not menu:
                print(f"{LOG} {name} did not open")
                continue
            print(f"{LOG} ==== {name} tree ====")
            dump_menu(menu[2])
            m7.dismiss_menus(session)
            time.sleep(1.0)

        # --- Edit > Delete All, 双目标对照 ---
        for target_name, target in (("frame", session.hwnd),
                                    ("topbar", tb_hwnd)):
            if not target:
                continue
            frac0 = m7.model_colored_frac(session)
            if frac0 < 0.004:
                print(f"{LOG} {target_name}: plate already empty — skip")
                continue
            _sub, _idx, wid = locate(session, topbar_util.open_dropdown_menu,
                                     "Edit", "Delete All")
            if wid is None:
                print(f"{LOG} {target_name}: Delete All row not located")
                continue
            send_cmd(target, wid)
            time.sleep(0.5)
            topbar_util.close_menu_windows(pid)
            fired = False
            for _ in range(10):
                if m7.model_colored_frac(session) < 0.004:
                    fired = True
                    break
                time.sleep(0.5)
            print(f"{LOG} DELETE-ALL via {target_name}: fired={fired} "
                  f"(frac {frac0:.3%} -> {m7.model_colored_frac(session):.3%})")
            if fired:
                break

        # --- View > Top, 双目标对照（视口差分）---
        import numpy as np
        for target_name, target in (("frame", session.hwnd),
                                    ("topbar", tb_hwnd)):
            if not target:
                continue
            before = m7.capture_bgr(session)
            _sub, _idx, wid = locate(session, topbar_util.open_dropdown_menu,
                                     "View", "Top")
            if wid is None:
                print(f"{LOG} {target_name}: Top row not located")
                continue
            send_cmd(target, wid)
            time.sleep(0.5)
            topbar_util.close_menu_windows(pid)
            time.sleep(1.5)
            after = m7.capture_bgr(session)
            diff = float(np.mean(np.abs(after[110:-60].astype(int)
                                       - before[110:-60].astype(int))))
            print(f"{LOG} VIEW-TOP via {target_name}: viewport_mad={diff:.2f}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
