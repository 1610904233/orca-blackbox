#!/usr/bin/env python3
# diag/macos_probe_transfer_dialog.py — dump the settings-transfer dialog.
#
# After a scene edit + Save As, File > New Project does not ask to save; it
# asks how to handle modified *settings* ("discard"/"transfer").  This probe
# captures its OCR text and AX buttons so the case can dismiss it.

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
import m7b_new_project as m7b  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "transfer_dialog"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


def _copy(element, attr):
    err, value = AS.AXUIElementCopyAttributeValue(element, attr, None)
    return value if err == 0 else None


def _role(elem):
    value = _copy(elem, AS.kAXRoleAttribute)
    return value if isinstance(value, str) else ""


def _text(elem):
    out = []
    for attr in (AS.kAXTitleAttribute, AS.kAXDescriptionAttribute,
                 AS.kAXValueAttribute):
        value = _copy(elem, attr)
        if isinstance(value, str) and value:
            out.append(value)
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
            for child in reversed(list(children)):
                stack.append((child, depth + 1))


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    work = OUT / "work"
    work.mkdir(parents=True)
    model = work / "model.3mf"
    shutil.copy2(MODEL, model)

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
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(3.0)
        rep.log(f"[INFO] add cube -> {m7b._add_cube(driver, app, win)}")
        driver.send_key("escape")
        time.sleep(1.0)

        item = next((c for c in driver.controls(win, max_depth=12)
                     if c.role == "AXMenuItem"
                     and c.title.strip().lower() == "save project as..."), None)
        rep.log(f"[INFO] Save As press -> "
                f"{driver.click_control(item) if item else None}")
        panel = driver.find_file_dialog(win.pid,
                                        titles=driver._SAVE_PANEL_TITLES,
                                        exclude_id=win.id, timeout_s=8.0)
        saved = (driver.save_file_dialog(win, work / "probe.3mf",
                                         default_dir=work) if panel else False)
        rep.log(f"[INFO] saved={saved} title={driver._refresh(win).title!r}")

        item = next((c for c in driver.controls(win, max_depth=12)
                     if c.role == "AXMenuItem"
                     and c.title.strip().lower() == "new project"), None)
        rep.log(f"[INFO] New Project press -> "
                f"{driver.click_control(item) if item else None}")
        time.sleep(2.0)

        wins = [w for w in driver.windows_for_pid(app.pid) if w.on_screen]
        rep.log(f"[INFO] windows: "
                f"{[(w.id, w.title, w.rect.to_xywh(), w.layer) for w in wins]}")
        for w in wins:
            if w.id == win.id:
                continue
            if w.handle is None:
                driver._attach_ax_window(w)
            rep.log(f"--- {w.title!r} rect={w.rect.to_xywh()} ---")
            for elem, depth in walk(w.handle):
                if _role(elem) in ("AXButton", "AXStaticText", "AXCheckBox",
                                   "AXRadioButton", "AXPopUpButton"):
                    rep.log(f"{'  ' * depth}{_role(elem)} {_text(elem)!r}")
            crop = driver.capture_screen().crop(w.rect)
            crop.save_png(OUT / f"dialog_{w.id}.png")
            rep.log(f"[INFO] OCR: {joined_text(recognize_text(crop))[:600]}")
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
