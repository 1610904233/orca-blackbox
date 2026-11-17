#!/usr/bin/env python3
# diag/macos_probe_pa_dialog2.py — PA Calibration: invalid input and OK by OCR.
#
# v1: the PA dialog exposes 5 AXTextFields (0 / 0.1 / 0.002 / '' / '') but all
# AX rects are None and the three AXButtons have empty titles.  Pressing the
# first empty button closed the dialog with no warning window.
#
# This probe locates "OK" in the dialog raster and real-clicks it, then looks
# for a warning window and dumps its OCR.

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

OUT = HERE / "artifacts" / "mac" / "probe" / "pa_dialog2"


def _copy(elem, attr):
    err, value = AS.AXUIElementCopyAttributeValue(elem, attr, None)
    return value if err == 0 else None


def _role(elem):
    v = _copy(elem, AS.kAXRoleAttribute)
    return v if isinstance(v, str) else ""


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


def click_word(driver, win, word):
    cx = win.rect.x + word.rect.center[0]
    cy = win.rect.y + word.rect.center[1]
    print(f"[pa] click {word.text!r} at ({cx:.0f},{cy:.0f})")
    driver.click(cx, cy)


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
        pa = next((c for c in driver.controls(win, max_depth=14)
                   if c.role == "AXMenuItem"
                   and "pressure advance" in c.title.lower()), None)
        driver.click_control(pa)
        time.sleep(2.0)
        dlg = dialog_by_title(driver, app, "PA Calibration")
        rep.check("PA dialog", dlg is not None,
                  f"rect={dlg.rect.to_xywh() if dlg else None}")
        if dlg is None:
            raise RuntimeError("no PA dialog")

        # Fields in document order.
        fields = [e for e, _d in walk(dlg.handle)
                  if _role(e) == "AXTextField"]
        rep.log(f"[INFO] fields={[(str(_copy(f, AS.kAXValueAttribute))) for f in fields]}")
        start = fields[0]
        AS.AXUIElementSetAttributeValue(start, AS.kAXValueAttribute, "abc")
        time.sleep(0.5)
        rep.log(f"[INFO] start readback={_copy(start, AS.kAXValueAttribute)!r}")

        crop = driver.capture_screen().crop(dlg.rect)
        crop.save_png(OUT / "pa_invalid.png")
        words = recognize_text(crop)
        rep.log("[INFO] OCR words: " + " | ".join(
            f"{w.text!r}@{w.rect.to_xywh()}" for w in words))
        ok_word = next((w for w in words
                        if w.text.strip().lower() in ("ok", "确定")), None)
        rep.check("OK button visible", ok_word is not None)
        if ok_word is None:
            raise RuntimeError("OK word not found")

        known = {w.id for w in driver.windows_for_pid(app.pid) if w.on_screen}
        click_word(driver, dlg, ok_word)
        time.sleep(2.5)
        wins = [w for w in driver.windows_for_pid(app.pid) if w.on_screen]
        rep.log(f"[INFO] windows after OK="
                f"{[(w.id, w.title, w.rect.to_xywh()) for w in wins]}")
        new = [w for w in wins if w.id not in known and w.id != dlg.id
               and w.id != win.id]
        rep.check("warning dialog appears", bool(new),
                  f"new={[(w.title, w.rect.to_xywh()) for w in new]}")
        for w in new:
            if w.handle is None:
                driver._attach_ax_window(w)
            c = driver.capture_screen().crop(w.rect)
            c.save_png(OUT / f"warning_{w.id}.png")
            ws = recognize_text(c)
            rep.log(f"[WARN] title={w.title!r} OCR="
                    f"{' | '.join(x.text for x in ws)}")
            for elem, _d in walk(w.handle):
                if _role(elem) in ("AXButton", "AXStaticText"):
                    rep.log(f"    {_role(elem)} "
                            f"{_copy(elem, AS.kAXValueAttribute)!r} "
                            f"{_copy(elem, AS.kAXTitleAttribute)!r}")

        dlg_after = dialog_by_title(driver, app, "PA Calibration", timeout_s=2.0)
        rep.check("PA dialog still open after warning", dlg_after is not None)
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
