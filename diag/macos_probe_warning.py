#!/usr/bin/env python3
# diag/macos_probe_warning.py — m4d: trash-delete down to the scheme-referenced
# filament, dump the Warning dialog and test Cancel/OK.

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
from mac_common import Reporter, close_app, launch_and_focus, wait_for_model  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "warning"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
TRASH = (378, 375)


def rows(driver, win):
    words = recognize_text(driver.capture(win))
    return len([w for w in words if w.rect.x < 330 and 400 < w.rect.y < 500
                and any(k in w.text.lower()
                        for k in ("petg", "pla", "silk"))])


def scheme_present(driver, win):
    return any("f3 50%" in w.text.lower()
               for w in recognize_text(driver.capture(win)))


def dump_windows(driver, app, win, tag):
    for w in driver.windows_for_pid(app.pid):
        if not w.on_screen or w.id == win.id or w.rect.area < 300:
            continue
        print(f"[{tag}] window id={w.id} title={w.title!r} "
              f"rect={w.rect.to_xywh()} layer={w.layer}")
        try:
            words = recognize_text(
                driver.capture_screen().crop(win.rect),
                Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
                     w.rect.w, w.rect.h))
            print(f"[{tag}] OCR=", [(q.text, q.rect.to_xywh()) for q in words][:25])
        except Exception as exc:
            print(f"[{tag}] OCR error {exc}")


def click_trash(driver, win):
    driver.click(win.rect.x + TRASH[0], win.rect.y + TRASH[1])
    time.sleep(1.5)


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
        print("[probe] rows0=", rows(driver, win), "scheme=", scheme_present(driver, win))
        click_trash(driver, win); print("[probe] rows1=", rows(driver, win))
        click_trash(driver, win); print("[probe] rows2=", rows(driver, win),
                                        "scheme=", scheme_present(driver, win))
        click_trash(driver, win)
        print("[probe] rows3=", rows(driver, win), "scheme=", scheme_present(driver, win))
        dump_windows(driver, app, win, "warning")
        driver.capture_screen().save_png(OUT / "warning.png")
        # Try Cancel first.
        for w in driver.windows_for_pid(app.pid):
            if not w.on_screen or w.id == win.id or w.layer == 0:
                continue
            words = recognize_text(
                driver.capture_screen().crop(win.rect),
                Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
                     w.rect.w, w.rect.h))
            cancel = next((q for q in words
                           if q.text.strip().lower() == "cancel"), None)
            print("[probe] cancel=", cancel)
            if cancel is not None:
                driver.click(win.rect.x + cancel.rect.center[0],
                             win.rect.y + cancel.rect.center[1])
                time.sleep(1.5)
                print("[probe] after cancel rows=", rows(driver, win),
                      "scheme=", scheme_present(driver, win))
                break
        # Delete again, then OK if present.
        click_trash(driver, win)
        dump_windows(driver, app, win, "warning2")
        for w in driver.windows_for_pid(app.pid):
            if not w.on_screen or w.id == win.id or w.layer == 0:
                continue
            words = recognize_text(
                driver.capture_screen().crop(win.rect),
                Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
                     w.rect.w, w.rect.h))
            okb = next((q for q in words
                        if q.text.strip().lower() in ("ok", "yes", "continue")), None)
            print("[probe] ok=", okb)
            if okb is not None:
                driver.click(win.rect.x + okb.rect.center[0],
                             win.rect.y + okb.rect.center[1])
                time.sleep(1.5)
                print("[probe] after ok rows=", rows(driver, win),
                      "scheme=", scheme_present(driver, win))
                break
        # Final delete down to 1.
        click_trash(driver, win)
        print("[probe] rows_final=", rows(driver, win),
              "scheme=", scheme_present(driver, win))
        click_trash(driver, win)
        print("[probe] rows_after_extra=", rows(driver, win))
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
