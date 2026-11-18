#!/usr/bin/env python3
# diag/macos_probe_filament_editor.py — open the filament "Material settings"
# dialog on macOS and dump its AX controls + OCR (m8x_123 pre-work).

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
import m8d_purifier_gcode as c8d  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "filament_editor"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def buttons_near(driver, win, y0, y1):
    out = []
    try:
        for c in driver.controls(win):
            if c.role == "AXButton" and c.rect is not None \
                    and y0 <= c.rect.y <= y1 and c.rect.x < 300:
                out.append((c.title, c.description, c.rect.to_xywh()))
    except Exception:
        pass
    return out


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
        rep.log(f"[INFO] buttons row1={buttons_near(driver, win, 405, 435)}")
        # Click the small edit button right of the preset combo.
        for pt in ((196, 418), (190, 418), (198, 414), (205, 418)):
            rep.log(f"[INFO] click edit candidate {pt}")
            driver.click(win.rect.x + pt[0], win.rect.y + pt[1])
            time.sleep(1.2)
            ws = c8d.ocr_window(driver, win)
            rows = [(w.text, w.rect.to_xywh()) for w in ws
                    if w.rect.y > 400 and w.rect.x < 500]
            rep.log(f"[INFO] after {pt}: {rows[:15]}")
            if any("material" in t.lower() or "edit" in t.lower()
                   for t, _r in rows):
                break
        driver.capture(win).save_png(OUT / "after_click.png")
        # The row menu offers Edit / Delete / Merge with; Edit opens the
        # filament preset editor.
        driver.click(win.rect.x + 198, win.rect.y + 446)
        time.sleep(2.0)
        driver.capture(win).save_png(OUT / "edit_dialog.png")
        driver.capture_screen().save_png(OUT / "edit_dialog_screen.png")
        dlg = None
        for w in driver.windows_for_pid(app.pid):
            if w.on_screen and "material settings" in (w.title or "").lower():
                dlg = w
                break
        rep.log(f"[INFO] material dialog={dlg.rect.to_xywh() if dlg else None}")
        if dlg is not None:
            ws = recognize_text(
                driver.capture_screen().crop(win.rect),
                Rect(dlg.rect.x - win.rect.x, dlg.rect.y - win.rect.y,
                     dlg.rect.w, dlg.rect.h))
            rep.log("[INFO] dialog OCR=" + repr(
                [(w.text, w.rect.to_xywh()) for w in ws]))
            for c in driver.controls(dlg):
                if c.rect is None or c.role not in (
                        "AXTextField", "AXButton", "AXPopUpButton",
                        "AXCheckBox"):
                    continue
                if not (dlg.rect.x <= c.rect.x <= dlg.rect.right
                        and dlg.rect.y <= c.rect.y <= dlg.rect.bottom):
                    continue
                rep.log(f"   {c.role} title={c.title!r} "
                        f"desc={c.description!r} value={str(c.value)[:30]!r} "
                        f"rect={c.rect.to_xywh()}")
        # Dump any popup/dialog windows.
        for w in driver.windows_for_pid(app.pid):
            if w.id == win.id or not w.on_screen or w.rect.area < 400:
                continue
            rep.log(f"[WINDOW] id={w.id} title={w.title!r} "
                    f"rect={w.rect.to_xywh()} layer={w.layer}")
            try:
                for c in driver.controls(w):
                    if c.role in ("AXButton", "AXTextField", "AXStaticText",
                                  "AXPopUpButton", "AXCheckBox", "AXRadioButton"):
                        rep.log(f"   {c.role} title={c.title!r} "
                                f"value={str(c.value)[:40]!r} "
                                f"rect={c.rect.to_xywh() if c.rect else None}")
            except Exception as exc:  # noqa: BLE001
                rep.log(f"   controls error: {exc}")
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
