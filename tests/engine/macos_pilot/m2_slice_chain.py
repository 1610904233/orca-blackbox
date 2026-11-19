#!/usr/bin/env python3
# m2_slice_chain.py — macOS port: Feishu #59 model load -> slice -> Preview toolpath.
# feishu: baseline#59  (macOS port; corresponds to the enabled Windows
#         m2_slice_chain, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   model arrives in the viewport, "Slice plate" completes, and switching to
#   Preview renders toolpaths: chromatic viewport fraction > 1.0% AND at
#   least 1.5x the pre-slice colored-model baseline.
#
# macOS mapping:
#   model loaded    -> mac_common.wait_for_model (two-poll stability).
#   slice started   -> Slice plate click at (1000,45) (window-relative).
#   slice completed -> File > Export G-code... menu item becomes enabled
#                      (macOS equivalent of the done badge).
#   Preview         -> click the Preview tab; active teal fraction > 0.5.
#   toolpath        -> chromatic fraction (channel spread > 40) over the
#                      viewport Rect(430,70,w-8,h-8), same thresholds as
#                      Windows.
#
# Artifacts: artifacts/mac/pilot/m2/{report.log,result.json,*.png}.

from __future__ import annotations

import argparse
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]       # repo root
ENGINE = Path(__file__).resolve().parents[1]     # tests/engine
for path in (str(HERE), str(ENGINE)):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.base import Frame, Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, dismiss_dialogs, launch_and_focus,
    teal_fraction, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m2"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
PREVIEW_TAB = Rect(180, 31, 122, 29)
VIEWPORT = Rect(430, 70, 762, 722)
SPREAD_COLORED = 40
TOOLPATH_COLORED_FLOOR = 0.010
TOOLPATH_RATIO = 1.5


def chromatic_fraction(frame: Frame, rect: Rect, sample_step: int = 4) -> float:
    """Fraction of viewport samples with channel spread > 40 (toolpaths)."""
    x0 = max(0, min(frame.width, int(round(rect.x))))
    y0 = max(0, min(frame.height, int(round(rect.y))))
    x1 = max(x0, min(frame.width, int(round(rect.right))))
    y1 = max(y0, min(frame.height, int(round(rect.bottom))))
    step = max(1, int(sample_step))
    data = frame.data
    n = colored = 0
    for y in range(y0, y1, step):
        row = y * frame.width * 4
        for x in range(x0, x1, step):
            i = row + x * 4
            b, g, r = data[i], data[i + 1], data[i + 2]
            if max(b, g, r) - min(b, g, r) > SPREAD_COLORED:
                colored += 1
            n += 1
    return colored / n if n else 0.0


def scaled(rect: Rect, win) -> Rect:
    sx = win.rect.w / 1200.0
    sy = win.rect.h / 800.0
    return Rect(rect.x * sx, rect.y * sy, rect.w * sx, rect.h * sy)


def export_enabled(driver, win) -> bool | None:
    item = driver.find_control(win, role="AXMenuItem",
                               title="Export G-code", timeout_s=2)
    return None if item is None else item.enabled


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--slice-timeout", default=240.0, type=float)
    args = ap.parse_args()

    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)

    rep = Reporter(OUT)
    rep.log("=== m2 macOS slice chain ===")
    rep.log(f"datadir={args.datadir} model={DEFAULT_MODEL}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=DEFAULT_MODEL,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"blockers={app.extra.get('blockers')}")

        loaded, model_frame, frac, seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        if model_frame is not None:
            model_frame.save_png(OUT / "model_loaded.png")
        rep.check("model loaded", loaded,
                  f"colored_fraction={frac:.4f} (threshold 0.03)")
        if not loaded:
            return rep.save({"stage": "load"})

        rep.check("Export disabled before slice",
                  export_enabled(driver, win) is False,
                  f"enabled={export_enabled(driver, win)}")
        base_vp = chromatic_fraction(model_frame, scaled(VIEWPORT, win))

        sx = win.rect.w / 1200.0
        sy = win.rect.h / 800.0
        driver.click(win.rect.x + 1000 * sx, win.rect.y + 45 * sy)
        started = time.monotonic()
        done = False
        while time.monotonic() - started < args.slice_timeout:
            seen = dismiss_dialogs(driver, app, win, seen)
            if export_enabled(driver, win):
                done = True
                break
            time.sleep(2.0)
        elapsed = time.monotonic() - started
        rep.check("slice completed (Export G-code enabled)", done,
                  f"elapsed={elapsed:.1f}s")
        if not done:
            return rep.save({"stage": "slice"})
        driver.capture(win).save_png(OUT / "slice_done.png")

        # The app already jumps to Preview after a slice; click the tab so the
        # assertion does not depend on that side effect.
        prev = scaled(PREVIEW_TAB, win)
        driver.click(win.rect.x + prev.x + prev.w / 2,
                     win.rect.y + prev.y + prev.h / 2)
        time.sleep(2.5)
        preview = driver.capture(win)
        preview.save_png(OUT / "preview.png")
        active = teal_fraction(preview, prev)
        rep.check("Preview tab active", active > 0.5, f"teal={active:.3f}")

        colored = chromatic_fraction(preview, scaled(VIEWPORT, win))
        ratio = colored / max(base_vp, 1e-4)
        rep.check("preview toolpath rendered",
                  colored > TOOLPATH_COLORED_FLOOR and ratio >= TOOLPATH_RATIO,
                  f"colored={colored:.4f} base={base_vp:.4f} "
                  f"ratio={ratio:.2f} floor={TOOLPATH_COLORED_FLOOR}")
        rep.check("app alive", app.alive())

        alive_before = app.alive()
        closed = close_app(driver, app, win)
        app = None
        rep.check("software closed", alive_before and closed,
                  f"alive_before={alive_before} closed={closed}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        exit_code = rep.save({"covered": ["#59"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
