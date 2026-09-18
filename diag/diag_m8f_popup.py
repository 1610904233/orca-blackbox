#!/usr/bin/env python3
"""diag_m8f_popup.py — pin down the nozzle Flow dropdown: what class of
window opens, its geometry/children, and which row click flips the value.

    C:\\Python311\\python.exe diag\\diag_m8f_popup.py
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import add_common_args, boot_session  # noqa: E402
import m8_common as m8  # noqa: E402
from harness import winutil, export_util, mixing_util  # noqa: E402
from harness.shot_archive import _save  # noqa: E402

OUT = HERE / "artifacts" / "m8f_diag"


def toplevels(pid):
    try:
        return {h: (c, t, r) for c, t, r, h in mixing_util.toplevel(pid)}
    except Exception as e:  # noqa: BLE001
        print(f"[d] enum err {e!r}", flush=True)
        return {}


def main() -> int:
    ap = __import__("argparse").ArgumentParser()
    add_common_args(ap)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    session = boot_session(args, model=HERE / "fixtures" / "mixed_filament_test.3mf")
    try:
        reads = m8.nozzle_reads(session)
        print(f"[d] reads: {reads}", flush=True)
        rect = reads["flow_rect"]
        cx, cy = rect[2] - 12, (rect[1] + rect[3]) // 2
        sx, sy = winutil.client_to_screen(session.hwnd, cx, cy)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.2)
        before = {session.hwnd}
        new = {}
        for h, info in toplevels(session.pid).items():
            if h not in before and h != session.hwnd:
                new[h] = info
        print(f"[d] popups after combo click: {new}", flush=True)
        for i, (h, (c, t, r)) in enumerate(new.items()):
            _save(h, OUT / f"popup{i}_{c.strip('#')}.png")
            kids = export_util._children_texts(h)
            print(f"[d] popup{i} class={c!r} rect={r} kids={kids[:12]}",
                  flush=True)
        # try REAL clicks down the first popup's rows, read back each time
        if new:
            h, (c, t, r) = next(iter(new.items()))
            n = 5
            for row in range(n):
                ry = r[1] + (row + 1) * (r[3] - r[1]) // (n + 1)
                rx = (r[0] + r[2]) // 2
                winutil.user32.SetCursorPos(rx, ry)
                time.sleep(0.2)
                winutil.real_click_screen(rx, ry)
                time.sleep(0.9)
                now = m8.nozzle_reads(session).get("flow")
                print(f"[d] real click row y={ry}: flow={now!r}", flush=True)
                if now == "High Flow":
                    print("[d] FLIPPED", flush=True)
                    break
                # reopen if the popup closed
                if not toplevels(session.pid):
                    winutil.msg_click_screen(cx, cy, session.hwnd)
                    time.sleep(1.0)
                    nl = {h2: i2 for h2, i2 in toplevels(session.pid).items()
                          if h2 not in before and h2 != session.hwnd}
                    if nl:
                        h, (c, t, r) = next(iter(nl.items()))
        return 0
    finally:
        session.close()
        print("[d] app closed", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
