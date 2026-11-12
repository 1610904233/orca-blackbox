#!/usr/bin/env python3
# probe_242_yolo217c.py — handle the 'Creating a new project: unsaved
# changes' prompt that appears when loading YOLO (perfectionist) after
# deleting the recommended model.
#
# m8x_217 RED: the perf click raised that modal prompt and every later click
# was swallowed. This probe dumps the prompt buttons, clicks the discard
# option, then loads perf and saves its 3mf for the exact 16 names.
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

LOG = "[p242y217c]"
ART = HERE / "artifacts"
user32 = winutil.user32
PROMPT = "creating a new project"


def real_click(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def key_combo(*vks):
    for v in vks[:-1]:
        user32.keybd_event(v, 0, 0, 0)
    user32.keybd_event(vks[-1], 0, 0, 0)
    time.sleep(0.08)
    user32.keybd_event(vks[-1], 0, 2, 0)
    for v in reversed(vks[:-1]):
        user32.keybd_event(v, 0, 2, 0)
    time.sleep(0.5)


def dialogs(session):
    return [(c, t, r, h) for c, t, r, h in m7._visible_toplevels(session.pid)
            if c == "#32770"]


def dump_prompt(session):
    for c, t, r, h in dialogs(session):
        if PROMPT in (t or "").lower():
            print(f"{LOG} prompt {t!r} rect={r}")
            for bt, br, bh in export_util._children_texts(h):
                if user32.IsWindowVisible(bh):
                    print(f"{LOG}   {winutil.window_class(bh):10s} {bt!r} {br}")
            return (c, t, r, h)
    return None


def click_prompt_discard(session):
    d = dump_prompt(session)
    if not d:
        return None
    for bt, br, bh in export_util._children_texts(d[3]):
        low = bt.strip().lower()
        if user32.IsWindowVisible(bh) and any(
                k in low for k in ("don't save", "dont save", "discard",
                                   "no", "否", "不保存")):
            print(f"{LOG} click prompt button {bt!r}")
            real_click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
            time.sleep(2.0)
            return bt
    # fallback: dump and press ESC
    print(f"{LOG} no discard word found; ESC")
    user32.SetForegroundWindow(d[3])
    time.sleep(0.3)
    key_combo(0x1B)
    time.sleep(1.0)
    return "ESC"


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
        time.sleep(2.0)
        f = m7.model_colored_frac(session)
        print(f"{LOG} click {want!r} y={y} frac={f:.4%} "
              f"dialogs={[(c, t) for c, t, r, h in dialogs(session)]}")
        if f > 0.003:
            return True
    return False


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


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        base = m7.model_colored_frac(session)
        print(f"{LOG} base frac={base:.4%}")

        sub = open_flow_submenu(session)
        click_row(session, sub[0], sub[2], "yolo (recommended)")
        print(f"{LOG} rec frac={m7.model_colored_frac(session):.4%}")

        user32.SetForegroundWindow(session.hwnd)
        time.sleep(0.4)
        key_combo(0x11, 0x41)
        key_combo(0x2E)
        time.sleep(2.0)
        print(f"{LOG} after clear frac={m7.model_colored_frac(session):.4%}")

        sub = open_flow_submenu(session)
        click_row(session, sub[0], sub[2], "yolo (perfectionist")
        time.sleep(1.0)
        print(f"{LOG} dialogs after perf click="
              f"{[(c, t) for c, t, r, h in dialogs(session)]}")
        bt = click_prompt_discard(session)
        print(f"{LOG} prompt button clicked={bt!r}")
        end = time.monotonic() + 30
        while time.monotonic() < end:
            f = m7.model_colored_frac(session)
            if f > max(base + 0.003, base * 2):
                break
            time.sleep(1.0)
        print(f"{LOG} after discard frac={m7.model_colored_frac(session):.4%} "
              f"dialogs={[(c, t) for c, t, r, h in dialogs(session)]}")

        p = ART / "p242_217_perf.3mf"
        p.unlink(missing_ok=True)
        saved = m7.save_project_as(session, p)
        names = names_from_3mf(p)
        print(f"{LOG} perf saved={saved} count={len(names)} names={names}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
