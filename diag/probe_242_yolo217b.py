#!/usr/bin/env python3
# probe_242_yolo217b.py — find a working bed-clear channel between the two
# YOLO models (#217).
#
# probe_242_yolo217: YOLO rec = 11 objects (names confirmed). Ctrl+N raised
# 'Creating a new project: unsaved changes' and every later key went to that
# modal dialog, so the second model never loaded. This probe tries
# Ctrl+A+Del first, then Ctrl+D, then Ctrl+N with the save-prompt handled.
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

LOG = "[p242y217b]"
user32 = winutil.user32


def real_click(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def dialogs(session):
    return [(c, t, r, h) for c, t, r, h in m7._visible_toplevels(session.pid)
            if c == "#32770"]


def dump_dialogs(session):
    for c, t, r, h in dialogs(session):
        print(f"{LOG} dialog {t!r} rect={r}")
        for bt, br, bh in export_util._children_texts(h):
            if user32.IsWindowVisible(bh) and (bt.strip() or
                                               winutil.window_class(bh) == "Button"):
                print(f"{LOG}   {winutil.window_class(bh):10s} {bt!r} {br}")


def key_combo(*vks):
    for v in vks[:-1]:
        user32.keybd_event(v, 0, 0, 0)
    user32.keybd_event(vks[-1], 0, 0, 0)
    time.sleep(0.08)
    user32.keybd_event(vks[-1], 0, 2, 0)
    for v in reversed(vks[:-1]):
        user32.keybd_event(v, 0, 2, 0)
    time.sleep(0.5)


def open_flow_submenu(session):
    menu = topbar_util.open_calibration_menu(session)
    if not menu:
        return None
    rect, mhwnd, hm = menu
    n = len(topbar_util.menu_items(hm))
    idx = topbar_util.find_item(hm, "flow rate")
    known = {mhwnd}
    cx = (rect[0] + rect[2]) // 2
    for y in topbar_util.submenu_row_candidates(rect, n, idx):
        user32.SetCursorPos(cx, y)
        time.sleep(0.7)
        for m in topbar_util._enum_menu_windows(session.pid):
            if m[4] in known:
                continue
            known.add(m[4])
            shm = topbar_util.menu_hmenu(m[4])
            labels = [l.lower() for _i, l, _s in topbar_util.menu_items(shm)]
            if any("pass 1" in l for l in labels):
                return (m[:4], m[4], shm)
    return None


def click_row(session, sub_rect, shm, want):
    items = topbar_util.menu_items(shm)
    idx = next((i for i, l, _s in items if want.lower() in l.lower()), None)
    if idx is None:
        return False
    x = (sub_rect[0] + sub_rect[2]) // 2
    for y in topbar_util.submenu_row_candidates(sub_rect, len(items), idx):
        real_click(x, y)
        time.sleep(1.8)
        f = m7.model_colored_frac(session)
        print(f"{LOG} click {want!r} y={y} frac={f:.4%}")
        if f > 0.003:
            return True
    return False


def try_clear(session, base, label, fn):
    print(f"{LOG} === clear channel: {label}")
    user32.SetForegroundWindow(session.hwnd)
    time.sleep(0.4)
    fn()
    time.sleep(2.0)
    dump_dialogs(session)
    f = m7.model_colored_frac(session)
    print(f"{LOG} {label}: frac={f:.4%}")
    return f <= base + 0.003


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        base = m7.model_colored_frac(session)
        print(f"{LOG} base frac={base:.4%}")
        sub = open_flow_submenu(session)
        if not sub:
            return 1
        click_row(session, sub[0], sub[2], "yolo (recommended)")
        print(f"{LOG} rec frac={m7.model_colored_frac(session):.4%}")

        if try_clear(session, base, "Ctrl+A+Del",
                     lambda: (key_combo(0x11, 0x41), key_combo(0x2E))):
            print(f"{LOG} CLEARED by Ctrl+A+Del")
            return 0
        if try_clear(session, base, "Ctrl+D", lambda: key_combo(0x11, 0x44)):
            print(f"{LOG} CLEARED by Ctrl+D")
            return 0

        print(f"{LOG} === clear channel: Ctrl+N + handle prompt")
        user32.SetForegroundWindow(session.hwnd)
        time.sleep(0.4)
        key_combo(0x11, 0x4E)
        time.sleep(2.0)
        dump_dialogs(session)
        for c, t, r, h in dialogs(session):
            for bt, br, bh in export_util._children_texts(h):
                low = bt.strip().lower()
                if user32.IsWindowVisible(bh) and any(
                        k in low for k in ("don't save", "discard", "no",
                                           "否", "不保存")):
                    print(f"{LOG} clicking prompt button {bt!r}")
                    real_click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
                    time.sleep(2.0)
                    break
        dump_dialogs(session)
        print(f"{LOG} after Ctrl+N+discard frac={m7.model_colored_frac(session):.4%}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
