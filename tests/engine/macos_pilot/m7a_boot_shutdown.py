#!/usr/bin/env python3
# m7a_boot_shutdown.py — macOS pilot: Feishu #7/#8 boot + graceful close.
# feishu: none  (macOS pilot probe; corresponds to the enabled Windows
#         m7a_boot_shutdown, not registered in cases.py yet)
#
# Windows assertions -> macOS equivalents:
#   Prepare tab active      -> teal selected-tab fraction (0,150,136)
#   canvas paints           -> viewport crop non-blank / non-black
#   empty plate (slice idle)-> File > Export G-code disabled
#   no leftover process     -> main process gone + no NSRunningApplication
#
# Artifacts: artifacts/mac/pilot/m7a/{before.png,report.log,result.json}.

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

import AppKit  # noqa: E402  (macOS-only pilot)

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, launch_and_focus, teal_fraction,
)

OUT = ARTIFACTS / "pilot" / "m7a"
BUNDLE_ID = "com.snapmaker.snapmaker-orca"
PREPARE_RECT = Rect(55, 31, 115, 29)
PREVIEW_RECT = Rect(180, 31, 122, 29)
VIEWPORT = Rect(420, 60, 780, 740)


def _export_item(driver, win):
    return driver.find_control(win, role="AXMenuItem",
                               title="Export G-code", timeout_s=3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    # Fresh profile for the boot invariant (same intent as profile.seed_profile(fresh=True)).
    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)

    rep = Reporter(OUT)
    rep.log("=== m7a macOS boot/shutdown pilot ===")
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
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"blockers={app.extra.get('blockers')}")

        before = driver.capture(win)
        before.save_png(OUT / "before.png")
        sx = win.rect.w / 1200.0
        sy = win.rect.h / 800.0
        prep = Rect(PREPARE_RECT.x * sx, PREPARE_RECT.y * sy,
                    PREPARE_RECT.w * sx, PREPARE_RECT.h * sy)
        prev = Rect(PREVIEW_RECT.x * sx, PREVIEW_RECT.y * sy,
                    PREVIEW_RECT.w * sx, PREVIEW_RECT.h * sy)
        prep_teal = teal_fraction(before, prep)
        prev_teal = teal_fraction(before, prev)
        rep.check("Prepare tab active", prep_teal > 0.5 and prev_teal < 0.1,
                  f"prepare_teal={prep_teal:.3f} preview_teal={prev_teal:.3f}")

        vp = before.crop(Rect(VIEWPORT.x * sx, VIEWPORT.y * sy,
                              VIEWPORT.w * sx, VIEWPORT.h * sy))
        vp_stats = vp.stats()
        canvas_ok = (vp_stats["nonblack_fraction"] > 0.5
                     and vp_stats["mean_luma"] > 50.0
                     and (vp_stats["max_luma"] - vp_stats["min_luma"]) > 10.0)
        rep.check("canvas paints", canvas_ok,
                  f"viewport {vp.width}x{vp.height} "
                  f"nonblack={vp_stats['nonblack_fraction']:.4f} "
                  f"mean_luma={vp_stats['mean_luma']:.2f}")

        export = _export_item(driver, win)
        rep.check("empty plate (Slice idle)",
                  export is not None and not export.enabled,
                  f"Export enabled={export.enabled if export else None}")

        rep.log("[INFO] graceful window close")
        driver.close_window(win)
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and app.alive():
            time.sleep(0.3)
        time.sleep(1.0)
        leftovers = AppKit.NSRunningApplication \
            .runningApplicationsWithBundleIdentifier_(BUNDLE_ID) or []
        no_leftover = (not app.alive()) and not leftovers
        rep.check("no leftover process", no_leftover,
                  f"popen_poll={app.poll()} leftovers="
                  f"{[a.processIdentifier() for a in leftovers]}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None and not args.keep:
            try:
                if app.alive():
                    app.terminate()
            except Exception:
                pass
            fh = app.extra.get("log_fh")
            if fh:
                try:
                    fh.close()
                except Exception:
                    pass
        elif app is not None:
            rep.log(f"[INFO] --keep: app pid={app.pid} left running")
        exit_code = rep.save({})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
