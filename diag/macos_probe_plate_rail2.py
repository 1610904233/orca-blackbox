#!/usr/bin/env python3
# diag/macos_probe_plate_rail2.py — fine scan of the plate rail with 3x OCR.
#
# The first scan found "Customize current plate" at ~(1070,300).  Tooltips are
# ~11px text, so this probe upscales the crop 3x before Vision OCR and scans a
# small grid over the rail (x 1050..1140, y 180..460).

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

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from harness.platform.base import Frame, Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "plate_rail2"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


def ocr_upscaled(frame, region, scale=3):
    crop = frame.crop(region)
    if crop.width <= 0 or crop.height <= 0:
        return ""
    arr = np.frombuffer(crop.data, dtype=np.uint8).reshape(
        crop.height, crop.width, 4)
    big = cv2.resize(arr, (crop.width * scale, crop.height * scale),
                     interpolation=cv2.INTER_CUBIC)
    return " ".join(w.text for w in recognize_text(
        Frame(big.shape[1], big.shape[0], big.tobytes())))


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
        for y in (180, 200, 220, 240, 260, 280, 300, 320, 340, 360,
                  380, 400, 420, 440, 460):
            for x in (1050, 1060, 1070, 1080, 1090, 1100, 1110, 1120, 1130):
                driver.move(win.rect.x + x, win.rect.y + y)
                time.sleep(1.0)
                text = ocr_upscaled(
                    driver.capture_screen(),
                    Rect(win.rect.x + x + 5, win.rect.y + y - 45, 300, 100))
                if any(k in text.lower() for k in
                       ("plate", "remove", "lock", "orient", "arrange",
                        "custom", "add")):
                    rep.log(f"[TIP] x={x} y={y}: {text!r}")
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
