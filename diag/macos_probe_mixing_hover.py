#!/usr/bin/env python3
# diag/macos_probe_mixing_tooltip.py — after a Manual match, hover the Color
# Mapping rows and look for the Delta-E tooltip (m3l/m3s pre-work).

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

OUT = HERE / "artifacts" / "mac" / "probe" / "mixing_tooltip"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def mixing_window(driver, app, win):
    for w in driver.windows_for_pid(app.pid):
        if (w.on_screen and w.id != win.id and w.layer != 0
                and "color mixing match" in (w.title or "").lower()):
            return w
    return None


def dlg_words(driver, win, dlg):
    return recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(dlg.rect.x - win.rect.x, dlg.rect.y - win.rect.y,
             dlg.rect.w, dlg.rect.h))


def find(words, needle):
    for w in words:
        if needle in w.text.lower():
            return w
    return None


def click_word(driver, win, word):
    driver.click(win.rect.x + word.rect.center[0],
                 win.rect.y + word.rect.center[1])
    time.sleep(1.0)


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
        entry = next((w for w in recognize_text(frame)
                      if "color mixing match" in w.text.lower()
                      and w.rect.x < 500), None)
        click_word(driver, win, entry)
        time.sleep(1.5)
        dlg = mixing_window(driver, app, win)
        rep.check("dialog", dlg is not None)
        ws = dlg_words(driver, win, dlg)
        auto = find(ws, "auto")
        click_word(driver, win, auto)
        ws = dlg_words(driver, win, dlg)
        click_word(driver, win, find(ws, "manual"))
        # Hover dialog controls before matching (m3s).
        for (hx, hy, tag) in ((802, 186, "plus"), (784, 186, "minus"),
                              (650, 117, "start"), (482, 119, "mode")):
            driver.move(win.rect.x + hx, win.rect.y + hy)
            time.sleep(2.5)
            words = recognize_text(
                driver.capture_screen(),
                Rect(win.rect.x + hx - 20, win.rect.y + hy + 8, 340, 70))
            rep.log(f"[HOVER {tag}] {win.rect.to_xywh()} -> "
                    f"{' '.join(w.text for w in words).strip()!r}")
        return rep.save({"stage": "hover-only"})
        ws = dlg_words(driver, win, dlg)
        click_word(driver, win, find(ws, "start matching"))
        time.sleep(6.0)
        driver.capture(win).save_png(OUT / "matched.png")
        ws = dlg_words(driver, win, dlg)
        rows = [(w.text, w.rect) for w in ws if w.rect.y > 680]
        rep.log(f"[INFO] lower band={[(t, r.to_xywh()) for t, r in rows][:20]}")
        # Hover a few points in the mapping rows and OCR the nearby area.
        for (hx, hy) in ((400, 725), (420, 725), (450, 725), (500, 725),
                         (550, 725), (600, 725), (400, 705), (450, 705)):
            driver.move(win.rect.x + hx, win.rect.y + hy)
            time.sleep(2.5)
            words = recognize_text(
                driver.capture_screen(),
                Rect(win.rect.x + hx - 20, win.rect.y + hy - 10, 420, 70))
            text = " ".join(w.text for w in words).strip()
            rep.log(f"[HOVER] ({hx},{hy}) -> {text!r}")
            if "color difference" in text.lower() or "ae=" in text.lower():
                driver.capture_screen().save_png(OUT / "tooltip.png")
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
