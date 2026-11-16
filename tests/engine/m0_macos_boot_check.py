#!/usr/bin/env python3
# m0_macos_boot_check.py — macOS M0: launch, find main window, capture, close.
# feishu: none  (macOS chain probe, not registered in cases.py)
#
# Standalone macOS port of the m0 boot/screenshot chain.  Uses the
# platform-neutral driver (AX + ScreenCaptureKit) and a fresh isolated
# datadir.  Writes artifacts/mac/m0/{boot_*.png,report.log,result.json}.

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
    ARTIFACTS, Reporter, close_app, frame_ok, launch_and_focus,
)

OUT = ARTIFACTS / "m0"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=None, help="optional 3mf/stl to auto-load")
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m0 macOS boot check ===")
    rep.log(f"datadir={args.datadir} model={args.model}")

    driver = None
    app = None
    win = None
    all_ok = False
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True,
                  f"{type(driver).__name__} message_input={driver.message_input}")
        app, win = launch_and_focus(
            driver, args.datadir, model=args.model,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True,
                  f"pid={app.pid} blockers={app.extra.get('blockers')}")
        rep.check("main window", bool(win.rect),
                  f"id={win.id} title={win.title!r} "
                  f"rect={win.rect.to_xywh()} scale={driver.dpi_scale(win):.2f}")

        all_ok = True
        for i, delay in enumerate((0.5, 2.0, 5.0)):
            time.sleep(delay)
            try:
                frame = driver.capture(win)
                path = OUT / f"boot_{i}.png"
                frame.save_png(path)
                ok, stats = frame_ok(frame)
                all_ok = all_ok and ok
                rep.check(f"capture {i}", ok,
                          f"{frame.width}x{frame.height} "
                          f"nonblack={stats['nonblack_fraction']:.4f} "
                          f"mean_luma={stats['mean_luma']:.2f} -> {path.name}")
            except Exception as exc:  # noqa: BLE001
                all_ok = False
                rep.check(f"capture {i}", False,
                          f"{type(exc).__name__}: {exc}")

        try:
            controls = driver.controls(win)
            rep.check("controls enumerated", len(controls) > 0,
                      f"total={len(controls)}")
        except Exception as exc:  # noqa: BLE001
            all_ok = False
            rep.check("controls enumerated", False,
                      f"{type(exc).__name__}: {exc}")
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
        exit_code = rep.save({"all_captures_ok": all_ok})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
