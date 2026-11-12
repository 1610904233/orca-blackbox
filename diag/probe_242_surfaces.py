#!/usr/bin/env python3
# probe_242_surfaces.py — 2.4.2 可观察面标定 v2
#
# 背景：2.4.2 全量 57 例 6 GREEN/51 RED，48 例红在「2.4.1 标定的观察面」。
# v1 结论：新包 File→Import 子菜单**能弹出**、下拉 Edit 子菜单**能弹出**；
# v1 在取子菜单句柄处崩溃（索引 bug），工具条扫描没跑到。
# v2：修 bug + 工具条扫描加「先点画布聚焦」与更长 dwell（怀疑 2.4.2 的
# tooltip 更慢/需要焦点），并打印 Import / Edit 子菜单的行文本。
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
import m7_common as m7
import m8_common as m8
from m3_common import add_common_args, boot_session
from harness import topbar_util, winutil as wu

LOG = "[p242]"


def shot(session, name):
    img = m7.capture_bgr(session)
    p = HERE / "artifacts" / f"p242_{name}.png"
    cv2.imwrite(str(p), img)
    print(f"{LOG} shot -> {p.name}")


def menu_windows(session):
    """[(rect, hwnd)] — 当前可见 #32768 菜单窗口。"""
    return [((m[0], m[1], m[2], m[3]), m[4])
            for m in topbar_util._enum_menu_windows(session.pid)]


def dismiss_all(session):
    m7.dismiss_menus(session)
    time.sleep(0.6)
    for _ in range(2):
        wu.user32.keybd_event(0x1B, 0, 0, 0)
        wu.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.2)
    time.sleep(0.4)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(),
                         default_model=HERE / "fixtures" / "Prusa.stl")
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.3%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        shot(session, "10_idle")

        # --- File 菜单 + Import 子菜单行 ---
        menu = topbar_util.open_file_menu(session)
        if menu:
            rect, mhwnd, mhmenu = menu
            items = m7.list_menu(mhmenu)
            print(f"{LOG} FILE rows={[l for _i, l in items]}")
            idx = topbar_util.find_item(mhmenu, "import")
            base = set(h for _r, h in menu_windows(session))
            topbar_util.hover_row(rect, len(items), idx)
            time.sleep(2.2)
            wins = [w for w in menu_windows(session) if w[1] not in base]
            print(f"{LOG} import submenu windows={wins}")
            if wins:
                shmenu = topbar_util.menu_hmenu(wins[0][1])
                print(f"{LOG} import submenu rows="
                      f"{[l for _i, l in m7.list_menu(shmenu)]}")
            shot(session, "11_import_submenu")
            dismiss_all(session)

        # --- 下拉菜单 Edit 子菜单行 ---
        time.sleep(1.0)
        menu = topbar_util.open_dropdown_menu(session)
        if menu:
            rect, mhwnd, mhmenu = menu
            items = m7.list_menu(mhmenu)
            print(f"{LOG} DROPDOWN rows={[l for _i, l in items]}")
            idx = next((i for i, l in items if "edit" in l.lower()), None)
            base = set(h for _r, h in menu_windows(session))
            topbar_util.hover_row(rect, len(items), idx)
            time.sleep(2.2)
            wins = [w for w in menu_windows(session) if w[1] not in base]
            print(f"{LOG} edit submenu windows={wins}")
            if wins:
                shmenu = topbar_util.menu_hmenu(wins[0][1])
                print(f"{LOG} edit submenu rows="
                      f"{[l for _i, l in m7.list_menu(shmenu)]}")
            shot(session, "12_edit_submenu")
            dismiss_all(session)

        # --- 工具条 hover 扫描（先点画布 + 长 dwell）---
        time.sleep(1.2)
        sx, sy = m7.client(session, m7.VIEWPORT_X0 + 60, 700)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(1.0)

        img = m7.capture_bgr(session)
        w = img.shape[1]
        hits = []
        for cy in (78, 84, 90, 96):
            row = []
            for cx in range(m7.VIEWPORT_X0 + 40, w - 100, 40):
                tip = m7.tooltip_text(session, cx, cy, dwell_s=1.6)
                if tip:
                    row.append((cx, tip))
                    hits.append((cx, cy, tip))
            print(f"{LOG} scan y={cy} hits={len(row)} {row[:8]}")
        print(f"{LOG} total hover hits={len(hits)}")
        shot(session, "13_toolbar_after_scan")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
