#!/usr/bin/env python3
# diag/macos_probe_add_mix_ratio.py — Add Mix Ratio tab: row combo, ratio bar
# ends, row add/remove (m3t pre-work).

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

OUT = HERE / "artifacts" / "mac" / "probe" / "add_mix_ratio"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
ADD_BTN = (388, 521)


def add_mix_window(driver, app, win):
    for w in driver.windows_for_pid(app.pid):
        if w.on_screen and w.id != win.id and w.layer != 0 \
                and "add mix" in (w.title or "").lower():
            return w
    return None


def dlg_words(driver, win, dlg):
    return recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(dlg.rect.x - win.rect.x, dlg.rect.y - win.rect.y,
             dlg.rect.w, dlg.rect.h))


def show(driver, win, dlg, tag):
    ws = dlg_words(driver, win, dlg)
    rows = [(w.text, w.rect.to_xywh()) for w in ws
            if 200 < w.rect.y < 470]
    print(f"[{tag}] {rows[:30]}")
    return ws


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
        driver.click(win.rect.x + ADD_BTN[0], win.rect.y + ADD_BTN[1])
        time.sleep(1.5)
        dlg = add_mix_window(driver, app, win)
        rep.check("Add Mix window", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({})
        show(driver, win, dlg, "open")

        # Row 1 combo -> pick option 3 (a PLA) to clear the compat banner.
        driver.click(win.rect.x + 566, win.rect.y + 255)
        time.sleep(1.2)
        driver.capture_screen().save_png(OUT / "combo.png")
        driver.click(win.rect.x + 558, win.rect.y + 321)
        time.sleep(1.5)
        ws = dlg_words(driver, win, dlg)
        text = " ".join(w.text for w in ws).lower()
        print("[after-pick] banner=", "cannot be mixed" in text)
        print("[after-pick] full=", [(w.text, w.rect.to_xywh()) for w in ws][:30])
        def pcts():
            ws = dlg_words(driver, win, dlg)
            return ws, [(w.text, w.rect.to_xywh()) for w in ws
                        if "%" in w.text and w.rect.y > 330]

        ws, pct = pcts()
        print("[after-pick] pct=", pct)
        bar_y = (min(w.rect.y for w in ws if "%" in w.text and w.rect.y > 330) - 18)
        driver.click(win.rect.x + 450, win.rect.y + bar_y)
        time.sleep(1.0)
        ws, pct = pcts()
        print("[left-end] pct=", pct)
        print("[left-end] full=", [(w.text, w.rect.to_xywh()) for w in ws][:30])
        bar_y2 = (min(w.rect.y for w in ws if "%" in w.text and w.rect.y > 330) - 18)
        driver.click(win.rect.x + 735, win.rect.y + bar_y2)
        time.sleep(1.0)
        ws, pct = pcts()
        print("[right-end2] pct=", pct)
        driver.capture_screen().save_png(OUT / "ratio_ends.png")

        # Row add/remove: the + sits right of the Filament Selection header.
        ws = dlg_words(driver, win, dlg)
        hdr = next((w for w in ws if "filament selection" in w.text.lower()), None)
        print("[add] header=", hdr.rect.to_xywh() if hdr else None)
        if hdr is not None:
            for i, yy in enumerate((hdr.rect.center[1],
                                    hdr.rect.center[1],
                                    hdr.rect.center[1],
                                    hdr.rect.center[1] - 15)):
                driver.click(win.rect.x + 735, win.rect.y + yy)
                time.sleep(1.0)
                ws = dlg_words(driver, win, dlg)
                combos = [w for w in ws if "petg" in w.text.lower()
                          or "pla" in w.text.lower()]
                print(f"[add {i} y={yy}] n={len(combos)} "
                      f"{[(w.text, w.rect.to_xywh()) for w in combos]}")
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
