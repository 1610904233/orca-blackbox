#!/usr/bin/env python3
# diag/macos_probe_slice_export.py — complete slice + Export G-code on macOS.
#
# Prusa.stl alone, click Slice plate, wait for File > Export G-code to become
# enabled, export through the native save panel, read filament usage.

from __future__ import annotations

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

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    Reporter, close_app, launch_and_focus, wait_for_model,
)
import mac_gcode  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "slice_export"
MODEL = HERE / "fixtures" / "Prusa.stl"


def export_item(driver, win):
    return driver.find_control(win, role="AXMenuItem",
                               title="Export G-code", timeout_s=2)


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    target = OUT / "probe.gcode"
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
                                                timeout_s=120.0,
                                                threshold=0.012)
        rep.check("launch/model", ok, f"colored={frac:.4f}")
        item = export_item(driver, win)
        rep.check("Export G-code present", item is not None,
                  f"enabled={None if item is None else item.enabled}")
        sx = win.rect.w / 1200.0
        sy = win.rect.h / 800.0
        driver.click(win.rect.x + 1000 * sx, win.rect.y + 45 * sy)
        deadline = time.monotonic() + 240.0
        enabled = False
        while time.monotonic() < deadline:
            it = export_item(driver, win)
            if it is not None and it.enabled:
                enabled = True
                break
            time.sleep(3.0)
        driver.capture(win).save_png(OUT / "after_slice.png")
        rep.check("slice completes (Export enabled)", enabled)

        rows = [c for c in driver.controls(win, max_depth=12)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("export g-code")]
        rep.log(f"[INFO] export rows={[(c.title, c.enabled) for c in rows]}")
        rep.check("Export G-code item clickable", bool(rows) and rows[0].enabled)
        if rows:
            driver.click_control(rows[0])
            time.sleep(1.5)
            saved = driver.save_file_dialog(
                win, target, default_dir=target.parent, accept_anywhere=True,
                search_roots=[OUT, HERE / "fixtures",
                              Path.home() / "Documents"])
            rep.log(f"[INFO] save_file_dialog={saved} exists={target.exists()}")
            rep.check("gcode written", saved and target.exists()
                      and target.stat().st_size > 0,
                      f"size={target.stat().st_size if target.exists() else 0}")
            if target.exists():
                data = target.read_bytes()
                used = mac_gcode.used_filaments(data)
                rep.log(f"[INFO] used filaments={used} bytes={len(data)}")
                rep.check("filament usage readable", bool(used))
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
