#!/usr/bin/env python3
# diag/macos_probe_plate_remove_lock.py — calibrate the plate-side Remove/Lock
# rail icons (m8x_194 / m8x_197) on macOS.
#
# Usage:
#   ORCA_BB_ALLOW_HOST=1 .venv/bin/python \
#     diag/macos_probe_plate_remove_lock.py [--add-plate]
#
# Hover-candidate scanning only; no destructive action is taken unless
# --click-remove/--click-lock is passed.

from __future__ import annotations

import argparse
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
for path in (str(HERE), str(HERE / "tests" / "engine"),
             str(HERE / "tests" / "engine" / "macos_pilot")):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = HERE / "artifacts" / "mac" / "probe" / "plate_remove_lock"
MODEL = HERE / "fixtures" / "Prusa.stl"
ADD_PLATE_XY = (520, 75)
CANDIDATES = [(1108, 326), (1126, 397)]
# Plate-2 (current) rail, read off two_plates.png at 1200x800: the icons
# follow the plate's top-right edge from the X at (920,251) to the up arrow.
RAIL_POINTS = [(920, 251), (933, 261), (952, 271),
               (972, 281), (992, 291), (1012, 302)]


def tooltip(driver, win, x, y, mode="right") -> str:
    driver.move(win.rect.x + x, win.rect.y + y)
    time.sleep(1.2)
    if mode == "right":
        region = Rect(win.rect.x + x + 8, win.rect.y + y - 20, 260, 80)
    else:
        region = Rect(win.rect.x + x - 100, win.rect.y + y + 12, 340, 70)
    words = recognize_text(driver.capture_screen(), region)
    return " ".join(w.text for w in words).strip()


def scan(driver, win, rep, tag):
    frame = driver.capture(win)
    frame.save_png(OUT / f"{tag}.png")
    words = recognize_text(driver.capture_screen().crop(win.rect))
    labels = [w for w in words
              if any(k in w.text.lower() for k in ("plate", "remove",
                                                   "lock", "arrange"))]
    rep.log(f"[{tag}] text words={[(w.text, w.rect.to_xywh()) for w in labels]}")
    rep.log(f"[{tag}] candidates:")
    for x, y in CANDIDATES:
        for mode in ("right", "below"):
            tip = tooltip(driver, win, x, y, mode)
            rep.log(f"  ({x},{y}) {mode}: {tip!r}")
    hits = []
    if tag == "two_plates":
        rep.log(f"[{tag}] rail points:")
        for x, y in RAIL_POINTS:
            for mode in ("right", "below"):
                tip = tooltip(driver, win, x, y, mode)
                rep.log(f"  rail ({x},{y}) {mode}: {tip!r}")
                low = tip.lower()
                if any(k in low for k in ("remove", "lock", "arrange",
                                          "plate")):
                    hits.append((x, y, tip))
    rep.check(f"{tag}: rail tooltip hits", bool(hits), f"n={len(hits)}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--add-plate", action="store_true")
    ap.add_argument("--click-remove", action="store_true")
    ap.add_argument("--click-lock", action="store_true")
    args = ap.parse_args()

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    rep = Reporter(OUT)
    driver = None
    app = None
    win = None
    code = 2
    try:
        driver = get_driver()
        app, win = launch_and_focus(driver, OUT / "profile", model=MODEL,
                                    timeout_s=150.0,
                                    log_path=OUT / "app_launch.log")
        ok, frame, frac, _seen = wait_for_model(driver, app, win,
                                                timeout_s=120.0)
        rep.log(f"[INFO] loaded={ok} colored={frac:.4f} "
                f"win={win.rect.to_xywh()}")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        scan(driver, win, rep, "single")
        if args.add_plate:
            tip = tooltip(driver, win, *ADD_PLATE_XY, mode="below")
            rep.log(f"[INFO] Add plate tooltip={tip!r}")
            driver.click(win.rect.x + ADD_PLATE_XY[0],
                         win.rect.y + ADD_PLATE_XY[1])
            time.sleep(3.0)
            hits = scan(driver, win, rep, "two_plates")
            target = None
            want = "remove" if args.click_remove else (
                "lock" if args.click_lock else "")
            if want:
                target = next(((x, y, t) for x, y, t in hits
                               if want in t.lower()), None)
                if target is None:
                    # Fall back to the user-supplied calibrated points.
                    for x, y in CANDIDATES:
                        t = tooltip(driver, win, x, y)
                        if want in t.lower():
                            target = (x, y, t)
                            break
                rep.log(f"[INFO] click target for {want!r}: {target}")
                if target:
                    driver.click(win.rect.x + target[0],
                                 win.rect.y + target[1])
                    time.sleep(3.0)
                    driver.capture(win).save_png(OUT / "after_click.png")
                    words = recognize_text(
                        driver.capture_screen().crop(win.rect))
                    rep.log(f"[INFO] after click words="
                            f"{[w.text for w in words if len(w.text) > 2][:40]}")
        rep.check("app alive", app.alive())
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        code = rep.save({})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
