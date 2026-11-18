#!/usr/bin/env python3
# diag/macos_probe_highflow_slice.py — why does the HF + High Flow slice not
# start?  Capture windows/dialogs before and after the Slice click.

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
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402
import m7b_new_project as m7b  # noqa: E402
import m8d_purifier_gcode as c8d  # noqa: E402
import m8f_nozzle_flow as c8f  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "highflow_slice"


def dump(driver, app, win, tag):
    driver.capture(win).save_png(OUT / f"{tag}.png")
    ws = c8d.ocr_window(driver, win)
    print(f"[{tag}] ocr=" + repr(
        [(w.text, w.rect.to_xywh()) for w in ws
         if w.rect.y < 120 or w.rect.y > 600][:25]))
    for w in driver.windows_for_pid(app.pid):
        if w.id == win.id or not w.on_screen:
            continue
        print(f"[{tag}] win id={w.id} title={w.title!r} "
              f"rect={w.rect.to_xywh()} layer={w.layer}")


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
        app, win = launch_and_focus(driver, OUT / "profile", model=None,
                                    timeout_s=150.0,
                                    log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid}")
        time.sleep(4.0)
        rep.check("add cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        rep.check("HF state", c8f.select_state(driver, win, rep, "HF", "HF",
                                               "High Flow", "probe"))
        dump(driver, app, win, "after_state")
        driver.click(win.rect.x + 1000, win.rect.y + 45)
        time.sleep(4.0)
        dump(driver, app, win, "after_slice_click")
        # If a dialog appeared, dump its OCR and try to find a button.
        from harness.platform.base import Rect
        from harness.platform.macos_ocr import recognize_text
        for w in driver.windows_for_pid(app.pid):
            if w.id == win.id or not w.on_screen or w.layer == 0:
                continue
            driver.capture_screen().save_png(OUT / "dialog_screen.png")
            print("[probe] dialog-ish window:", w.rect.to_xywh(), w.title)
            try:
                for c in driver.controls(w):
                    print("   ctrl", c.role, repr(c.title), repr(c.value),
                          c.rect.to_xywh() if c.rect else None)
            except Exception as exc:  # noqa: BLE001
                print("   controls error", exc)
            words = recognize_text(
                driver.capture_screen().crop(win.rect),
                Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
                     w.rect.w, w.rect.h))
            print("[probe] dialog OCR=",
                  [(x.text, x.rect.to_xywh()) for x in words])
            break
        for i in range(6):
            item = driver.find_control(win, role="AXMenuItem",
                                       title="Export G-code", timeout_s=1)
            print(f"[probe] t={i * 3}s export={None if item is None else item.enabled}")
            if item is not None and item.enabled:
                break
            time.sleep(3.0)
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
