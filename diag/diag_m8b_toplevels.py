#!/usr/bin/env python3
"""diag_m8b_toplevels.py — pin down what (if anything) appears after a REAL
click on slot 2's color picker. 09-17/18: wait_toplevel(#32770) catches
nothing, so enumerate EVERY toplevel of the app pid for 10s and screenshot
new arrivals. Boot-only (no fixture assertions) — speed over everything.

    C:\\Python311\\python.exe diag\\diag_m8b_toplevels.py
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

import cv2  # noqa: E402

from m3_common import add_common_args, boot_session  # noqa: E402
import m8_common as m8  # noqa: E402
from harness import winutil, mixing_util  # noqa: E402
from harness.shot_archive import _save  # noqa: E402

OUT = HERE / "artifacts" / "m8b_diag"


def snapshot_toplevels(pid):
    out = {}
    try:
        for cls, txt, rect, hwnd in mixing_util.toplevel(pid):
            out[hwnd] = (cls, txt, rect)
    except Exception as e:  # noqa: BLE001
        print(f"[d] toplevel enum error: {e!r}", flush=True)
    return out


def main() -> int:
    ap = __import__("argparse").ArgumentParser()
    add_common_args(ap)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    session = boot_session(args, model=HERE / "fixtures" / "mixed_filament_test.3mf")
    try:
        slots = m8.filament_slots(session)
        print(f"[d] slots: {[(s['slot'], s.get('combo')) for s in slots]}", flush=True)
        hit = next((s for s in slots if s["slot"] == 2), None)
        if not hit or not hit.get("picker"):
            print("[d] NO slot2 picker rect", flush=True)
            return 1
        print(f"[d] slot2 picker rect: {hit['picker']}", flush=True)

        before = snapshot_toplevels(session.pid)
        px = (hit["picker"][0] + hit["picker"][2]) // 2
        py = (hit["picker"][1] + hit["picker"][3]) // 2
        sx, sy = winutil.client_to_screen(session.hwnd, px, py)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        winutil.real_click_screen(sx, sy)
        print(f"[d] clicked picker at screen ({sx},{sy})", flush=True)

        seen = set(before)
        t0 = time.time()
        n_shot = 0
        while time.time() - t0 < 10.0:
            time.sleep(0.5)
            now = snapshot_toplevels(session.pid)
            for hwnd, (cls, txt, rect) in now.items():
                if hwnd not in seen:
                    seen.add(hwnd)
                    n_shot += 1
                    p = OUT / f"new_{n_shot}_{cls.strip('#')}.png"
                    _save(hwnd, p)
                    print(f"[d] NEW toplevel hwnd=0x{hwnd:x} class={cls!r} "
                          f"title={txt[:60]!r} rect={rect} shot={p.name}",
                          flush=True)
        print(f"[d] done; toplevels now: "
              f"{[(c, t[:30]) for c, t, _r in snapshot_toplevels(session.pid).values()]}",
              flush=True)
        return 0
    finally:
        session.close()
        print("[d] app closed", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
