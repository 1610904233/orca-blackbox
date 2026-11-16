#!/usr/bin/env python3
# diag/macos_probe_newproject_dialog.py — what does New Project ask on macOS?
#
# m8x_200 hit a "Creating a new project: unsaved changes ... discard the
# preset values ... or transfer" dialog after a scene edit.  This probe dumps
# that dialog's windows/AX buttons/OCR text, dismisses it, then lists File
# menu items whose title contains "project".
#
# Artifacts: artifacts/mac/probe/newproject_dialog/...

from __future__ import annotations

import argparse
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
from harness.platform.macos_ocr import (  # noqa: E402
    find_text, joined_text, recognize_text,
)
from mac_common import (  # noqa: E402
    Reporter, close_app, launch_and_focus,
)
import m7b_new_project as m7b  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "newproject_dialog"
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


def dump_window(driver, win, rep):
    rep.log(f"--- window id={win.id} title={win.title!r} "
            f"rect={win.rect.to_xywh()} layer={win.layer} ---")
    if win.handle is None:
        driver._attach_ax_window(win)
    for elem, depth in walk(win.handle):
        if _role(elem) in ("AXButton", "AXStaticText", "AXTextField",
                           "AXCheckBox", "AXRadioButton", "AXPopUpButton"):
            rep.log(f"{'  ' * depth}{_role(elem)} {_text(elem)!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    work = OUT / "work"
    work.mkdir(parents=True)
    model = work / "model.3mf"
    shutil.copy2(MODEL, model)

    rep = Reporter(OUT)
    rep.log("=== macOS New Project dialog probe ===")
    driver = None
    app = None
    win = None
    code = 2
    try:
        driver = get_driver()
        app, win = launch_and_focus(driver, args.datadir, model=model,
                                    timeout_s=150.0,
                                    log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(3.0)

        rep.log(f"[INFO] add cube -> {m7b._add_cube(driver, app, win)}")
        driver.send_key("escape")
        time.sleep(1.0)

        item = next((c for c in driver.controls(win, max_depth=12)
                     if c.role == "AXMenuItem"
                     and c.title.strip().lower() == "new project"), None)
        rep.check("New Project item", item is not None)
        driver.click_control(item)
        time.sleep(2.0)

        wins = [w for w in driver.windows_for_pid(app.pid) if w.on_screen]
        rep.log(f"[INFO] windows: "
                f"{[(w.id, w.title, w.rect.to_xywh(), w.layer) for w in wins]}")
        for w in wins:
            if w.id == win.id:
                continue
            dump_window(driver, w, rep)
            crop = driver.capture_screen().crop(w.rect)
            crop.save_png(OUT / f"dialog_{w.id}.png")
            words = recognize_text(crop)
            rep.log(f"[INFO] OCR({w.title!r}): {joined_text(words)[:500]}")

        # Dismiss with whatever "discard"-like button exists.
        dismissed = False
        for w in wins:
            if w.id == win.id:
                continue
            if w.handle is None:
                driver._attach_ax_window(w)
            for elem, _depth in walk(w.handle):
                if _role(elem) == "AXButton":
                    label = _text(elem).lower()
                    if any(k in label for k in ("discard", "no", "cancel",
                                                "don't", "dont")):
                        rep.log(f"[INFO] press {label!r} -> "
                                f"{AS.AXUIElementPerformAction(elem, AS.kAXPressAction) == 0}")
                        dismissed = True
                        break
            if dismissed:
                break
        rep.check("dialog dismissed", dismissed)
        time.sleep(2.0)

        items = [c for c in driver.controls(win, max_depth=12)
                 if c.role == "AXMenuItem"
                 and "project" in c.title.lower()]
        rep.log(f"[INFO] project menu items: "
                f"{[(c.title, c.enabled) for c in items]}")
        rep.check("Open Project item exists",
                  any("open" in c.title.lower() for c in items))

        rep.check("app alive", app.alive())
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None and not args.keep:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        code = rep.save({})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
