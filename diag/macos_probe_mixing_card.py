#!/usr/bin/env python3
# diag/macos_probe_mixing_card.py — Manual filament card: row count and the
# add/remove icon buttons (m3m pre-work).

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

OUT = HERE / "artifacts" / "mac" / "probe" / "mixing_card"
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


def card_rows(words):
    return [w for w in words if 190 < w.rect.y < 330
            and ("petg" in w.text.lower() or "silk" in w.text.lower()
                 or "pla" in w.text.lower())]


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
        click_word(driver, win, find(ws, "auto"))
        ws = dlg_words(driver, win, dlg)
        click_word(driver, win, find(ws, "manual"))
        time.sleep(1.0)
        ws = dlg_words(driver, win, dlg)
        rows = card_rows(ws)
        rep.log(f"[INFO] card rows ({len(rows)}): "
                f"{[(w.text, w.rect.to_xywh()) for w in rows]}")
        driver.capture(win).save_png(OUT / "manual.png")
        # Hover candidate add/remove icon spots near the card top-right.
        for (x, y) in ((664, 228), (682, 228), (700, 228), (664, 210),
                       (682, 210), (700, 210)):
            driver.move(win.rect.x + x, win.rect.y + y)
            time.sleep(2.0)
            words = recognize_text(
                driver.capture_screen(),
                Rect(win.rect.x + x - 10, win.rect.y + y + 5, 300, 60))
            text = " ".join(w.text for w in words).strip()
            rep.log(f"[HOVER] ({x},{y}) -> {text!r}")
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
