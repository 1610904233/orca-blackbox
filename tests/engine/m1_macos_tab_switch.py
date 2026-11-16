#!/usr/bin/env python3
# m1_macos_tab_switch.py — macOS M1: Prepare <-> Preview tab switch.
# feishu: none  (macOS chain probe, not registered in cases.py)
#
# The macOS top bar is custom-drawn (no AX elements), so this uses real
# clicks with an explicit CGEventSource.  State is verified with the same
# teal selected-tab colour the Windows m1 case uses:
#   selected   = (0,150,136)
#   unselected = (59,68,70)
#
# Artifacts: artifacts/mac/m1/{tab_*.png,report.log,result.json}.

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

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, teal_fraction,
)

OUT = ARTIFACTS / "m1"
# Calibrated on the default 1200x800 window (window-relative pixels).
PREPARE_RECT = Rect(55, 31, 115, 29)
PREVIEW_RECT = Rect(180, 31, 122, 29)
PREPARE_CLICK = (110, 45)
PREVIEW_CLICK = (240, 45)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m1 macOS Prepare/Preview tab switch ===")
    rep.log(f"datadir={args.datadir}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, timeout_s=args.timeout,
            log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid}")
        rep.check("main window", bool(win.rect),
                  f"id={win.id} title={win.title!r} rect={win.rect.to_xywh()}")

        sx = win.rect.w / 1200.0
        sy = win.rect.h / 800.0
        if abs(sx - 1.0) > 0.02 or abs(sy - 1.0) > 0.02:
            rep.log(f"[WARN] window {win.rect.to_xywh()} differs from 1200x800; "
                    f"scaling tab offsets ({sx:.3f},{sy:.3f})")
        prep_rect = Rect(PREPARE_RECT.x * sx, PREPARE_RECT.y * sy,
                         PREPARE_RECT.w * sx, PREPARE_RECT.h * sy)
        prev_rect = Rect(PREVIEW_RECT.x * sx, PREVIEW_RECT.y * sy,
                         PREVIEW_RECT.w * sx, PREVIEW_RECT.h * sy)

        before = driver.capture(win)
        before.save_png(OUT / "tab_before.png")
        p0 = teal_fraction(before, prep_rect)
        v0 = teal_fraction(before, prev_rect)
        rep.check("Prepare active initially", p0 > 0.5 and v0 < 0.1,
                  f"prepare_teal={p0:.3f} preview_teal={v0:.3f} "
                  f"colors={before.pixel(int(PREPARE_CLICK[0]*sx), int(PREPARE_CLICK[1]*sy))}"
                  f"/{before.pixel(int(PREVIEW_CLICK[0]*sx), int(PREVIEW_CLICK[1]*sy))}")

        ox, oy = int(win.rect.x), int(win.rect.y)
        driver.click(ox + PREVIEW_CLICK[0] * sx, oy + PREVIEW_CLICK[1] * sy)
        time.sleep(1.2)
        preview = driver.capture(win)
        preview.save_png(OUT / "tab_preview.png")
        p1 = teal_fraction(preview, prep_rect)
        v1 = teal_fraction(preview, prev_rect)
        diff1 = before.difference(preview)
        rep.check("Preview tab click", v1 > 0.5 and p1 < 0.1 and diff1 > 0.01,
                  f"prepare_teal={p1:.3f} preview_teal={v1:.3f} "
                  f"frame_diff={diff1:.4f}")

        driver.click(ox + PREPARE_CLICK[0] * sx, oy + PREPARE_CLICK[1] * sy)
        time.sleep(1.2)
        back = driver.capture(win)
        back.save_png(OUT / "tab_prepare_back.png")
        p2 = teal_fraction(back, prep_rect)
        v2 = teal_fraction(back, prev_rect)
        diff2 = before.difference(back)
        rep.check("Prepare switch back", p2 > 0.5 and v2 < 0.1,
                  f"prepare_teal={p2:.3f} preview_teal={v2:.3f} "
                  f"frame_diff_vs_start={diff2:.4f}")
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
