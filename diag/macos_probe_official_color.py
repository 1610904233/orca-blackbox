#!/usr/bin/env python3
# diag/macos_probe_official_color.py — official Snapmaker filament colour
# dialog: open, read SKU, pick two swatches, OK/Cancel round trip.

from __future__ import annotations

import re
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

OUT = HERE / "artifacts" / "mac" / "probe" / "official_color"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
CHIP = (220, 418)
# dialog-relative coordinates (380x376 at 1x)
SWATCHES = [(29, 166), (77, 166), (125, 166), (173, 166), (221, 166),
            (29, 194), (77, 194), (125, 194), (173, 194), (221, 194)]
OK_REL = (259, 348)
CANCEL_REL = (120, 348)


def dialog(driver, app, win):
    for w in driver.windows_for_pid(app.pid):
        if w.id == win.id or not w.on_screen or w.layer == 0:
            continue
        if "colors" in (w.title or "").lower():
            continue
        if 300 <= w.rect.w <= 460 and 260 <= w.rect.h <= 460:
            return w
    return None


def dialog_text(driver, win, dlg):
    words = recognize_text(driver.capture_screen().crop(win.rect),
                           Rect(dlg.rect.x - win.rect.x,
                                dlg.rect.y - win.rect.y,
                                dlg.rect.w, dlg.rect.h))
    return " ".join(w.text for w in words)


def sku(text):
    m = re.search(r"sku\s*(\d+)", text, re.I)
    return m.group(1) if m else None


def chip_rgb(driver, win):
    frame = driver.capture(win)
    i = (CHIP[1] * frame.width + CHIP[0]) * 4
    return (frame.data[i + 2], frame.data[i + 1], frame.data[i])


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
        before = chip_rgb(driver, win)
        rep.log(f"[INFO] chip before={before}")
        driver.click(win.rect.x + CHIP[0], win.rect.y + CHIP[1])
        time.sleep(2.0)
        dlg = dialog(driver, app, win)
        rep.check("official dialog", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({})
        text0 = dialog_text(driver, win, dlg)
        rep.log(f"[INFO] text0={text0!r}")
        sku0 = sku(text0)
        rep.check("SKU visible", sku0 is not None, f"sku={sku0}")

        # Pick the second swatch in the first row.
        sx = dlg.rect.x + SWATCHES[1][0]
        sy = dlg.rect.y + SWATCHES[1][1]
        rep.log(f"[INFO] click swatch ({sx},{sy})")
        driver.click(sx, sy)
        time.sleep(1.0)
        text1 = dialog_text(driver, win, dlg)
        sku1 = sku(text1)
        rep.log(f"[INFO] text1={text1!r} sku={sku1}")
        rep.check("swatch changes SKU", sku1 is not None and sku1 != sku0,
                  f"{sku0} -> {sku1}")

        rep.log(f"[INFO] click OK at "
                f"({dlg.rect.x + OK_REL[0]},{dlg.rect.y + OK_REL[1]})")
        driver.click(dlg.rect.x + OK_REL[0], dlg.rect.y + OK_REL[1])
        time.sleep(2.0)
        after_ok = chip_rgb(driver, win)
        rep.log(f"[INFO] chip after OK={after_ok}")
        rep.check("OK closes dialog", dialog(driver, app, win) is None)
        rep.check("chip changed after OK", after_ok != before,
                  f"{before} -> {after_ok}")

        # Reopen and verify the persisted SKU.
        driver.click(win.rect.x + CHIP[0], win.rect.y + CHIP[1])
        time.sleep(2.0)
        dlg2 = dialog(driver, app, win)
        rep.check("reopen dialog", dlg2 is not None)
        if dlg2 is not None:
            text2 = dialog_text(driver, win, dlg2)
            rep.log(f"[INFO] text2={text2!r}")
            rep.check("reopen keeps SKU", sku(text2) == sku1,
                      f"{sku2 if False else sku(text2)} vs {sku1}")
            # Pick a different swatch and Cancel.
            driver.click(dlg2.rect.x + SWATCHES[7][0],
                         dlg2.rect.y + SWATCHES[7][1])
            time.sleep(1.0)
            text3 = dialog_text(driver, win, dlg2)
            sku3 = sku(text3)
            rep.log(f"[INFO] text3={text3!r} sku={sku3}")
            rep.check("second swatch changes SKU",
                      sku3 is not None and sku3 != sku1,
                      f"{sku1} -> {sku3}")
            driver.click(dlg2.rect.x + CANCEL_REL[0],
                         dlg2.rect.y + CANCEL_REL[1])
            time.sleep(2.0)
            after_cancel = chip_rgb(driver, win)
            rep.log(f"[INFO] chip after cancel={after_cancel}")
            rep.check("Cancel closes dialog",
                      dialog(driver, app, win) is None)
            rep.check("Cancel leaves chip unchanged", after_cancel == after_ok,
                      f"{after_ok} -> {after_cancel}")
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
