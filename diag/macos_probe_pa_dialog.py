#!/usr/bin/env python3
# diag/macos_probe_pa_dialog.py — explore PA Calibration on macOS.
#
# Windows #207 needs: Calibration > Pressure advance -> PA Calibration dialog
# -> invalid Start PA input (abc / empty / "1a！@") -> every OK raises a
# warning ("Please input valid values") and no model is generated, while the
# PA dialog stays open.
#
# This probe dumps the macOS dialog's AX controls and OCR, then tries one
# invalid value and logs any warning window.

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
from harness.platform.macos_ocr import joined_text, recognize_text  # noqa: E402
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "pa_dialog"


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


def _rect(elem):
    try:
        pos = _copy(elem, AS.kAXPositionAttribute)
        size = _copy(elem, AS.kAXSizeAttribute)
        return (pos.origin.x, pos.origin.y, size.width, size.height)
    except Exception:
        return None


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
        rep.check("Calibration menu", calib is not None)
        driver.click_control(calib)
        time.sleep(0.8)
        pa = next((c for c in driver.controls(win, max_depth=14)
                   if c.role == "AXMenuItem"
                   and "pressure advance" in c.title.lower()), None)
        rep.check("Pressure advance row", pa is not None,
                  f"rect={pa.rect if pa else None}")
        driver.click_control(pa)
        time.sleep(2.0)

        rep.log(f"[INFO] windows="
                f"{[(w.id, w.title, w.rect.to_xywh(), w.layer) for w in driver.windows_for_pid(app.pid) if w.on_screen]}")
        dlg = dialog_by_title(driver, app, "PA Calibration", timeout_s=8.0) \
            or dialog_by_title(driver, app, "Pressure", timeout_s=2.0)
        rep.check("PA dialog", dlg is not None,
                  f"title={dlg.title!r}" if dlg else "")
        if dlg is None:
            driver.capture_screen().save_png(OUT / "no_dialog.png")
            raise RuntimeError("PA dialog missing")

        crop = driver.capture_screen().crop(dlg.rect)
        crop.save_png(OUT / "pa_dialog.png")
        rep.log(f"[OCR] {joined_text(recognize_text(crop))[:600]}")
        rep.log("[INFO] AX controls:")
        fields = []
        buttons = []
        for elem, depth in walk(dlg.handle):
            role = _role(elem)
            if role in ("AXTextField", "AXStaticText", "AXButton",
                        "AXRadioButton", "AXCheckBox", "AXPopUpButton"):
                rep.log(f"  {'  ' * depth}{role} {_text(elem)!r} "
                        f"rect={_rect(elem)}")
            if role == "AXTextField":
                fields.append(elem)
            elif role == "AXButton":
                buttons.append(elem)
        rep.check("PA fields exposed", len(fields) >= 2, f"fields={len(fields)}")

        # Try one invalid value on the first field that looks like Start PA.
        start = None
        labels = [e for e in walk(dlg.handle) if _role(e[0]) == "AXStaticText"
                  and "start pa" in _text(e[0]).lower()]
        if labels:
            ly = _rect(labels[0][0])[1] if _rect(labels[0][0]) else None
            for f in fields:
                r = _rect(f)
                if r and ly is not None and abs(r[1] - ly) < 30:
                    start = f
                    break
        if start is None and fields:
            start = fields[0]
        rep.check("Start PA field", start is not None)
        if start is not None and buttons:
            rep.log(f"[INFO] Start before={_copy(start, AS.kAXValueAttribute)!r}")
            ok = AS.AXUIElementSetAttributeValue(
                start, AS.kAXValueAttribute, "abc") == 0
            time.sleep(0.5)
            rep.log(f"[INFO] set abc={ok} readback="
                    f"{_copy(start, AS.kAXValueAttribute)!r}")
            okbtn = next((b for b in buttons
                          if "ok" in _text(b).strip().lower()), buttons[0])
            rep.log(f"[INFO] press {_text(okbtn)!r} -> "
                    f"{AS.AXUIElementPerformAction(okbtn, AS.kAXPressAction) == 0}")
            time.sleep(2.0)
            wins = [w for w in driver.windows_for_pid(app.pid) if w.on_screen]
            rep.log(f"[INFO] windows after OK="
                    f"{[(w.id, w.title, w.rect.to_xywh()) for w in wins]}")
            for w in wins:
                if w.id in (win.id, dlg.id):
                    continue
                if w.handle is None:
                    driver._attach_ax_window(w)
                c = driver.capture_screen().crop(w.rect)
                c.save_png(OUT / f"warn_{w.id}.png")
                rep.log(f"[WARN] {w.title!r} OCR="
                        f"{joined_text(recognize_text(c))[:400]}")
                for elem, _d in walk(w.handle):
                    if _role(elem) in ("AXButton", "AXStaticText"):
                        rep.log(f"    {_role(elem)} {_text(elem)!r}")
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
