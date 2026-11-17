#!/usr/bin/env python3
# diag/macos_probe_plate_settings.py — Plate Settings dialog on macOS.
#
# Entry: plate rail "Customize current plate" at (1070,300).  Dumps the dialog
# (title, AXTextFields, buttons, OCR), then tries renaming to B@#1 and OK.

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

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import joined_text, recognize_text  # noqa: E402
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "plate_settings"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"
CUSTOMIZE_XY = (1070, 300)


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
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(3.0)
        driver.move(win.rect.x + CUSTOMIZE_XY[0],
                    win.rect.y + CUSTOMIZE_XY[1])
        time.sleep(1.2)
        tip = " ".join(w.text for w in recognize_text(
            driver.capture_screen(),
            Rect(win.rect.x + CUSTOMIZE_XY[0] + 5,
                 win.rect.y + CUSTOMIZE_XY[1] - 45, 300, 100)))
        rep.log(f"[INFO] tooltip={tip!r}")
        driver.click(win.rect.x + CUSTOMIZE_XY[0],
                     win.rect.y + CUSTOMIZE_XY[1])
        time.sleep(2.0)
        wins = [w for w in driver.windows_for_pid(app.pid) if w.on_screen]
        rep.log(f"[INFO] windows={[(w.id, w.title, w.rect.to_xywh()) for w in wins]}")
        dlg = next((w for w in wins if w.id != win.id and w.rect.area > 1000),
                   None)
        rep.check("dialog", dlg is not None,
                  f"title={dlg.title if dlg else None}")
        if dlg is None:
            raise RuntimeError("no Plate Settings dialog")
        if dlg.handle is None:
            driver._attach_ax_window(dlg)
        rep.log(f"[INFO] dialog title={dlg.title!r} rect={dlg.rect.to_xywh()}")
        for e, d in walk(dlg.handle):
            if _role(e) in ("AXTextField", "AXButton", "AXStaticText",
                            "AXCheckBox", "AXRadioButton", "AXPopUpButton"):
                rep.log(f"  {'  ' * d}{_role(e)} {_text(e)!r}")
        crop = driver.capture_screen().crop(dlg.rect)
        crop.save_png(OUT / "dialog.png")
        rep.log(f"[OCR] {joined_text(recognize_text(crop))[:400]}")
        fields = [e for e, _d in walk(dlg.handle) if _role(e) == "AXTextField"]
        rep.check("name field", bool(fields),
                  f"values={[str(_copy(f, AS.kAXValueAttribute)) for f in fields]}")
        if fields:
            ok = AS.AXUIElementSetAttributeValue(
                fields[0], AS.kAXValueAttribute, "B@#1") == 0
            time.sleep(0.5)
            rep.log(f"[INFO] set B@#1 ok={ok} readback="
                    f"{_copy(fields[0], AS.kAXValueAttribute)!r}")
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
