#!/usr/bin/env python3
# diag/macos_probe_assembly.py — m8z: objects tab + Assembly View entry.
#
# Loads fixtures/assembly_pokemon_box.3mf, verifies object rows can be
# selected, then scans toolbar tooltips for an Assembly View slot and tries
# clicking it (viewport must change).

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
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "assembly"
MODEL = HERE / "fixtures" / "assembly_pokemon_box.3mf"


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
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(4.0)
        frame0 = driver.capture(win)
        frame0.save_png(OUT / "loaded.png")

        words = recognize_text(driver.capture_screen().crop(win.rect))
        tab = next((w for w in words if w.text.strip() == "Objects"), None)
        rep.log(f"[INFO] Objects tab={tab}")
        if tab is not None:
            driver.click(win.rect.x + tab.rect.center[0],
                         win.rect.y + tab.rect.center[1])
            time.sleep(1.2)
        words = recognize_text(driver.capture_screen().crop(win.rect))
        rows = [w for w in words
                if w.rect.x < 430 and 380 < w.rect.y < 760 and len(w.text) > 2]
        rep.log(f"[INFO] left rows sample={[(w.text, w.rect.to_xywh()) for w in rows[:12]]}")

        hits = []
        for y in (40, 50, 60, 70, 80):
            for x in range(430, 1161, 15):
                driver.move(win.rect.x + x, win.rect.y + y)
                time.sleep(1.0)
                tip = " ".join(w.text for w in recognize_text(
                    driver.capture_screen(),
                    Rect(win.rect.x + x - 100, win.rect.y + y + 10, 420, 80)))
                low = tip.lower()
                if "assembl" in low:
                    hits.append((x, y, tip.strip()))
                    rep.log(f"[TIP] x={x} y={y}: {tip!r}")
        rep.check("assembly view slot found", bool(hits))
        if hits:
            x, y, _tip = hits[0]
            driver.click(win.rect.x + x, win.rect.y + y)
            time.sleep(3.0)
            frame1 = driver.capture(win)
            frame1.save_png(OUT / "after_assembly.png")
            diff = frame0.difference(frame1)
            rep.log(f"[INFO] viewport diff after assembly click={diff:.4f}")
            rep.check("assembly view toggles (viewport change)", diff > 0.02,
                      f"diff={diff:.4f}")
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
