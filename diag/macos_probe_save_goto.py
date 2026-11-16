#!/usr/bin/env python3
# diag/macos_probe_save_goto.py — can the Save panel navigate with Cmd+Shift+G?
#
# probe_save_submit established:
#   * bare filename + AXPress(Save) commits into the panel's current folder
#   * an absolute path in the Save As field becomes a literal filename
#     ("/" -> ":") and saves nowhere useful
#
# This probe inspects the panel AX window attributes (AXDocument/AXURL/...) and
# tries Cmd+Shift+G -> Go-to-folder -> Return.
#
# Artifacts: artifacts/mac/probe/save_goto/...

from __future__ import annotations

import argparse
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

OUT = HERE / "artifacts" / "mac" / "probe" / "save_goto"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


def _copy(element, attr):
    err, value = AS.AXUIElementCopyAttributeValue(element, attr, None)
    return value if err == 0 else None


def _attrs(element):
    err, names = AS.AXUIElementCopyAttributeNames(element, None)
    return list(names) if err == 0 and names else []


def _role(elem):
    value = _copy(elem, AS.kAXRoleAttribute)
    return value if isinstance(value, str) else ""


def _text(elem):
    out = []
    for attr in (AS.kAXRoleAttribute, AS.kAXTitleAttribute,
                 AS.kAXDescriptionAttribute, AS.kAXValueAttribute,
                 AS.kAXSubroleAttribute):
        value = _copy(elem, attr)
        if isinstance(value, str) and value:
            out.append(value)
    return " | ".join(out)


def find_window(driver, app, title, timeout_s=10.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for w in driver.windows_for_pid(app.pid):
            if w.on_screen and (w.title or "").strip().lower() == title.lower():
                if w.handle is None:
                    driver._attach_ax_window(w)
                return w
        time.sleep(0.3)
    return None


def walk(root, max_depth=10):
    stack = [(root, 0)]
    seen = set()
    while stack:
        elem, depth = stack.pop()
        key = id(elem)
        if key in seen:
            continue
        seen.add(key)
        yield elem, depth
        if depth >= max_depth:
            continue
        try:
            for child in list(_copy(elem, AS.kAXChildrenAttribute) or []):
                stack.append((child, depth + 1))
        except Exception:
            pass


def dump(root, rep, max_depth=10):
    for elem, depth in walk(root, max_depth):
        rep.log(f"{'  ' * depth}{_text(elem)!r} actions="
                f"{list(AS.AXUIElementCopyActionNames(elem, None)[1] or []) if True else ''}")


def set_value(elem, text):
    return AS.AXUIElementSetAttributeValue(
        elem, AS.kAXValueAttribute, text) == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    inputs = OUT / "inputs"
    target_dir = OUT / "target_dir"
    for d in (args.datadir, inputs, target_dir):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    inputs.mkdir(parents=True)
    target_dir.mkdir(parents=True)
    model = inputs / "probe_model.3mf"
    shutil.copy2(MODEL, model)

    rep = Reporter(OUT)
    rep.log("=== macOS save-panel go-to probe ===")

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

        item = next((c for c in driver.controls(win, max_depth=12)
                     if c.role == "AXMenuItem"
                     and c.title.strip().lower() == "save project as..."), None)
        rep.check("Save Project as... found", item is not None)
        if item is None:
            raise RuntimeError("menu item missing")
        driver.click_control(item)
        panel = find_window(driver, app, "Save")
        rep.check("save panel found", panel is not None,
                  f"rect={panel.rect.to_xywh()}" if panel else "")
        if panel is None:
            raise RuntimeError("save panel missing")

        rep.log(f"[INFO] panel attributes: {_attrs(panel.handle)}")
        for attr in _attrs(panel.handle):
            if any(k in attr for k in ("Document", "URL", "Title", "Directory",
                                       "Default", "Role", "Subrole")):
                try:
                    rep.log(f"  {attr} = {_copy(panel.handle, attr)!r}")
                except Exception as exc:  # noqa: BLE001
                    rep.log(f"  {attr} EXC {exc!r}")

        rep.log("[INFO] panel tree before go-to:")
        dump(panel.handle, rep)

        # --- Cmd+Shift+G ---
        driver.set_foreground(win)
        time.sleep(0.5)
        driver.send_key("g", modifiers=("cmd", "shift"))
        time.sleep(2.0)
        wins = [(w.id, w.title, w.rect.to_xywh(), w.layer)
                for w in driver.windows_for_pid(app.pid) if w.on_screen]
        rep.log(f"[INFO] windows after Cmd+Shift+G: {wins}")
        frame = driver.capture_screen()
        frame.save_png(OUT / "after_goto.png")

        # Dump whatever new window/sheet appeared (same or new title).
        go = find_window(driver, app, "Go to Folder", timeout_s=2.0) or \
            find_window(driver, app, "Save", timeout_s=2.0)
        if go is not None:
            rep.log(f"[INFO] dumping window {go.title!r} after go-to:")
            dump(go.handle, rep)

        # Try to find the path field and submit with Return / AXConfirm.
        path_field = None
        for elem, _depth in walk(go.handle if go is not None else panel.handle):
            role = _role(elem)
            text = _text(elem).lower()
            if role == "AXTextField" and "tag" not in text:
                path_field = elem
                rep.log(f"[INFO] path field candidate: {_text(elem)!r}")
                break
        if path_field is not None:
            rep.check("path field set", set_value(path_field, str(target_dir)))
            time.sleep(0.5)
            rep.log(f"[INFO] readback: {_copy(path_field, AS.kAXValueAttribute)!r}")
            rep.log(f"[INFO] AXConfirm -> "
                    f"{AS.AXUIElementPerformAction(path_field, AS.kAXConfirmAction) == 0}")
            time.sleep(1.5)
            driver.send_key("return")
            time.sleep(2.0)
            wins = [(w.id, w.title, w.rect.to_xywh(), w.layer)
                    for w in driver.windows_for_pid(app.pid) if w.on_screen]
            rep.log(f"[INFO] windows after go submit: {wins}")
            rep.log("[INFO] panel tree after go submit:")
            dump(panel.handle, rep)

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
