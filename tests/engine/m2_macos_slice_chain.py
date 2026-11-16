#!/usr/bin/env python3
# m2_macos_slice_chain.py — macOS M2: model load -> Slice -> completion.
# feishu: none  (macOS chain probe, not registered in cases.py)
#
# Completion signal: the File > "Export G-code..." AXMenuItem is disabled
# before slicing and becomes enabled when the slice result is ready — the
# macOS equivalent of the Windows `can_export_gcode()` signal.  No template
# matching / OCR is needed for this chain.
#
# Artifacts: artifacts/mac/m2/{model_loaded.png,slice_done.png,report.log,
# result.json}.

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
for path in (str(HERE), str(HERE / "tests" / "engine")):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, dismiss_dialogs, launch_and_focus,
)

OUT = ARTIFACTS / "m2"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MODEL_COLORED_THRESHOLD = 0.03  # empty bed ~0.018, U1 mixed fixture ~0.040


def _wait_model(driver, app, win, timeout_s: float, seen: set):
    deadline = time.monotonic() + timeout_s
    last_frac = 0.0
    last_frame = None
    while time.monotonic() < deadline:
        seen = dismiss_dialogs(driver, app, win, seen)
        frame = driver.capture(win)
        frac = frame.stats()["colored_fraction"]
        last_frac, last_frame = frac, frame
        if frac >= MODEL_COLORED_THRESHOLD:
            time.sleep(1.0)
            frame2 = driver.capture(win)
            frac2 = frame2.stats()["colored_fraction"]
            if frac2 >= MODEL_COLORED_THRESHOLD:
                return True, frame2, max(frac, frac2), seen
        time.sleep(1.0)
    return False, last_frame, last_frac, seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float,
                    help="main-window timeout")
    ap.add_argument("--model-timeout", default=60.0, type=float)
    ap.add_argument("--slice-timeout", default=180.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m2 macOS slice chain ===")
    rep.log(f"datadir={args.datadir} model={args.model}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=args.model,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"blockers={app.extra.get('blockers')}")
        rep.check("main window", bool(win.rect),
                  f"id={win.id} rect={win.rect.to_xywh()}")

        seen: set = set()
        loaded, model_frame, frac, seen = _wait_model(
            driver, app, win, args.model_timeout, seen)
        if model_frame is not None:
            model_frame.save_png(OUT / "model_loaded.png"
                                 if loaded else OUT / "model_missing.png")
        rep.check("model loaded", loaded,
                  f"colored_fraction={frac:.4f} "
                  f"(threshold {MODEL_COLORED_THRESHOLD})")

        export = driver.find_control(
            win, role="AXMenuItem", title="Export G-code", timeout_s=3)
        rep.check("Export G-code item found", export is not None,
                  f"enabled={export.enabled if export else None}")
        rep.check("Export disabled before slice",
                  export is not None and not export.enabled,
                  f"enabled={export.enabled if export else None}")

        before = model_frame or driver.capture(win)
        sx = win.rect.w / 1200.0
        sy = win.rect.h / 800.0
        if abs(sx - 1.0) > 0.02 or abs(sy - 1.0) > 0.02:
            rep.log(f"[WARN] window {win.rect.to_xywh()} differs from 1200x800; "
                    f"scaling slice-button offsets ({sx:.3f},{sy:.3f})")
        slice_point = (win.rect.x + 1000 * sx, win.rect.y + 45 * sy)
        rep.log(f"[INFO] click Slice plate at {slice_point}")
        driver.click(*slice_point)
        time.sleep(1.0)
        clicked = driver.capture(win)
        clicked.save_png(OUT / "slice_clicked.png")

        done = False
        elapsed = 0.0
        export_enabled = None
        start = time.monotonic()
        poll = 0
        while time.monotonic() - start < args.slice_timeout:
            poll += 1
            seen = dismiss_dialogs(driver, app, win, seen)
            current = driver.find_control(
                win, role="AXMenuItem", title="Export G-code", timeout_s=0)
            export_enabled = current.enabled if current is not None else None
            if export_enabled:
                done = True
                elapsed = time.monotonic() - start
                break
            if poll == 3:
                driver.capture(win).save_png(OUT / "slice_progress.png")
            time.sleep(2.0)
        if not done:
            elapsed = time.monotonic() - start
        rep.check("slice completed (Export G-code enabled)", done,
                  f"elapsed={elapsed:.1f}s export_enabled={export_enabled}")

        after = driver.capture(win)
        after.save_png(OUT / "slice_done.png")
        diff = before.difference(after)
        rep.check("UI changed after slice", diff > 0.01,
                  f"frame_diff={diff:.4f} colored={after.stats()['colored_fraction']:.4f}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None and not args.keep:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        elif app is not None:
            rep.log(f"[INFO] --keep: app pid={app.pid} left running")
        exit_code = rep.save({})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
