#!/usr/bin/env python3
# diag/macos_probe_silk_scroll.py — after switching slot 2 to Generic ABS,
# can the Snapmaker vendor submenu be scrolled to find "PLA Silk"?

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
import m8d_purifier_gcode as c8d  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "silk_scroll"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def popup_windows(driver, app, win):
    return [w for w in driver.windows_for_pid(app.pid)
            if w.id != win.id and w.on_screen and w.layer != 0
            and w.rect.area > 3000]


def dump(driver, win, tag):
    words = c8d.ocr_window(driver, win)
    rows = [(w.text, w.rect.to_xywh()) for w in words
            if w.rect.x > 450 and w.rect.y > 430]
    print(f"[{tag}] {rows[:40]}")
    return words


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
        rep.check("launch", True, f"pid={app.pid} loaded={ok} frac={frac:.3f}")

        print("[probe] slot2 -> ABS:", c8d.select_slot2_preset(
            driver, win, rep, "ABS"))
        # Reopen the combo and the Snapmaker vendor.
        words = c8d.ocr_window(driver, win)
        combo = next((w for w in words
                      if 200 < w.rect.x < 400 and 400 <= w.rect.y <= 435), None)
        print("[probe] combo:", combo)
        driver.click(win.rect.x + combo.rect.center[0],
                     win.rect.y + combo.rect.center[1])
        time.sleep(1.2)
        words = c8d.ocr_window(driver, win)
        vendor = next((w for w in words
                       if w.text.strip().lower() == "snapmaker"
                       and 200 < w.rect.x < 490 and w.rect.y > 440), None)
        print("[probe] vendor:", vendor)
        driver.click(win.rect.x + vendor.rect.center[0],
                     win.rect.y + vendor.rect.center[1])
        time.sleep(1.2)
        dump(driver, win, "before-scroll")
        pops = popup_windows(driver, app, win)
        print("[probe] popups:", [(w.rect.to_xywh(), w.layer) for w in pops])
        # Rightmost popup is the type submenu.
        sub = max(pops, key=lambda w: w.rect.x)
        cx, cy = sub.rect.center
        print(f"[probe] wheel at screen ({cx:.0f},{cy:.0f})")
        for i in range(30):
            driver.wheel(cx, cy, -3)
            time.sleep(0.35)
            words = c8d.ocr_window(driver, win)
            silk = [w for w in words
                    if "silk" in w.text.lower() and w.rect.x > 450]
            print(f"[scroll-down-{i + 1}] silk={[(w.text, w.rect.to_xywh()) for w in silk]}")
            if silk:
                print("[probe] FOUND silk after down", i + 1)
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
