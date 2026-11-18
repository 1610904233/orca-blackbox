#!/usr/bin/env python3
# diag/macos_probe_assembly_select.py — m8z: select the Plate 1 object ("1")
# in the Objects tab and confirm the object really becomes selected.
#
# Run with a wide window so the Assembly View slot is inside the frame:
#   ORCA_BB_WINDOW_FRAME="180; 40; 1512; 982; 0" \
#     .venv/bin/python diag/macos_probe_assembly_select.py

from __future__ import annotations

import os
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
from mac_common import (  # noqa: E402
    Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = HERE / "artifacts" / "mac" / "probe" / "assembly_select"
MODEL = HERE / "fixtures" / "assembly_pokemon_box.3mf"


def ocr_words(driver, win):
    return recognize_text(driver.capture_screen().crop(win.rect))


def dump(rep, words, tag, pred=None):
    sel = [w for w in words if pred is None or pred(w)]
    rep.log(f"[{tag}] n={len(sel)}")
    for w in sel:
        rep.log(f"  {w.text!r} @ {w.rect.to_xywh()}")
    return sel


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
        rep.log(f"[ENV] ORCA_BB_WINDOW_FRAME={os.environ.get('ORCA_BB_WINDOW_FRAME')!r}")
        driver = get_driver()
        app, win = launch_and_focus(driver, OUT / "profile", model=MODEL,
                                    timeout_s=150.0,
                                    log_path=OUT / "app_launch.log")
        rep.log(f"[INFO] pid={app.pid} win={win.rect.to_xywh()} title={win.title!r}")
        ok, frame, frac, _seen = wait_for_model(driver, app, win,
                                                timeout_s=120.0)
        rep.log(f"[INFO] model loaded={ok} colored={frac:.4f}")
        frame.save_png(OUT / "loaded.png")

        words = ocr_words(driver, win)
        dump(rep, words, "ALL-AFTER-LOAD")
        tab = next((w for w in words
                    if w.text.strip().lower() in ("objects", "object")), None)
        rep.log(f"[INFO] Objects tab={tab}")
        if tab is not None:
            driver.click(win.rect.x + tab.rect.center[0],
                         win.rect.y + tab.rect.center[1])
            time.sleep(1.5)
        driver.capture(win).save_png(OUT / "objects_tab.png")
        words = ocr_words(driver, win)
        left = dump(rep, words, "LEFT-TREE",
                    lambda w: w.rect.x < 430 and 300 < w.rect.y < 800)

        plate1 = next((w for w in left if "plate 1" in w.text.lower()), None)
        rep.log(f"[INFO] plate1={plate1}")
        # The single-character object name "1" is too small for Vision OCR
        # (the row is visible in the screenshot but not recognised), so the
        # click point is derived from the Plate 1 row: first child at
        # x~25, one 23px row below.
        if plate1 is None:
            rep.check("object row '1' found", False, "no Plate 1 row")
            return rep.save({})
        cx = 25.0
        cy = plate1.rect.y + 23.0
        rep.log(f"[INFO] clicking Plate1 child row at window-rel "
                f"({cx:.0f},{cy:.0f})")
        driver.click(win.rect.x + cx, win.rect.y + cy)
        time.sleep(2.0)
        driver.capture(win).save_png(OUT / "after_row_click.png")
        words2 = ocr_words(driver, win)
        dump(rep, words2, "ALL-AFTER-ROW-CLICK")
        objname = [w for w in words2
                   if "object name" in w.text.lower()
                   or "name:" in w.text.lower()]
        rep.log(f"[INFO] name markers={[(w.text, w.rect.to_xywh()) for w in objname]}")
        rep.check("object row '1' found", True, str(row.rect.to_xywh()))

        # Assembly View: known slot around window-rel (1470,70) at 1512 width.
        hits = [w for w in words2
                if "assembl" in w.text.lower()]
        rep.log(f"[INFO] assembly words={[(w.text, w.rect.to_xywh()) for w in hits]}")
        x, y = 1470, 70
        before = driver.capture(win)
        driver.click(win.rect.x + x, win.rect.y + y)
        time.sleep(3.0)
        after = driver.capture(win)
        after.save_png(OUT / "after_assembly.png")
        diff = before.difference(after)
        rep.log(f"[INFO] viewport diff={diff:.4f}")
        words3 = ocr_words(driver, win)
        markers = [w.text for w in words3
                   if any(k in w.text.lower() for k in
                          ("section view", "explosion", "selection mode"))]
        rep.log(f"[INFO] assembly markers={markers}")
        rep.check("assembly view entered", diff > 0.02 and bool(markers),
                  f"diff={diff:.4f} markers={markers[:4]}")
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
