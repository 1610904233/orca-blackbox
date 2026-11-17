#!/usr/bin/env python3
# diag/macos_probe_calib_dialogs.py — dump the other calibration dialogs.
#
# For m8x_212/213/214/221/222 we need each dialog's fields, defaults,
# enabled states and (for PA) the method radio positions.
#
# Opens one dialog per app session, dumps AX controls and OCR, closes with Esc.

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

OUT = HERE / "artifacts" / "mac" / "probe" / "calib_dialogs"


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


def walk(root, max_depth=12):
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


def open_calib(driver, win, label: str) -> bool:
    calib = next((c for c in driver.controls(win, max_depth=12)
                  if c.role == "AXMenuBarItem"
                  and c.title.strip().lower() == "calibration"), None)
    if calib is None or not driver.click_control(calib):
        return False
    time.sleep(0.8)
    row = next((c for c in driver.controls(win, max_depth=14)
                if c.role == "AXMenuItem"
                and c.title.strip().lower() == label.lower()), None)
    if row is None:
        print(f"[calib] menu row {label!r} not found")
        return False
    ok = driver.click_control(row)
    time.sleep(2.0)
    return ok


def dump_dialog(driver, app, win, tag, rep):
    wins = [w for w in driver.windows_for_pid(app.pid)
            if w.on_screen and w.id != win.id and w.rect.area > 800]
    rep.log(f"[{tag}] windows={[(w.id, w.title, w.rect.to_xywh()) for w in wins]}")
    for w in wins:
        if w.handle is None:
            driver._attach_ax_window(w)
        rep.log(f"[{tag}] {w.title!r} controls:")
        for e, d in walk(w.handle):
            if _role(e) in ("AXTextField", "AXCheckBox", "AXRadioButton",
                            "AXButton", "AXStaticText", "AXPopUpButton"):
                rep.log(f"  {'  ' * d}{_role(e)} {_text(e)!r} "
                        f"enabled={_copy(e, AS.kAXEnabledAttribute)}")
        words = recognize_text(driver.capture_screen().crop(w.rect))
        rep.log(f"[{tag}] OCR: " + " | ".join(
            f"{x.text!r}@{x.rect.to_xywh()}" for x in words))
        driver.send_key("escape")
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
        app, win = launch_and_focus(driver, OUT / "profile", model=None,
                                    timeout_s=150.0,
                                    log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(2.0)
        for label, tag in (("Retraction test", "retract212"),
                           ("Max flowrate", "maxflow213"),
                           ("Input Shaping Frequency", "inputshaping214")):
            rep.log(f"[calib] open {label!r}: {open_calib(driver, win, label)}")
            dump_dialog(driver, app, win, tag, rep)
            # close any leftover modal
            driver.send_key("escape")
            time.sleep(0.8)
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
