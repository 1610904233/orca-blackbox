#!/usr/bin/env python3
# probe_242_yolo217.py — Calibration > Flow rate > YOLO (recommended /
# perfectionist) for #217.
#
# Needs: no parameter dialog, 11 vs 16 blocks, exact object names from the
# saved 3mf, and a reliable way to clear the bed between the two models
# (Ctrl+N new project / Ctrl+A+Del / Ctrl+D). Also handles a possible STEP
# import dialog like #213.
import argparse
import re
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7
from m3_common import add_common_args, boot_session
from harness import export_util, topbar_util, winutil

LOG = "[p242y217]"
ART = HERE / "artifacts"
user32 = winutil.user32


def real_click(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def dialogs(session):
    return [(c, t, r, h) for c, t, r, h in m7._visible_toplevels(session.pid)
            if c == "#32770"]


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
                print(f"{LOG} submenu rect={m[:4]} rows={labels}")
                return (m[:4], m[4], shm)
    return None


def click_submenu_row(session, sub_rect, shm, want):
    items = topbar_util.menu_items(shm)
    idx = next((i for i, l, _s in items if want.lower() in l.lower()), None)
    if idx is None:
        print(f"{LOG} row {want!r} not found")
        return False
    n = len(items)
    x = (sub_rect[0] + sub_rect[2]) // 2
    for y in topbar_util.submenu_row_candidates(sub_rect, n, idx):
        for attempt in (1, 2):
            print(f"{LOG} click {want!r} y={y} attempt={attempt}")
            real_click(x, y)
            time.sleep(1.8)
            f = m7.model_colored_frac(session)
            print(f"{LOG}   frac={f:.4%} dialogs={[(c, t) for c, t, r, h in dialogs(session)]}")
            if f > 0.003:
                return True
    return False


def accept_step(session):
    for c, t, r, h in dialogs(session):
        if "step file import" in (t or "").lower():
            for bt, br, bh in export_util._children_texts(h):
                if bt.strip().lower() == "ok" and user32.IsWindowVisible(bh):
                    real_click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
                    print(f"{LOG} STEP import accepted")
                    return True
    return False


def wait_model(session, base, timeout_s=90):
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        accept_step(session)
        f = m7.model_colored_frac(session)
        if f > max(base + 0.003, base * 2):
            return f
        time.sleep(1.0)
    return m7.model_colored_frac(session)


def names_from_3mf(path):
    names = []
    if not path.exists():
        return names
    with zipfile.ZipFile(path) as z:
        cfg = z.read("Metadata/model_settings.config").decode(
            "utf-8", "replace")
    for obj in re.finditer(r"<object\b[^>]*>(.*?)</object>", cfg, re.S):
        mm = re.search(r'<metadata key="name" value="([^"]*)"', obj.group(1))
        if mm:
            names.append(mm.group(1))
    return names


def key_combo(*vks):
    for v in vks[:-1]:
        user32.keybd_event(v, 0, 0, 0)
    user32.keybd_event(vks[-1], 0, 0, 0)
    time.sleep(0.08)
    user32.keybd_event(vks[-1], 0, 2, 0)
    for v in reversed(vks[:-1]):
        user32.keybd_event(v, 0, 2, 0)
    time.sleep(0.4)


def clear_bed(session, base):
    """Try Ctrl+N (new project), then Ctrl+A+Del, then Ctrl+D."""
    user32.SetForegroundWindow(session.hwnd)
    time.sleep(0.4)
    for label, fn in (
        ("Ctrl+N", lambda: key_combo(0x11, 0x4E)),
        ("Ctrl+A+Del", lambda: (key_combo(0x11, 0x41), key_combo(0x2E))),
        ("Ctrl+D", lambda: key_combo(0x11, 0x44)),
    ):
        fn()
        time.sleep(2.0)
        for c, t, r, h in dialogs(session):
            print(f"{LOG} {label}: dialog {t!r}")
        f = m7.model_colored_frac(session)
        print(f"{LOG} {label}: frac={f:.4%}")
        if f <= base + 0.003:
            return label
    return None


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        base = m7.model_colored_frac(session)
        print(f"{LOG} base frac={base:.4%}")

        # ---- YOLO recommended ----
        sub = open_flow_submenu(session)
        if not sub:
            return 1
        ok = click_submenu_row(session, sub[0], sub[2], "yolo (recommended)")
        f1 = wait_model(session, base)
        print(f"{LOG} rec loaded={ok} frac={f1:.4%} dialogs={[(c, t) for c, t, r, h in dialogs(session)]}")
        p1 = ART / "p242_217_rec.3mf"
        p1.unlink(missing_ok=True)
        saved1 = m7.save_project_as(session, p1)
        n1 = names_from_3mf(p1)
        print(f"{LOG} rec saved={saved1} count={len(n1)} names={n1}")

        cleared = clear_bed(session, base)
        print(f"{LOG} cleared by={cleared} frac={m7.model_colored_frac(session):.4%}")

        # ---- YOLO perfectionist ----
        sub = open_flow_submenu(session)
        if not sub:
            return 1
        ok2 = click_submenu_row(session, sub[0], sub[2],
                                "yolo (perfectionist")
        f2 = wait_model(session, base)
        print(f"{LOG} perf loaded={ok2} frac={f2:.4%}")
        p2 = ART / "p242_217_perf.3mf"
        p2.unlink(missing_ok=True)
        saved2 = m7.save_project_as(session, p2)
        n2 = names_from_3mf(p2)
        print(f"{LOG} perf saved={saved2} count={len(n2)} names={n2}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
