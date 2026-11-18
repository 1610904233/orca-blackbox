#!/usr/bin/env python3
# diag/macos_probe_mixing_manual.py — Mixing dialog (separate window,
# title 'Color Mixing Match'): Auto -> Manual -> Start Matching -> Confirm.

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

OUT = HERE / "artifacts" / "mac" / "probe" / "mixing_manual"
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


def click(driver, win, word, tag):
    # dlg_words() returns WINDOW-relative boxes (frame = crop of win.rect).
    sx = win.rect.x + word.rect.center[0]
    sy = win.rect.y + word.rect.center[1]
    print(f"[probe] click {tag!r} ({word.text!r}) at ({sx:.0f},{sy:.0f})")
    driver.click(sx, sy)
    time.sleep(1.2)


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
        words = recognize_text(frame)
        entry = next((w for w in words
                      if "color mixing match" in w.text.lower()
                      and w.rect.x < 500), None)
        rep.check("entry", entry is not None)
        if entry is None:
            return rep.save({})
        driver.click(win.rect.x + entry.rect.center[0],
                     win.rect.y + entry.rect.center[1])
        time.sleep(1.5)
        dlg = mixing_window(driver, app, win)
        rep.check("dialog window", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({})
        ws = dlg_words(driver, win, dlg)
        rep.log(f"[INFO] OCR={[(w.text, w.rect.to_xywh()) for w in ws][:25]}")
        rep.log("[INFO] AX controls:")
        try:
            for c in driver.controls(dlg):
                if c.rect is None:
                    continue
                if not (dlg.rect.x <= c.rect.x <= dlg.rect.right
                        and dlg.rect.y <= c.rect.y <= dlg.rect.bottom):
                    continue
                rep.log(f"   {c.role} title={c.title!r} "
                        f"desc={c.description!r} value={str(c.value)[:30]!r} "
                        f"rect={c.rect.to_xywh()} actions={c.actions}")
        except Exception as exc:
            rep.log(f"   controls error {exc}")

        auto = find(ws, "auto")
        rep.log(f"[INFO] auto={auto.text if auto else None}")
        if auto is not None:
            click(driver, win, auto, "Auto combo")
            ws = dlg_words(driver, win, dlg)
            rep.log("[INFO] after combo=" + repr(
                [(w.text, w.rect.to_xywh()) for w in ws
                 if 80 < w.rect.y < 200][:20]))
            driver.capture_screen().save_png(OUT / "combo.png")
            manual = find(ws, "manual")
            rep.log(f"[INFO] manual={manual.text if manual else None}")
            if manual is not None:
                click(driver, win, manual, "Manual")
                ws = dlg_words(driver, win, dlg)
                rep.log("[INFO] after manual=" + repr(
                    [(w.text, w.rect.to_xywh()) for w in ws
                     if w.rect.y < 220][:20]))
                start = find(ws, "start matching")
                rep.check("start matching", start is not None)
                if start is not None:
                    click(driver, win, start, "Start Matching")
                    time.sleep(5.0)
                    ws = dlg_words(driver, win, dlg)
                    rep.log("[INFO] after match=" + repr(
                        [(w.text, w.rect.to_xywh()) for w in ws][:30]))
                    driver.capture_screen().save_png(OUT / "matched.png")
                    rematch = find(ws, "rematch")
                    confirm = find(ws, "confirm")
                    rep.log(f"[INFO] rematch={rematch} confirm={confirm}")
                    if confirm is not None:
                        click(driver, win, confirm, "Confirm")
                        time.sleep(2.0)
                        gone = mixing_window(driver, app, win) is None
                        rep.check("Confirm closes dialog", gone)
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
