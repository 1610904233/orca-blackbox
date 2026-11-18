#!/usr/bin/env python3
# diag/macos_probe_color_chip.py — what opens when the filament colour chip is
# clicked on macOS?  Discovery only: dump windows, AX controls and OCR.

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
from mac_common import (  # noqa: E402
    Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = HERE / "artifacts" / "mac" / "probe" / "color_chip"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
CHIP_XY = (220, 418)


def pixel(frame, x, y):
    i = (y * frame.width + x) * 4
    b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
    return (r, g, b)


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
        ok, frame, frac, _s = wait_for_model(driver, app, win, timeout_s=120.0)
        rep.check("launch", True, f"pid={app.pid} loaded={ok} frac={frac:.3f}")
        rep.log(f"[INFO] chip rgb before={pixel(frame, *CHIP_XY)}")
        driver.click(win.rect.x + CHIP_XY[0], win.rect.y + CHIP_XY[1])
        time.sleep(2.0)
        driver.capture(win).save_png(OUT / "after_click.png")
        driver.capture_screen().save_png(OUT / "dialog_screen.png")
        words = recognize_text(driver.capture_screen().crop(win.rect))
        rep.log(f"[INFO] OCR={[(w.text, w.rect.to_xywh()) for w in words][:60]}")
        for w in driver.windows_for_pid(app.pid):
            if not w.on_screen or w.rect.area < 200:
                continue
            rep.log(f"[WINDOW] id={w.id} title={w.title!r} "
                    f"rect={w.rect.to_xywh()} layer={w.layer}")
            try:
                ctrls = driver.controls(w)
            except Exception as exc:  # noqa: BLE001
                rep.log(f"   controls error: {exc}")
                continue
            for c in ctrls[:60]:
                rep.log(f"   {c.role} title={c.title!r} value={c.value!r} "
                        f"rect={c.rect.to_xywh() if c.rect else None} "
                        f"enabled={c.enabled}")
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
