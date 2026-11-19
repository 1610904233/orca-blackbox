#!/usr/bin/env python3
# diag/macos_probe_filops.py — physical-filament ops entry points (m4d):
# the F3 mixing-entry "..." menu and the Filaments header buttons.

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

OUT = HERE / "artifacts" / "mac" / "probe" / "filops"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def dump_windows(driver, app, win, tag):
    for w in driver.windows_for_pid(app.pid):
        if not w.on_screen or w.id == win.id or w.rect.area < 300:
            continue
        print(f"[{tag}] window id={w.id} title={w.title!r} "
              f"rect={w.rect.to_xywh()} layer={w.layer}")
        try:
            items = [(c.title, c.enabled) for c in driver.controls(w)
                     if c.role == "AXMenuItem"]
            if items:
                print(f"[{tag}]   menu items={items[:15]}")
        except Exception:
            pass


def sidebar_rows(driver, win):
    words = recognize_text(driver.capture(win))
    return len([w for w in words if w.rect.x < 330 and 400 < w.rect.y < 500
                and any(k in w.text.lower()
                        for k in ("petg", "pla", "silk"))])


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
        rep.log(f"[INFO] rows before={sidebar_rows(driver, win)}")

        # F3 entry options.
        print("[probe] click F3 '...' at (191,558)")
        driver.click(win.rect.x + 191, win.rect.y + 558)
        time.sleep(1.0)
        dump_windows(driver, app, win, "f3-menu")
        words = recognize_text(driver.capture(win))
        print("[probe] f3 OCR=", [(w.text, w.rect.to_xywh()) for w in words
                                  if 480 < w.rect.y < 640 and w.rect.x < 400])
        driver.capture(win).save_png(OUT / "f3_menu.png")
        driver.send_key("escape")
        time.sleep(0.5)

        # Filaments header icon.
        print("[probe] click Filaments header icon at (380,452)")
        driver.click(win.rect.x + 380, win.rect.y + 452)
        time.sleep(1.5)
        dump_windows(driver, app, win, "header")
        driver.capture(win).save_png(OUT / "after_header.png")
        print("[probe] rows after header click=", sidebar_rows(driver, win))
        words = recognize_text(driver.capture(win))
        print("[probe] OCR=", [(w.text, w.rect.to_xywh()) for w in words
                               if w.rect.y > 400 and w.rect.x < 430][:20])
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
