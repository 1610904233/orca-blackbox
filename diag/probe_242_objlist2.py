#!/usr/bin/env python3
# probe_242_objlist2.py — Process 面板「Objects」标签页：行点击选中 + 右键菜单
# 这是绕开画布选中的最后一条按钮面路径（m8x_152 的「先指定模型耗材」步骤）。
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
import m8_common as m8
from harness import export_util, winutil
from m3_common import PRUSA_STL, add_common_args, boot_session

LOG = "[p242ol2]"
WM_CLOSE = 0x0010


def dismiss_strays(session):
    for _ in range(10):
        dlg = next(((c, t, r, h) for c, t, r, h in m7._visible_toplevels(session.pid)
                    if c == "#32770"), None)
        if not dlg:
            return
        print(f"{LOG} dismiss stray dialog {dlg[1]!r}")
        winutil.user32.SendMessageW(dlg[3], WM_CLOSE, 0, 0)
        time.sleep(1.0)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=PRUSA_STL)
    args = ap.parse_args()
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, _ = m8.wait_arrival(session)
        m7.ensure_maximized(session)
        time.sleep(1.5)
        dismiss_strays(session)
        # 1) 找 Objects 标签（Process 面板底部: Process | Global | Objects | Advanced）
        rows = export_util._children_texts(session.hwnd)
        tab = next(((t, r, h) for t, r, h in rows
                    if t.strip() == "Objects" and r[1] > 500 and r[0] < 430), None)
        if tab:
            t, r, _h = tab
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
        else:
            # 自绘标签：按 Process/Advanced 的几何夹出 Objects 位置
            proc = next(((t, r) for t, r, h in rows if t.strip() == "Process"), None)
            adv = next(((t, r) for t, r, h in rows if t.strip() == "Advanced"), None)
            print(f"{LOG} geometric: process={proc and proc[1]} adv={adv and adv[1]}")
            if not (proc and adv):
                return 1
            cx = (proc[1][2] + adv[1][0]) // 2 + 20
            cy = (proc[1][1] + proc[1][3]) // 2
        print(f"{LOG} clicking Objects tab @({cx},{cy})")
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.3)
        winutil.real_click_screen(cx, cy)
        time.sleep(1.5)
        # 2) dump 行
        rows2 = export_util._children_texts(session.hwnd)
        obj_rows = [(t2, r2, h2) for t2, r2, h2 in rows2
                    if t2.strip() and r2[0] < 430 and r2[1] > 500
                    and ("prusa" in t2.lower() or "untitled" in t2.lower())]
        print(f"{LOG} object rows = {[(t2, r2) for t2, r2, _ in obj_rows]}")
        print(f"{LOG} sidebar sample: {[(t2[:18], r2) for t2, r2, _ in rows2 if t2.strip() and r2[0] < 430 and 500 < r2[1] < 900][:10]}")
        if not obj_rows:
            return 1
        t2, r2, _h2 = obj_rows[0]
        cx, cy = (r2[0] + r2[2]) // 2, (r2[1] + r2[3]) // 2
        print(f"{LOG} click object row {t2!r} @({cx},{cy})")
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.3)
        winutil.real_click_screen(cx, cy)
        time.sleep(1.2)
        print(f"{LOG} selected = {m7.object_selected(session)} "
              f"info={m7.object_info_text(session)[:50]!r}")
        # 3) 右键行
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.2)
        winutil.real_right_click_screen(cx, cy)
        time.sleep(1.2)
        menus = m7.topbar_util._enum_menu_windows(session.pid)
        print(f"{LOG} row right-click menus={len(menus)}")
        if menus:
            hmenu = m7.topbar_util.menu_hmenu(menus[0][4])
            print(f"{LOG} menu rows={[l for _i, l in m7.list_menu(hmenu)]}")
        m7.dismiss_menus(session)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
