#!/usr/bin/env python3
# diag/macos_probe_chip_scan.py — locate the filament colour chips in the
# sidebar by scanning saturated pixels around the filament rows.

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
from mac_common import Reporter, close_app, launch_and_focus, wait_for_model  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "chip_scan"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def main() -> int:
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
        ok, frame, _frac, _s = wait_for_model(driver, app, win, timeout_s=120.0)
        rep.check("launch", True, f"pid={app.pid} loaded={ok}")
        w = frame.width
        for y in (405, 412, 418, 425, 440, 447, 455, 470, 478, 486):
            runs = []
            start = None
            for x in range(0, 430):
                i = (y * w + x) * 4
                b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
                spread = max(r, g, b) - min(r, g, b)
                hot = spread > 40 and max(r, g, b) > 60
                if hot and start is None:
                    start = x
                elif not hot and start is not None:
                    if x - start >= 4:
                        i2 = (y * w + start + 2) * 4
                        runs.append((start, x - 1,
                                     (frame.data[i2 + 2],
                                      frame.data[i2 + 1],
                                      frame.data[i2])))
                    start = None
            if start is not None:
                runs.append((start, 429, None))
            rep.log(f"y={y} runs={runs}")
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
