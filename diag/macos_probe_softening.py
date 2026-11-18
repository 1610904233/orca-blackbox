#!/usr/bin/env python3
# diag/macos_probe_softening.py — set the slot-1 softening temperature in the
# Material settings dialog (AXTextField) and check whether it reaches the
# sliced gcode (temperature_vitrification / SET_PURIFIER_MODE).

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

import ApplicationServices as AS  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos import _ax_set  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
    wait_for_model,
)
import m7b_new_project as m7b  # noqa: E402
import m8d_purifier_gcode as c8d  # noqa: E402
import mac_gcode  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "softening"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def open_editor(driver, app, win):
    driver.click(win.rect.x + 196, win.rect.y + 418)
    time.sleep(1.0)
    driver.click(win.rect.x + 198, win.rect.y + 446)
    time.sleep(2.0)
    for w in driver.windows_for_pid(app.pid):
        if w.on_screen and "material settings" in (w.title or "").lower():
            return w
    return None


def vitr_field(driver, dlg):
    for c in driver.controls(dlg):
        if c.role == "AXTextField" and c.rect is not None:
            if c.rect.x < 900 and 300 <= c.rect.y <= 340:
                return c
    return None


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    work = OUT / "work"
    work.mkdir(parents=True)
    model = work / "soft_mixed.3mf"
    shutil.copy2(MODEL, model)
    gcode = work / "soft.gcode"
    rep = Reporter(OUT)
    driver = None
    app = None
    win = None
    code = 2
    try:
        driver = get_driver()
        app, win = launch_and_focus(driver, OUT / "profile", model=model,
                                    timeout_s=150.0,
                                    log_path=OUT / "app_launch.log")
        ok, _f, _frac, _s = wait_for_model(driver, app, win, timeout_s=120.0)
        rep.check("launch", True, f"pid={app.pid} loaded={ok}")
        item = driver.find_control(win, role="AXMenuItem",
                                   title="Delete All", timeout_s=3)
        driver.click_control(item)
        time.sleep(2.0)
        rep.check("add cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        dlg = open_editor(driver, app, win)
        rep.check("material dialog", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({})
        fld = vitr_field(driver, dlg)
        rep.log(f"[INFO] vitr field={fld.rect.to_xywh() if fld else None} "
                f"value={fld.value if fld else None}")
        if fld is not None and fld.handle is not None:
            ok_set = _ax_set(fld.handle, AS.kAXValueAttribute, "45")
            rep.log(f"[INFO] AXSetValue 45 -> {ok_set}")
            time.sleep(0.5)
            # Commit the edit: focus the field with a real click, select all,
            # type the value, then Tab out (AXSetValue alone may not fire the
            # wx text-change event).
            driver.click(*fld.rect.center)
            time.sleep(0.3)
            driver.send_key("a", modifiers=("cmd",))
            driver.send_text("45")
            time.sleep(0.5)
            driver.send_key("tab")
            time.sleep(1.0)
            fld2 = vitr_field(driver, dlg)
            rep.log(f"[INFO] readback after typing={fld2.value if fld2 else None}")
        # Close via the window close button.
        driver.close_window(dlg)
        time.sleep(1.5)
        roots = [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"]
        rep.check("slice+export", slice_and_export(driver, win, rep, gcode,
                                                   roots))
        if gcode.exists():
            data = gcode.read_bytes()
            txt = data.decode("utf-8", "replace")
            vitr = re.search(r"^; temperature_vitrification = (.*)$", txt, re.M)
            pa = mac_gcode.purifier_params(data)
            rep.log(f"[INFO] vitr={vitr.group(1) if vitr else None} "
                    f"purifier={pa}")
        # If the close discarded the edit, inspect the bookmark/save path.
        if gcode.exists() and "45,45,45,45,45" not in \
                gcode.read_text(encoding="utf-8", errors="replace"):
            dlg = open_editor(driver, app, win)
            if dlg is not None:
                fld = vitr_field(driver, dlg)
                driver.click(*fld.rect.center)
                driver.send_key("a", modifiers=("cmd",))
                driver.send_text("45")
                driver.send_key("tab")
                time.sleep(0.5)
                # bookmark / save-as button at the dialog top-right
                driver.click(dlg.rect.x + 594, dlg.rect.y + 44)
                time.sleep(1.5)
                driver.capture_screen().save_png(OUT / "bookmark.png")
                ws = c8d.ocr_window(driver, win)
                rep.log("[INFO] after bookmark=" + repr(
                    [(w.text, w.rect.to_xywh()) for w in ws
                     if w.rect.y > 80][:40]))
                for w in driver.windows_for_pid(app.pid):
                    if w.on_screen and w.id != win.id:
                        rep.log(f"[WINDOW] {w.title!r} {w.rect.to_xywh()} "
                                f"layer={w.layer}")
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
