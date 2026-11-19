#!/usr/bin/env python3
# diag/macos_probe_filops2.py — Filaments-header trash and the mixing-entry
# "..." options menu (Edit/Delete/Merge with), m4d pre-work.

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

OUT = HERE / "artifacts" / "mac" / "probe" / "filops2"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def rows(driver, win):
    words = recognize_text(driver.capture(win))
    return [w for w in words if w.rect.x < 330 and 400 < w.rect.y < 500
            and any(k in w.text.lower() for k in ("petg", "pla", "silk"))]


def dump_windows(driver, app, win, tag):
    for w in driver.windows_for_pid(app.pid):
        if not w.on_screen or w.id == win.id or w.rect.area < 300:
            continue
        print(f"[{tag}] window id={w.id} title={w.title!r} "
              f"rect={w.rect.to_xywh()} layer={w.layer}")
    words = recognize_text(driver.capture(win))
    print(f"[{tag}] OCR=", [(w.text, w.rect.to_xywh()) for w in words
                            if w.rect.x > 150 and 400 < w.rect.y < 650][:25])


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
        rep.log(f"[INFO] rows before={len(rows(driver, win))}")

        # Mixing-entry "..." candidates around the F3 row (y~564).
        for (x, y) in ((9999, 9999),):
            driver.click(win.rect.x + x, win.rect.y + y)
            time.sleep(1.0)
            texts = [w.text for w in recognize_text(driver.capture(win))
                     if "merge" in w.text.lower() or "edit" in w.text.lower()
                     or "delete" in w.text.lower()]
            print(f"[probe] f3 click ({x},{y}) texts={texts}")
            if texts:
                dump_windows(driver, app, win, f"f3-{x}-{y}")
                driver.capture(win).save_png(OUT / f"f3_{x}_{y}.png")
                driver.send_key("escape")
                time.sleep(0.5)
                break

        # Filaments-header trash around (391,452).
        for (x, y) in ((378, 375), (407, 375), (384, 375), (401, 375)):
            driver.click(win.rect.x + x, win.rect.y + y)
            time.sleep(1.5)
            n = len(rows(driver, win))
            print(f"[probe] trash click ({x},{y}) rows={n}")
            dump_windows(driver, app, win, f"trash-{x}-{y}")
            if n != 5:
                driver.capture(win).save_png(OUT / f"trash_{x}_{y}.png")
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
