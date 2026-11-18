#!/usr/bin/env python3
# diag/macos_probe_filament_combo.py — can the sidebar filament preset combo
# be driven on macOS?  Open the slot-2 combo, dump AX menu items + OCR, try to
# select "Generic ABS", and read the row back.

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

OUT = HERE / "artifacts" / "mac" / "probe" / "filament_combo"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def sidebar_words(driver, win):
    frame = driver.capture(win)
    return frame, recognize_text(frame, Rect(0, 300, 430, 300))


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
        frame, words = sidebar_words(driver, win)
        rows = [w for w in words if any(k in w.text.lower()
                                        for k in ("generic", "silk", "petg",
                                                  "pla", "abs", "pc"))]
        rep.log(f"[INFO] filament rows={[(w.text, w.rect.to_xywh()) for w in rows]}")
        frame.save_png(OUT / "sidebar.png")
        # Two slot columns: slot 1 at x≈58, slot 2 at x≈242 (same row y).
        word = next((w for w in rows
                     if w.rect.x > 200 and "silk" in w.text.lower()), None)
        if word is None:
            rep.check("filament rows found", False, f"rows={rows}")
            return rep.save({})
        rep.log(f"[INFO] click slot-2 combo {word.text!r} @ {word.rect.to_xywh()}")
        driver.click(win.rect.x + word.rect.center[0],
                     win.rect.y + word.rect.center[1])
        time.sleep(1.5)
        driver.capture(win).save_png(OUT / "popup.png")
        rep.log("[INFO] windows:")
        for w in driver.windows_for_pid(app.pid):
            if not w.on_screen or w.rect.area < 200:
                continue
            items = []
            try:
                items = [(c.title, c.enabled) for c in driver.controls(w)
                         if c.role == "AXMenuItem"]
            except Exception:
                pass
            rep.log(f"   id={w.id} {w.title!r} rect={w.rect.to_xywh()} "
                    f"layer={w.layer} items={items[:12]}")
        pop = recognize_text(driver.capture_screen().crop(win.rect))
        hits = [w for w in pop
                if any(k in w.text.lower() for k in ("abs", "pc", "petg",
                                                     "silk", "pla", "generic"))]
        rep.log(f"[INFO] popup words={[(w.text, w.rect.to_xywh()) for w in hits[:30]]}")
        generic = next((w for w in hits
                        if w.text.strip().lower() == "generic"), None)
        if generic is not None:
            rep.log(f"[INFO] click category {generic.text!r} "
                    f"@ {generic.rect.to_xywh()}")
            driver.click(win.rect.x + generic.rect.center[0],
                         win.rect.y + generic.rect.center[1])
            time.sleep(1.2)
            driver.capture(win).save_png(OUT / "submenu.png")
            sub = recognize_text(driver.capture_screen().crop(win.rect))
            sub_hits = [w for w in sub
                        if any(k in w.text.lower() for k in
                               ("abs", "pc", "petg", "pla", "tpu", "asa"))]
            rep.log(f"[INFO] submenu words="
                    f"{[(w.text, w.rect.to_xywh()) for w in sub_hits[:30]]}")
            abs_word = next((w for w in sub_hits
                             if w.text.strip().lower().endswith("abs")), None)
            if abs_word is not None:
                rep.log(f"[INFO] click {abs_word.text!r}")
                driver.click(win.rect.x + abs_word.rect.center[0],
                             win.rect.y + abs_word.rect.center[1])
                time.sleep(2.0)
                driver.capture(win).save_png(OUT / "after_select.png")
                _f2, words2 = sidebar_words(driver, win)
                rep.log(f"[INFO] after select rows="
                        f"{[(w.text, w.rect.to_xywh()) for w in words2 if w.rect.x < 330][:20]}")
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
