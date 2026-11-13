#!/usr/bin/env python3
# probe_242_pa222.py — PA Pattern (V-shape) control states for #222.
#
# Feishu #222 expects: defaults 0/0.08/0.005, Print numbers checked but
# disabled, Accelerations/Speeds fillable (empty). Probe_c's screenshot showed
# the Print numbers box UNCHECKED for PA Pattern; this probe records the API
# enable states plus the owner-drawn checkbox pixel state and saves a shot.
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
import numpy as np

import m7_common as m7
from m3_common import add_common_args, boot_session
from harness import export_util, topbar_util, winutil

LOG = "[p242pa222]"
ART = HERE / "artifacts"


def real_click(x, y):
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def pa_dialog(session):
    for cls, t, r, h in m7._visible_toplevels(session.pid):
        if cls == "#32770" and "pa calibration" in (t or "").lower():
            return (cls, t, r, h)
    return None


def open_pa(session):
    menu = topbar_util.open_calibration_menu(session)
    if not menu:
        return None
    rect, _m, hm = menu
    idx = topbar_util.find_item(hm, "pressure advance")
    cx = (rect[0] + rect[2]) // 2
    for y in topbar_util.submenu_row_candidates(rect, len(topbar_util.menu_items(hm)), idx):
        real_click(cx, y)
        time.sleep(1.5)
        d = pa_dialog(session)
        if d:
            return d
    return None


def kids(dlg):
    return export_util._children_texts(dlg[3])


def label_rect(dlg, text):
    return next((r for t, r, h in kids(dlg) if t.strip() == text), None)


def radio_click(dlg, label):
    lab = label_rect(dlg, label)
    if not lab:
        return False
    ly = (lab[1] + lab[3]) // 2
    circles = [r for t, r, h in kids(dlg)
               if not t.strip()
               and winutil.window_class(h) in ("Static", "Button")
               and abs(((r[1] + r[3]) // 2) - ly) <= 12
               and lab[0] - 40 < r[0] < lab[0]
               and (r[2] - r[0]) <= 30]
    if circles:
        r = circles[0]
        real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    else:
        real_click((lab[0] + lab[2]) // 2, ly)
    time.sleep(1.5)
    return True


def edit_by_label(dlg, label):
    lab = next(((t, r) for t, r, h in kids(dlg)
                if t.strip().lower().startswith(label)), None)
    if not lab:
        return None
    ly = (lab[1][1] + lab[1][3]) // 2
    for t, r, h in kids(dlg):
        if winutil.window_class(h) == "Edit" and \
                abs(((r[1] + r[3]) // 2) - ly) <= 14 and \
                winutil.user32.IsWindowVisible(h):
            return h
    return None


def pn_btn(dlg):
    lab = label_rect(dlg, "Print numbers")
    if not lab:
        return None
    ly = (lab[1] + lab[3]) // 2
    return next(((r, h) for t, r, h in kids(dlg)
                 if winutil.window_class(h) == "Button"
                 and abs(((r[1] + r[3]) // 2) - ly) <= 14
                 and winutil.user32.IsWindowVisible(h)), None)


def pn_visual(dlg):
    btn = pn_btn(dlg)
    if not btn:
        return -1, False
    br, bh = btn
    cx0, cy0 = winutil.client_to_screen(dlg[3], 0, 0)
    w, h, bgra = winutil.capture_window(dlg[3])
    img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
    x0, y0 = max(0, br[0] - cx0), max(0, br[1] - cy0)
    x1, y1 = min(w, br[2] - cx0), min(h, br[3] - cy0)
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return -1, bool(winutil.user32.IsWindowEnabled(bh))
    teal = int(((crop[:, :, 0] > 100) & (crop[:, :, 1] > 100)
                & (crop[:, :, 2] < 120)).sum())
    return teal, bool(winutil.user32.IsWindowEnabled(bh))


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        dlg = open_pa(session)
        print(f"{LOG} dialog={bool(dlg)}")
        if not dlg:
            return 1
        radio_click(dlg, "PA Pattern")
        s = edit_by_label(dlg, "start pa")
        e = edit_by_label(dlg, "end pa")
        st = edit_by_label(dlg, "pa step")
        acc = edit_by_label(dlg, "accelerations")
        spd = edit_by_label(dlg, "speeds")
        teal, pn_en = pn_visual(dlg)
        print(f"{LOG} start/end/step="
              f"{[winutil.edit_text(h).strip() for h in (s, e, st)]}")
        print(f"{LOG} print numbers teal={teal} enabled={pn_en}")
        print(f"{LOG} accel enabled={bool(winutil.user32.IsWindowEnabled(acc))} "
              f"text={winutil.edit_text(acc)!r}; "
              f"speed enabled={bool(winutil.user32.IsWindowEnabled(spd))} "
              f"text={winutil.edit_text(spd)!r}")
        w, h, bgra = winutil.capture_window(dlg[3])
        img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
        p = ART / "p242_pa222_pattern.png"
        cv2.imwrite(str(p), img)
        print(f"{LOG} shot -> {p.name}")
        winutil.user32.SetForegroundWindow(dlg[3])
        time.sleep(0.3)
        winutil.user32.keybd_event(0x1B, 0, 0, 0)
        winutil.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.5)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
