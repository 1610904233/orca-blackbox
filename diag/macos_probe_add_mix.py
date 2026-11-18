#!/usr/bin/env python3
# diag/macos_probe_add_mix.py — find the entry to the Add Mix dialog (Ratio /
# Cycle / Match / Gradient tabs) from the Color Mixing panel.

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
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import Reporter, close_app, launch_and_focus, wait_for_model  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "add_mix"
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
        ok, frame, frac, _s = wait_for_model(driver, app, win, timeout_s=120.0)
        rep.check("launch", True, f"pid={app.pid} loaded={ok}")
        ws = recognize_text(frame)
        mix = [w for w in ws if "color mixing" in w.text.lower()
               or "f3 50%" in w.text.lower()]
        rep.log(f"[INFO] mixing words={[(w.text, w.rect.to_xywh()) for w in mix]}")
        # AX buttons around the Color Mixing panel.
        for c in driver.controls(win):
            if c.role == "AXButton" and c.rect is not None \
                    and 450 < c.rect.y < 600 and c.rect.x < 430:
                rep.log(f"[BUTTON] {c.title!r} {c.description!r} "
                        f"{c.rect.to_xywh()} actions={c.actions}")
        candidates = [(372, 524), (372, 490), (372, 558), (380, 452),
                      (404, 524), (404, 558)]
        for (x, y) in candidates:
            driver.click(win.rect.x + x, win.rect.y + y)
            time.sleep(1.2)
            wins = [w for w in driver.windows_for_pid(app.pid)
                    if w.on_screen and w.id != win.id and w.rect.area > 400]
            if wins:
                rep.log(f"[INFO] click ({x},{y}) windows="
                        f"{[(w.title, w.rect.to_xywh(), w.layer) for w in wins]}")
                for w in wins:
                    try:
                        from harness.platform.base import Rect
                        words = recognize_text(
                            driver.capture_screen().crop(win.rect),
                            Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
                                 w.rect.w, w.rect.h))
                        rep.log(f"[INFO]   OCR={[(q.text, q.rect.to_xywh()) for q in words][:25]}")
                    except Exception as exc:
                        rep.log(f"[INFO]   OCR error {exc}")
                break
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
