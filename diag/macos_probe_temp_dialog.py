#!/usr/bin/env python3
# diag/macos_probe_temp_dialog.py — Temperature calibration defaults on macOS.
#
# #218 needs: Calibration > Temperature -> switch filament type (PLA, ABS/ASA,
# PETG, PCTG, TPU, PA-CF, PET-CF, Custom) and read the Start/End defaults plus
# the fixed disabled Temp step (5).
#
# Dumps the dialog's AX controls and OCR, then clicks each type label by OCR
# and logs the three field values.

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

import ApplicationServices as AS  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "temp_dialog"
TYPES = ("PLA", "ABS", "ASA", "PETG", "PCTG", "TPU", "PA-CF", "PET-CF",
         "Custom")


def _copy(elem, attr):
    err, value = AS.AXUIElementCopyAttributeValue(elem, attr, None)
    return value if err == 0 else None


def _role(elem):
    v = _copy(elem, AS.kAXRoleAttribute)
    return v if isinstance(v, str) else ""


def _text(elem):
    out = []
    for attr in (AS.kAXTitleAttribute, AS.kAXValueAttribute,
                 AS.kAXDescriptionAttribute):
        v = _copy(elem, attr)
        if isinstance(v, str) and v:
            out.append(v)
    return " | ".join(out)


def walk(root, max_depth=14):
    stack = [(root, 0)]
    seen = set()
    keep = [root]
    while stack:
        elem, depth = stack.pop()
        key = id(elem)
        if key in seen:
            continue
        seen.add(key)
        yield elem, depth
        if depth >= max_depth:
            continue
        children = _copy(elem, AS.kAXChildrenAttribute)
        if children:
            keep.extend(children)
            for c in reversed(list(children)):
                stack.append((c, depth + 1))


def dialog_by_title(driver, app, needle, timeout_s=8.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for w in driver.windows_for_pid(app.pid):
            if w.on_screen and needle.lower() in (w.title or "").lower():
                if w.handle is None:
                    driver._attach_ax_window(w)
                return w
        time.sleep(0.3)
    return None


def field_values(dlg):
    vals = []
    for e, _d in walk(dlg.handle):
        if _role(e) == "AXTextField":
            vals.append(str(_copy(e, AS.kAXValueAttribute)))
    return vals


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
        app, win = launch_and_focus(driver, OUT / "profile", model=None,
                                    timeout_s=150.0,
                                    log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(2.0)
        calib = next((c for c in driver.controls(win, max_depth=12)
                      if c.role == "AXMenuBarItem"
                      and c.title.strip().lower() == "calibration"), None)
        driver.click_control(calib)
        time.sleep(0.8)
        row = next((c for c in driver.controls(win, max_depth=14)
                    if c.role == "AXMenuItem"
                    and c.title.strip().lower().startswith("temperature")), None)
        rep.log(f"[INFO] temperature row={row.title if row else None}")
        driver.click_control(row)
        time.sleep(2.0)
        dlg = dialog_by_title(driver, app, "Temperature")
        rep.check("Temperature dialog", dlg is not None,
                  f"rect={dlg.rect.to_xywh() if dlg else None}")
        if dlg is None:
            raise RuntimeError("no temperature dialog")

        rep.log("[INFO] AX controls:")
        for e, d in walk(dlg.handle):
            if _role(e) in ("AXTextField", "AXRadioButton", "AXCheckBox",
                            "AXButton", "AXStaticText", "AXPopUpButton"):
                rep.log(f"  {'  ' * d}{_role(e)} {_text(e)!r}")
        words = recognize_text(driver.capture_screen().crop(dlg.rect))
        rep.log("[INFO] OCR: " + " | ".join(
            f"{w.text!r}@{w.rect.to_xywh()}" for w in words))
        rep.log(f"[INFO] initial fields={field_values(dlg)}")

        for name in TYPES:
            w = next((x for x in words
                      if x.text.strip().upper() == name.upper()), None)
            if w is None:
                rep.log(f"[INFO] type {name!r}: label not found")
                continue
            driver.click(dlg.rect.x + w.rect.center[0],
                         dlg.rect.y + w.rect.center[1])
            time.sleep(0.8)
            rep.log(f"[INFO] type {name!r}: fields={field_values(dlg)}")
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
