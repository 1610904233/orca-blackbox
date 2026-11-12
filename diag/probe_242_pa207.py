#!/usr/bin/env python3
# probe_242_pa207.py — characterize Calibration > Pressure advance for #207.
#
# Goal: find the dialog's controls (Start/End/Step edits, OK button), then try
# one illegal input ('abc') and record what rejection looks like (warning
# dialog texts, dialog still open, bed stays empty). No case logic here.
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

LOG = "[p242pa]"


def toplevels(session):
    skip = {session.hwnd}
    return [(cls, t, r, h) for cls, t, r, h in m7._visible_toplevels(session.pid)
            if h not in skip]


def dump_children(h, label="dialog"):
    print(f"{LOG} --- {label} hwnd=0x{h:x} class={winutil.window_class(h)} "
          f"title={winutil.window_title(h)!r} rect={winutil.window_rect(h)}")
    for t, r, ch in export_util._children_texts(h):
        cls = winutil.window_class(ch)
        vis = bool(winutil.user32.IsWindowVisible(ch))
        if vis or t.strip():
            print(f"{LOG}    {cls:14s} {t!r} rect={r}")


def real_click(x, y, hold_ms=60):
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=hold_ms)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        before = m7.model_colored_frac(session)
        print(f"{LOG} bed frac before={before:.4%}")
        menu = topbar_util.open_calibration_menu(session)
        print(f"{LOG} menu opened={bool(menu)}")
        if not menu:
            return 1
        rect, mhwnd, hm = menu
        items = topbar_util.menu_items(hm)
        n_items = len(items)
        idx = topbar_util.find_item(hm, "pressure advance")
        print(f"{LOG} pressure advance idx={idx} rows={[lb for _i, lb, _s in items]}")
        if idx is None:
            return 1
        cx = (rect[0] + rect[2]) // 2
        dlg = None
        for y in topbar_util.submenu_row_candidates(rect, n_items, idx):
            print(f"{LOG} click row candidate y={y}")
            real_click(cx, y)
            time.sleep(1.5)
            wins = toplevels(session)
            print(f"{LOG} toplevels={[(c, t[:40], r) for c, t, r, h in wins]}")
            if wins:
                dlg = wins[0]
                break
        if not dlg:
            print(f"{LOG} no dialog opened")
            return 1
        dump_children(dlg[3], "pressure-advance dialog")

        # locate the first numeric-looking Edit (largest / topmost edit)
        kids = export_util._children_texts(dlg[3])
        edits = [(t, r, ch) for t, r, ch in kids
                 if winutil.window_class(ch) == "Edit"
                 and winutil.user32.IsWindowVisible(ch)
                 and (r[2] - r[0]) > 10 and (r[3] - r[1]) > 8]
        print(f"{LOG} visible edits={[(t, r) for t, r, ch in edits]}")

        # find an OK-ish button by text (class-agnostic, m8x_198 lesson)
        btns = [(t, r, ch) for t, r, ch in kids
                if t.strip().lower() in ("ok", "确定", "confirm", "apply")
                and winutil.user32.IsWindowVisible(ch)]
        print(f"{LOG} ok buttons={[(t, r) for t, r, ch in btns]}")
        if edits and btns:
            _t, er, eh = edits[0]
            ex, ey = (er[0] + er[2]) // 2, (er[1] + er[3]) // 2
            real_click(ex, ey)
            time.sleep(0.4)
            winutil.msg_text(eh, "abc")
            time.sleep(0.5)
            print(f"{LOG} start readback={winutil.edit_text(eh)!r}")
            _bt, br, _bh = btns[0]
            real_click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
            time.sleep(2.0)
            wins = toplevels(session)
            print(f"{LOG} after OK toplevels={[(c, t[:60], r) for c, t, r, h in wins]}")
            for cls, t, r, h in wins:
                dump_children(h, "after-OK window")
            print(f"{LOG} PA dialog still visible="
                  f"{bool(winutil.user32.IsWindowVisible(dlg[3]))}")
            after = m7.model_colored_frac(session)
            print(f"{LOG} bed frac after={after:.4%}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
