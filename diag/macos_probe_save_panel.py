#!/usr/bin/env python3
# diag/macos_probe_save_panel.py — explore the native NSSavePanel on macOS.
#
# Findings so far:
#   * "Save Project" is disabled for an untitled project; "Save Project as..."
#     is the row that opens the panel.
#
# Questions answered here:
#   1) is the panel a separate CGWindow or an AXSheet child?
#   2) which AXTextField holds the filename, which AXButton saves?
#   3) which attributes does the sheet expose (AXDocument/AXURL/...)?
#   4) can the filename field take an absolute path, or is a directory
#      navigation step required?
#
# Usage:
#   .venv/bin/python diag/macos_probe_save_panel.py [--no-submit] [--keep]
#
# Artifacts: artifacts/mac/probe/save_panel/...

from __future__ import annotations

import argparse
import objc
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
for path in (str(HERE), str(HERE / "tests" / "engine")):
    if path not in sys.path:
        sys.path.insert(0, path)

import ApplicationServices as AS  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "save_panel"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


def _copy(element, attr):
    err, value = AS.AXUIElementCopyAttributeValue(element, attr, None)
    return value if err == 0 else None


def _attr_names(element):
    err, names = AS.AXUIElementCopyAttributeNames(element, None)
    return list(names) if err == 0 and names else []


def _role(element):
    value = _copy(element, AS.kAXRoleAttribute)
    return value if isinstance(value, str) else ""


def _text(element):
    parts = []
    for attr in (AS.kAXTitleAttribute, AS.kAXDescriptionAttribute,
                 AS.kAXValueAttribute):
        value = _copy(element, attr)
        if isinstance(value, str) and value:
            parts.append(value)
    return " | ".join(parts)


def dump_tree(element, depth, rep, max_depth=8):
    if element is None or depth > max_depth:
        return
    children = _copy(element, AS.kAXChildrenAttribute) or []
    for child in children:
        role = _role(child)
        try:
            actions = [str(a) for a in (
                AS.AXUIElementCopyActionNames(child, None)[1] or [])]
        except Exception:
            actions = []
        enabled = _copy(child, AS.kAXEnabledAttribute)
        pos = _copy(child, AS.kAXPositionAttribute)
        size = _copy(child, AS.kAXSizeAttribute)
        # Only expand the interesting native panel roles.
        rep.log(f"{'  ' * depth}{role:20s} {_text(child)!r} "
                f"enabled={enabled} actions={actions} "
                f"pos={pos!r} size={size!r}")
        if role in ("AXSheet", "AXGroup", "AXWindow", "AXScrollArea",
                    "AXSplitGroup", "AXList", "AXOutline", "AXTable",
                    "AXToolbar", "AXButton", "AXTextField", "AXMenuButton"):
            dump_tree(child, depth + 1, rep, max_depth)


def find_role(root, role, title_contains=None):
    stack = [root]
    seen = set()
    while stack:
        elem = stack.pop()
        key = id(elem)
        if key in seen:
            continue
        seen.add(key)
        if _role(elem) == role:
            text = _text(elem).lower()
            if title_contains is None or title_contains.lower() in text:
                return elem
        stack.extend(list(_copy(elem, AS.kAXChildrenAttribute) or []))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=MODEL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--no-submit", action="store_true")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    rep = Reporter(OUT)
    rep.log("=== macOS save panel probe v2 ===")

    driver = None
    app = None
    win = None
    code = 2
    try:
        driver = get_driver()
        app, win = launch_and_focus(driver, args.datadir, model=args.model,
                                    timeout_s=args.timeout,
                                    log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(2.0)

        # Open File > Save Project as... through the AX menu item.
        item = next((c for c in driver.controls(win, max_depth=12)
                     if c.role == "AXMenuItem"
                     and c.title.strip().lower() == "save project as..."), None)
        rep.check("Save Project as... item found", item is not None,
                  f"enabled={getattr(item, 'enabled', None)}")
        if item is None:
            raise RuntimeError("Save Project as... not in the AX tree")
        rep.log(f"[INFO] press Save Project as... -> {driver.click_control(item)}")
        time.sleep(3.0)

        wins = [w for w in driver.windows_for_pid(app.pid) if w.on_screen]
        rep.log(f"[INFO] on-screen windows: "
                f"{[(w.id, w.title, w.rect.to_xywh(), w.layer) for w in wins]}")
        for label, w in (("main", win), *[(f"win{w.id}", w) for w in wins
                                          if w.id != win.id]):
            dump_tree(w.handle if w.handle is not None else None, 0, rep)
            if w.handle is None:
                driver._attach_ax_window(w)
                dump_tree(w.handle, 0, rep)

        driver._attach_ax_window(win)
        sheet = find_role(win.handle, "AXSheet")
        rep.check("AXSheet present", sheet is not None)
        if sheet is None:
            frame = driver.capture_screen()
            frame.save_png(OUT / "no_sheet.png")
            raise RuntimeError("no AXSheet after Save Project as...")

        rep.log(f"[INFO] sheet attributes: {_attr_names(sheet)}")
        for attr in _attr_names(sheet):
            if any(k in attr for k in ("Document", "URL", "Title", "Label",
                                       "Description", "Default", "Cancel",
                                       "Position", "Size")):
                try:
                    rep.log(f"  {attr} = {_copy(sheet, attr)!r}")
                except Exception as exc:  # noqa: BLE001
                    rep.log(f"  {attr} EXC {exc!r}")
        rep.log("[INFO] sheet subtree:")
        dump_tree(sheet, 0, rep, max_depth=10)

        crop = driver.capture_screen().crop(
            type(win.rect)(win.rect.x, win.rect.y, win.rect.w, win.rect.h))
        crop.save_png(OUT / "panel.png")

        name_field = find_role(sheet, "AXTextField")
        rep.log(f"[INFO] first AXTextField: {_text(name_field)!r}")
        rep.check("filename field present", name_field is not None)
        save_btn = find_role(sheet, "AXButton", "save")
        rep.log(f"[INFO] save button: {_text(save_btn)!r}")
        rep.check("save button present", save_btn is not None)

        if name_field is not None and save_btn is not None and not args.no_submit:
            target = OUT / "probe_saved.3mf"
            target.unlink(missing_ok=True)
            # Test 1: absolute path in the name field.
            rep.log(f"[INFO] set absolute path {str(target)!r}")
            ok_set = bool(AS.AXUIElementSetAttributeValue(
                name_field, AS.kAXValueAttribute, str(target)) == 0)
            time.sleep(0.8)
            rep.log(f"[INFO] readback={_copy(name_field, AS.kAXValueAttribute)!r} "
                    f"set={ok_set}")
            if ok_set:
                rep.log(f"[INFO] press Save -> {AS.AXUIElementPerformAction(save_btn, AS.kAXPressAction) == 0}")
                deadline = time.monotonic() + 8.0
                while time.monotonic() < deadline and not target.exists():
                    time.sleep(0.5)
                rep.check("absolute path saved", target.exists(),
                          f"size={target.stat().st_size if target.exists() else 0}")
                if not target.exists():
                    driver.send_key("escape")
                    time.sleep(1.0)

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
        elif app is not None:
            rep.log(f"[INFO] --keep: app pid={app.pid} left running")
        code = rep.save({})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
