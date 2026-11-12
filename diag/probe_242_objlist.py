#!/usr/bin/env python3
# probe_242_objlist.py — 左侧「对象列表」行点击/右键是否可用（绕开画布选中的
# 最后一条路）：dump 侧栏控件找模型行 → 点击行 → 信息面板出现? → 右键行 →
# dump 菜单（是否有 Change Filament）
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

LOG = "[p242ol]"


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=PRUSA_STL)
    args = ap.parse_args()
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, _ = m8.wait_arrival(session)
        m7.ensure_maximized(session)
        time.sleep(2.0)
        # 1) 枚举侧栏：找模型名/对象树相关控件
        rows = export_util._children_texts(session.hwnd)
        hits = [(t, r, h) for t, r, h in rows
                if t.strip() and any(k in t.lower() for k in
                                     ("prusa", "object", "untitled"))]
        print(f"{LOG} sidebar candidates: {len(hits)}")
        for t, r, h in hits[:12]:
            print(f"{LOG}   {t[:40]!r} rect={r} class={winutil.window_class(h)!r}")
        # 2) 点击模型名那一行（点在该行中部）
        name_row = next((hx for hx in hits if "prusa" in hx[0].lower()), None)
        if not name_row:
            print(f"{LOG} no model row found — dump all texts with y>500:")
            for t, r, h in rows:
                if r[1] > 500 and t.strip():
                    print(f"{LOG}   {t[:30]!r} {r}")
            return 1
        t, r, h = name_row
        cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
        print(f"{LOG} click model row {t!r} @({cx},{cy})")
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.3)
        winutil.real_click_screen(cx, cy)
        time.sleep(1.2)
        print(f"{LOG} selected after row click = {m7.object_selected(session)} "
              f"info={m7.object_info_text(session)[:50]!r}")
        # 3) 右键该行 -> 菜单
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.2)
        winutil.real_right_click_screen(cx, cy)
        time.sleep(1.2)
        menus = m7.topbar_util._enum_menu_windows(session.pid)
        print(f"{LOG} row right-click menus={len(menus)}")
        if menus:
            hwnd = menus[0][4]
            hmenu = m7.topbar_util.menu_hmenu(hwnd)
            print(f"{LOG} menu rows={[l for _i, l in m7.list_menu(hmenu)]}")
            m7.dismiss_menus(session)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
