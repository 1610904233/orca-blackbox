#!/usr/bin/env python3
# diag/macos_probe_toolbar.py — map the custom-drawn top toolbar by tooltips.
#
# The macOS toolbar icons have no AX nodes; hover tooltips are the only text.
# Scans a grid over the toolbar strip and OCRs the area right/below the cursor.

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

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "toolbar"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


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
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(3.0)
        driver.capture_screen().crop(win.rect).save_png(OUT / "window.png")

        hits = 0
        for y in (45, 55, 65, 75):
            for x in range(620, 1161, 20):
                driver.move(win.rect.x + x, win.rect.y + y)
                time.sleep(1.1)
                region = Rect(win.rect.x + x - 120, win.rect.y + y + 10,
                              400, 80)
                words = recognize_text(driver.capture_screen(), region)
                text = " ".join(w.text for w in words).strip()
                if len(text) >= 4 and any(ch.isalpha() for ch in text):
                    hits += 1
                    rep.log(f"[TIP] x={x} y={y}: {text!r}")
        rep.check("tooltips found", hits > 0, f"hits={hits}")
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
