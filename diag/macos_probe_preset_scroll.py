#!/usr/bin/env python3
# diag/macos_probe_preset_scroll.py — three ways to move the custom Snapmaker
# preset submenu to PLA Rainbow: type-ahead, wheel variants, scrollbar drag.

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

import Quartz  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import Reporter, close_app, launch_and_focus, wait_for_model  # noqa: E402
import m8d_purifier_gcode as c8d  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "preset_scroll"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def drag(x0, y0, x1, y1, steps=14):
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    p0 = Quartz.CGPointMake(x0, y0)
    ev = Quartz.CGEventCreateMouseEvent(src, Quartz.kCGEventMouseMoved, p0,
                                        Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
    time.sleep(0.1)
    ev = Quartz.CGEventCreateMouseEvent(src, Quartz.kCGEventLeftMouseDown, p0,
                                        Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
    time.sleep(0.05)
    for i in range(1, steps + 1):
        p = Quartz.CGPointMake(x0 + (x1 - x0) * i / steps,
                               y0 + (y1 - y0) * i / steps)
        ev = Quartz.CGEventCreateMouseEvent(
            src, Quartz.kCGEventLeftMouseDragged, p,
            Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.03)
    ev = Quartz.CGEventCreateMouseEvent(
        src, Quartz.kCGEventLeftMouseUp, Quartz.CGPointMake(x1, y1),
        Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
    time.sleep(0.5)


def open_snapmaker_submenu(driver, win):
    ws = c8d.ocr_window(driver, win)
    combo = next((w for w in ws
                  if 200 < w.rect.x < 400 and 400 <= w.rect.y <= 435), None)
    driver.click(win.rect.x + combo.rect.center[0],
                 win.rect.y + combo.rect.center[1])
    time.sleep(1.2)
    ws = c8d.ocr_window(driver, win)
    right = [(w.text, w.rect) for w in ws
             if w.rect.x > 430 and w.rect.y > 430]
    if not any(any(k in t.lower() for k in ("silk", "rainbow", "starlight"))
               for t, _r in right):
        vendor = next((w for w in ws
                       if w.text.strip().lower() == "snapmaker"
                       and 200 < w.rect.x < 490 and w.rect.y > 440), None)
        if vendor is None:
            return None
        driver.click(win.rect.x + vendor.rect.center[0],
                     win.rect.y + vendor.rect.center[1])
        time.sleep(1.0)
    pops = [w for w in driver.windows_for_pid(win.pid)
            if w.id != win.id and w.on_screen and w.layer != 0
            and w.rect.area > 3000]
    return max(pops, key=lambda w: w.rect.x) if pops else None


def find_rainbow(driver, win):
    ws = c8d.ocr_window(driver, win)
    return next((w for w in ws if "rainbow" in w.text.lower()
                 and w.rect.x > 430 and w.rect.y > 430), None)


def slot2_row(driver, win):
    return [w.text for w in c8d.ocr_window(driver, win)
            if 200 < w.rect.x < 400 and 400 <= w.rect.y <= 435]


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
        ok, _f, _frac, _s = wait_for_model(driver, app, win, timeout_s=120.0)
        rep.check("launch", True, f"pid={app.pid} loaded={ok}")

        # Method 1: type-ahead.
        sub = open_snapmaker_submenu(driver, win)
        rep.check("submenu open (type-ahead)", sub is not None,
                  sub.rect.to_xywh() if sub else "")
        if sub is not None:
            driver.send_text("PLA Rainbow")
            time.sleep(1.0)
            driver.send_key("return")
            time.sleep(2.0)
            row = slot2_row(driver, win)
            rep.log(f"[INFO] after type-ahead row={row}")
            rep.check("type-ahead selects Rainbow",
                      any("rainbow" in t.lower() for t in row), str(row))
            if any("rainbow" in t.lower() for t in row):
                return rep.save({"method": "type-ahead"})
            driver.send_key("escape")
            time.sleep(0.8)

        # Method 2: wheel variants.
        for label, (wx, wy, notch) in (
                ("left-edge", (None, None, -6)),
                ("right-edge", (None, None, -6)),
                ("big-left", (None, None, -20))):
            sub = open_snapmaker_submenu(driver, win)
            if sub is None:
                rep.log(f"[INFO] {label}: submenu missing")
                continue
            if "left" in label:
                x = sub.rect.x + 6
            else:
                x = sub.rect.right - 6
            y = sub.rect.y + 40
            rep.log(f"[INFO] {label}: wheel ({x:.0f},{y:.0f}) notch={notch}")
            for i in range(8):
                driver.wheel(x, y, notch)
                time.sleep(0.5)
                found = find_rainbow(driver, win)
                if found is not None:
                    rep.log(f"[INFO] {label}: found at step {i}")
                    break
            found = find_rainbow(driver, win)
            rep.log(f"[INFO] {label}: found={found}")
            if found is not None:
                driver.click(win.rect.x + found.rect.center[0],
                             win.rect.y + found.rect.center[1])
                time.sleep(2.0)
                row = slot2_row(driver, win)
                rep.log(f"[INFO] {label}: row={row}")
                rep.check(f"wheel {label} selects Rainbow",
                          any("rainbow" in t.lower() for t in row), str(row))
                if any("rainbow" in t.lower() for t in row):
                    return rep.save({"method": label})
            driver.send_key("escape")
            time.sleep(1.0)

        # Method 3: scrollbar drag.
        sub = open_snapmaker_submenu(driver, win)
        if sub is not None:
            x = sub.rect.right - 5
            rep.log(f"[INFO] drag scrollbar at x={x:.0f} "
                    f"from y={sub.rect.y + 30:.0f} to y={sub.rect.bottom - 20:.0f}")
            for i in range(4):
                drag(x, sub.rect.y + 30, x, sub.rect.bottom - 20)
                found = find_rainbow(driver, win)
                rep.log(f"[INFO] drag {i}: found={found}")
                if found is not None:
                    driver.click(win.rect.x + found.rect.center[0],
                                 win.rect.y + found.rect.center[1])
                    time.sleep(2.0)
                    row = slot2_row(driver, win)
                    rep.check("drag selects Rainbow",
                              any("rainbow" in t.lower() for t in row),
                              str(row))
                    return rep.save({"method": "drag"})
        rep.check("no method found Rainbow", False, "")
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
