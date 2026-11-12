#!/usr/bin/env python3
# probe_242_maxflow213b.py — why does Max volumetric OK not close the dialog?
#
# m8x_213: defaults read fine, but two OK clicks left 'Max volumetric speed
# test' open and the bed fraction only moved 0.064% -> 0.123%. This probe
# clicks OK and dumps every #32770 (title + OCR body) plus the frac over
# time, so we can see a validation warning / a second dialog / slow load.
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
from harness import export_util, ocr_util, topbar_util, winutil

LOG = "[p242m213b]"
TITLE = "max volumetric speed test"


def real_click(x, y):
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def dialogs(session):
    return [(c, t, r, h) for c, t, r, h in m7._visible_toplevels(session.pid)
            if c == "#32770"]


def dump(session, label):
    print(f"{LOG} --- {label} frac={m7.model_colored_frac(session):.4%}")
    for c, t, r, h in dialogs(session):
        print(f"{LOG}   #32770 {t!r} rect={r}")
        try:
            body = ocr_util.ocr_hwnd(h, scale=2)
        except Exception as exc:
            body = f"<ocr failed: {exc}>"
        print(f"{LOG}     body={body!r}")
        for bt, br, bh in export_util._children_texts(h):
            if bt.strip() and winutil.user32.IsWindowVisible(bh):
                print(f"{LOG}     child {winutil.window_class(bh)} {bt!r}")


def open_maxflow(session):
    menu = topbar_util.open_calibration_menu(session)
    if not menu:
        return None
    rect, _m, hm = menu
    idx = topbar_util.find_item(hm, "max flowrate")
    cx = (rect[0] + rect[2]) // 2
    for y in topbar_util.submenu_row_candidates(rect, len(topbar_util.menu_items(hm)), idx):
        real_click(cx, y)
        time.sleep(1.5)
        for c, t, r, h in dialogs(session):
            if TITLE in (t or "").lower():
                return (c, t, r, h)
    return None


def ok_button(dlg):
    for t, r, h in export_util._children_texts(dlg[3]):
        if t.strip().lower() == "ok" and winutil.user32.IsWindowVisible(h):
            return h, r
    return None, None


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        frac0 = m7.model_colored_frac(session)
        print(f"{LOG} frac0={frac0:.4%}")
        dlg = open_maxflow(session)
        print(f"{LOG} dialog={bool(dlg)}")
        if not dlg:
            return 1
        dump(session, "before OK")
        h, r = ok_button(dlg)
        print(f"{LOG} ok hwnd={h} rect={r}")
        for attempt in (1, 2, 3):
            real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            time.sleep(2.0)
            dump(session, f"after OK click {attempt}")
        for i in range(6):
            time.sleep(3.0)
            print(f"{LOG} t+{(i + 1) * 3}s frac={m7.model_colored_frac(session):.4%} "
                  f"dialogs={[(t, r) for c, t, r, h in dialogs(session)]}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
