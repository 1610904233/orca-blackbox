#!/usr/bin/env python3
# m3b_delete_scene.py — macOS pilot: delete all objects -> empty bed.
# feishu: none  (macOS pilot probe, not registered in cases.py)
#
# macOS equivalent of the Windows m3b chain:
#   load a model -> Edit > Delete All -> viewport color drops to the empty-bed
#   baseline -> Slice is rejected (Export G-code stays disabled).
#
# Artifacts: artifacts/mac/pilot/m3b/{before,after_delete,after_slice}.png.

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]       # repo root
ENGINE = Path(__file__).resolve().parents[1]     # tests/engine
for path in (str(HERE), str(ENGINE)):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, dismiss_dialogs, launch_and_focus,
)

OUT = ARTIFACTS / "pilot" / "m3b"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MODEL_COLORED_THRESHOLD = 0.03


def _export_item(driver, win):
    return driver.find_control(win, role="AXMenuItem",
                               title="Export G-code", timeout_s=3)


def _wait_model(driver, app, win, timeout_s: float, seen: set):
    deadline = time.monotonic() + timeout_s
    last_frame = None
    last_frac = 0.0
    while time.monotonic() < deadline:
        seen = dismiss_dialogs(driver, app, win, seen)
        frame = driver.capture(win)
        frac = frame.stats()["colored_fraction"]
        last_frame, last_frac = frame, frac
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
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--model-timeout", default=60.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m3b macOS delete-scene pilot ===")
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

        seen: set = set()
        loaded, before, frac, seen = _wait_model(
            driver, app, win, args.model_timeout, seen)
        if before is not None:
            before.save_png(OUT / "before.png")
        rep.check("model loaded", loaded,
                  f"colored_fraction={frac:.4f} "
                  f"(threshold {MODEL_COLORED_THRESHOLD})")

        export = _export_item(driver, win)
        rep.check("Export disabled before delete",
                  export is not None and not export.enabled,
                  f"enabled={export.enabled if export else None}")

        delete = driver.find_control(
            win, role="AXMenuItem", title="Delete All", timeout_s=3)
        if delete is None or not delete.enabled:
            # Some builds only populate the Edit menu after it is opened.
            edit = driver.find_control(
                win, role="AXMenuBarItem", title="Edit", timeout_s=2)
            if edit is not None:
                driver.click_control(edit)
                time.sleep(1.0)
                delete = driver.find_control(
                    win, role="AXMenuItem", title="Delete All", timeout_s=2)
        rep.check("Delete All found/enabled",
                  delete is not None and delete.enabled,
                  f"enabled={delete.enabled if delete else None}")
        if delete is None or not delete.enabled:
            raise RuntimeError("Delete All menu item unavailable")

        rep.log("[INFO] AXPress Delete All")
        driver.click_control(delete)
        time.sleep(1.5)
        seen = dismiss_dialogs(driver, app, win, seen)
        time.sleep(1.0)

        after = driver.capture(win)
        after.save_png(OUT / "after_delete.png")
        a_stats = after.stats()
        a_frac = a_stats["colored_fraction"]
        cleared = a_frac < 0.025 and a_frac < frac * 0.7
        rep.check("scene cleared", cleared,
                  f"before_colored={frac:.4f} after_colored={a_frac:.4f} "
                  f"mean_luma={a_stats['mean_luma']:.2f}")

        export2 = _export_item(driver, win)
        rep.check("Export disabled after delete",
                  export2 is not None and not export2.enabled,
                  f"enabled={export2.enabled if export2 else None}")

        sx = win.rect.w / 1200.0
        sy = win.rect.h / 800.0
        rep.log("[INFO] click Slice on the empty bed")
        driver.click(win.rect.x + 1000 * sx, win.rect.y + 45 * sy)
        stayed_disabled = True
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            seen = dismiss_dialogs(driver, app, win, seen)
            cur = _export_item(driver, win)
            if cur is None or cur.enabled:
                stayed_disabled = False
                break
            time.sleep(1.0)
        rep.check("Slice rejected after delete (Export stays disabled)",
                  stayed_disabled)
        driver.capture(win).save_png(OUT / "after_slice.png")
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
