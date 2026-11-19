#!/usr/bin/env python3
# diag/macos_probe_merge.py — mixing-entry Options -> Merge with -> physical
# filament (m4d pre-work).

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

OUT = HERE / "artifacts" / "mac" / "probe" / "merge"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def ocr_all(driver, win, ymin=0):
    return [(w.text, w.rect.to_xywh()) for w in
            recognize_text(driver.capture(win)) if w.rect.y >= ymin]


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
        ok, _f, frac, _s = wait_for_model(driver, app, win, timeout_s=120.0)
        rep.check("launch", True, f"pid={app.pid} loaded={ok}")
        # Open the scheme's context menu.
        driver.click(win.rect.x + 191, win.rect.y + 562)
        time.sleep(1.0)
        print("[probe] menu OCR=", ocr_all(driver, win, 550))
        # Hover "Merge with" (window-relative 198,608); the submenu flies out.
        driver.move(win.rect.x + 210, win.rect.y + 608)
        time.sleep(1.5)
        driver.capture(win).save_png(OUT / "merge_hover.png")
        print("[probe] after hover=", ocr_all(driver, win, 550))
        for w in driver.windows_for_pid(app.pid):
            if not w.on_screen or w.id == win.id or w.rect.area < 300:
                continue
            print(f"[probe] window {w.title!r} {w.rect.to_xywh()} "
                  f"layer={w.layer}")
        # Click a physical target in the flyout (right of the menu).
        for (x, y) in ((400, 615), (400, 640)):
            driver.click(win.rect.x + x, win.rect.y + y)
            time.sleep(1.5)
            texts = [t for t, _r in ocr_all(driver, win, 550)]
            print(f"[probe] click ({x},{y}) lower=", texts[:12])
            if not any("f3 50%" in t.lower() for t in texts):
                driver.capture(win).save_png(OUT / "after_merge.png")
                print("[probe] scheme label gone")
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
