#!/usr/bin/env python3
# m7h_context_delete.py — macOS port: Feishu #18 delete model via context menu.
# feishu: none  (macOS port; corresponds to the enabled Windows
#         m7h_context_delete, registered in cases.MACOS_BASELINE)
#
# Windows flow -> macOS equivalents:
#   load mixed fixture             -> launch --model
#   select model                   -> click the green model cube
#   right-click model              -> real right-click; native object menu
#   Delete row                     -> AXPress the menu's exact "Delete" item
#   viewport empty                 -> viewport chromatic fraction drops
#   Slice on empty scene rejected  -> Export G-code stays disabled
#
# macOS note: the mixed fixture's big colored block (upper-left) is a legend,
# not a hit-testable model; the green cube is the object.  Right-clicking the
# block opens nothing, so the model point is the cube.
#
# Artifacts: artifacts/mac/pilot/m7h/{*.png,report.log,result.json}.

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

import numpy as np  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import (  # noqa: E402
    find_text, joined_text, recognize_text,
)
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m7h"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MODEL_POINT = (814, 396)  # green model cube, window-relative
VIEWPORT = (430, 100, 1080, 700)
EMPTY_BED_MAX = 0.015


def _vp_colored(frame) -> float:
    arr = np.frombuffer(frame.data, dtype=np.uint8).reshape(
        frame.height, frame.width, 4)
    b = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    r = arr[:, :, 2].astype(int)
    spread = np.maximum(np.maximum(b, g), r) - np.minimum(np.minimum(b, g), r)
    x0, y0, x1, y1 = VIEWPORT
    return float((spread[y0:y1, x0:x1] > 24).mean())


def _delete_item(driver, app, win):
    """Right-click the model; return (menu_window, Delete AXMenuItem)."""
    driver.click(win.rect.x + MODEL_POINT[0], win.rect.y + MODEL_POINT[1])
    time.sleep(0.8)
    driver.click(win.rect.x + MODEL_POINT[0], win.rect.y + MODEL_POINT[1],
                 button="right")
    time.sleep(1.0)
    for w in driver.windows_for_pid(app.pid):
        if w.id == win.id or not w.on_screen or w.rect.area < 1000:
            continue
        try:
            for c in driver.controls(w):
                if (c.role == "AXMenuItem"
                        and c.title.strip().lower() == "delete"):
                    return w, c
        except Exception:
            continue
    return None, None


def _export_enabled(driver, win):
    ctl = driver.find_control(win, role="AXMenuItem",
                              title="Export G-code", timeout_s=2)
    return None if ctl is None else ctl.enabled


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
    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    rep = Reporter(OUT)
    rep.log("=== m7h macOS context-delete (#18) ===")
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

        loaded, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=args.model_timeout)
        frame.save_png(OUT / "before.png")
        before_vp = _vp_colored(frame)
        rep.check("model arrives", loaded,
                  f"colored_fraction={frac:.4f} viewport={before_vp:.4f}")

        menu, item = _delete_item(driver, app, win)
        if menu is not None:
            frame2 = driver.capture(win)
            frame2.save_png(OUT / "context_menu.png")
            rows = [w.text for w in recognize_text(frame2)
                    if any(k in w.text.lower() for k in
                           ("delete", "clone", "simplify", "center",
                            "drop", "split", "mirror", "mesh"))]
            rep.log(f"[INFO] context-menu rows: {rows}")
        rep.check("context menu opens", menu is not None and item is not None,
                  f"menu={menu.title if menu else None}")
        rep.check("delete row found", item is not None)
        if item is None:
            raise RuntimeError("object context-menu Delete not found")

        print("[m7h] AXPress Delete")
        driver.click_control(item)
        time.sleep(2.0)
        after = driver.capture(win)
        after.save_png(OUT / "after_delete.png")
        after_vp = _vp_colored(after)
        rep.check("viewport empty after delete",
                  after_vp < EMPTY_BED_MAX,
                  f"viewport={after_vp:.4f} (before={before_vp:.4f})")

        export_before = _export_enabled(driver, win)
        rep.check("Export G-code item found", export_before is not None,
                  f"enabled={export_before}")
        sx = win.rect.w / 1200.0
        sy = win.rect.h / 800.0
        print("[m7h] click Slice on the emptied bed")
        driver.click(win.rect.x + 1000 * sx, win.rect.y + 45 * sy)
        stayed_disabled = True
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            enabled = _export_enabled(driver, win)
            if enabled:
                stayed_disabled = False
                break
            time.sleep(1.0)
        rep.check("empty scene rejects slice",
                  export_before is not None and stayed_disabled,
                  f"Export before={export_before} after={enabled}")
        driver.capture(win).save_png(OUT / "after_slice.png")

        rep.check("app alive", app.alive())
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
