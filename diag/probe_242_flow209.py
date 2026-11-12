#!/usr/bin/env python3
# probe_242_flow209.py — Calibration > Flow rate > Pass 1 (#209, 粗调).
#
# Needs: (a) hover Flow rate to open its submenu and real-click "Pass 1"
# with no parameter dialog; (b) 9 blocks load on the bed; (c) object list
# names match flowrate_0/5/10/15/20 + flowrate_m5/m10/m15/m20.
# This probe exercises (a)(b) and dumps the Objects tab's OCR band for (c).
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
from harness import export_util, mix_dialog_util as mdu, topbar_util, winutil

LOG = "[p242f209]"
user32 = winutil.user32


def real_click(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def menu_wins(session):
    return topbar_util._enum_menu_windows(session.pid)


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
        for m in menu_wins(session):
            if m[4] in known:
                continue
            known.add(m[4])
            shm = topbar_util.menu_hmenu(m[4])
            labels = [l.lower() for _i, l, _s in topbar_util.menu_items(shm)]
            if any("pass 1" in l for l in labels):
                print(f"{LOG} flow submenu rect={m[:4]} rows={labels}")
                return (m[:4], m[4], shm)
    return None


def click_row0(session, sub_rect, shm, frac0):
    n = len(topbar_util.menu_items(shm))
    x = (sub_rect[0] + sub_rect[2]) // 2
    for y in topbar_util.submenu_row_candidates(sub_rect, n, 0):
        for attempt in (1, 2):
            print(f"{LOG} click Pass1 candidate y={y} attempt={attempt}")
            real_click(x, y)
            time.sleep(1.8)
            f = m7.model_colored_frac(session)
            print(f"{LOG}   frac={f:.4%} dialogs="
                  f"{[(c, t) for c, t, r, h in m7._visible_toplevels(session.pid) if c == '#32770']}")
            if f > frac0 + 0.005:
                return True, y, f
    return False, None, m7.model_colored_frac(session)


def ocr_band(session, y0, y1, x0=0, x1=430, scale=3):
    from harness.anchors import capture_bgr as _cap
    img = _cap(session)
    crop = img[max(0, y0):y1, x0:x1]
    if crop.size == 0:
        return []
    return [(w[0], w[1] + x0, w[2] + y0, w[3], w[4])
            for w in mdu.ocr_words_img(crop, scale=scale)]


def dump_objects(session):
    rows = export_util._children_texts(session.hwnd)
    proc = next(((t, r) for t, r, h in rows if t.strip() == "Process"), None)
    adv = next(((t, r) for t, r, h in rows if t.strip() == "Advanced"), None)
    print(f"{LOG} process={proc and proc[1]} advanced={adv and adv[1]}")
    if not proc:
        print(f"{LOG} frame texts={[t for t, r, h in rows if t.strip()][:30]}")
        return
    y0, y1 = proc[1][1] - 8, proc[1][3] + 8
    band = ocr_band(session, y0, y1, scale=3)
    print(f"{LOG} tab band={[(w[0], w[1], w[2]) for w in band]}")
    objw = next((w for w in band if "bject" in w[0].lower()), None)
    if not objw:
        print(f"{LOG} no Objects tab word")
        return
    cx = objw[1] + objw[3] // 2
    cy = objw[2] + objw[4] // 2
    print(f"{LOG} click Objects tab @({cx},{cy})")
    real_click(cx, cy)
    time.sleep(1.5)
    words = ocr_band(session, y1 + 2, 800, scale=4)
    # group by y
    lines = {}
    for t, x, y, w, h in words:
        key = next((k for k in lines if abs(k - y) <= 10), y)
        lines.setdefault(key, []).append((x, t))
    for k in sorted(lines):
        print(f"{LOG}   y={k}: {' '.join(t for _x, t in sorted(lines[k]))}")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        frac0 = m7.model_colored_frac(session)
        print(f"{LOG} bed frac0={frac0:.4%}")
        ok = False
        y = None
        f = frac0
        for attempt in range(3):
            print(f"{LOG} --- attempt {attempt + 1}")
            sub = open_flow_submenu(session)
            if not sub:
                print(f"{LOG} no flow submenu")
                break
            ok, y, f = click_row0(session, sub[0], sub[2], frac0)
            if ok:
                break
            m7.dismiss_menus(session)
            time.sleep(1.0)
        print(f"{LOG} Pass1 loaded={ok} y={y} frac={f:.4%}")
        if ok:
            dump_objects(session)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
