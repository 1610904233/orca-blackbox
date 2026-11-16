#!/usr/bin/env python3
# diag/macos_probe_save_submit.py — how to commit the native macOS Save panel.
#
# Known from probe v2:
#   * "Save Project" is disabled for an untitled project; use
#     "Save Project as...".
#   * the panel is a separate CGWindow (title "Save", layer 8) whose controls
#     are also reachable from the main window's AX children:
#       AXStaticText 'Save As:' + AXTextField '<project name>'
#       AXButton 'Cancel' / AXButton 'Save'
#   * the default folder is the directory of the model passed on the CLI.
#
# Experiments:
#   A) absolute path typed into the Save As field -> does Save commit?
#   B) bare filename -> file lands in the panel's current folder
#      (the model's directory, which this probe controls).
#
# Artifacts: artifacts/mac/probe/save_submit/...

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

OUT = HERE / "artifacts" / "mac" / "probe" / "save_submit"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


def _copy(element, attr):
    err, value = AS.AXUIElementCopyAttributeValue(element, attr, None)
    return value if err == 0 else None


def _role(elem):
    value = _copy(elem, AS.kAXRoleAttribute)
    return value if isinstance(value, str) else ""


def _title_value(elem):
    """(title, value) as strings."""
    title = _copy(elem, AS.kAXTitleAttribute)
    value = _copy(elem, AS.kAXValueAttribute)
    return (title if isinstance(title, str) else "",
            value if isinstance(value, str) else "")


def _rect(elem):
    pos = _copy(elem, AS.kAXPositionAttribute)
    size = _copy(elem, AS.kAXSizeAttribute)
    try:
        return (pos.origin.x, pos.origin.y, size.width, size.height)
    except Exception:
        return None


def save_widgets(win):
    """(name_field, save_button, cancel_button, where_popup) from win children."""
    name_field = save_button = cancel_button = where = None
    stack = [win.handle] if win.handle is not None else []
    seen = set()
    while stack:
        elem = stack.pop()
        key = id(elem)
        if key in seen:
            continue
        seen.add(key)
        role = _role(elem)
        title, value = _title_value(elem)
        if role == "AXTextField":
            content = f"{title} {value}".strip().lower()
            if content and "tag editor" not in content:
                name_field = elem
        elif role == "AXButton" and title == "Save":
            save_button = elem
        elif role == "AXButton" and title == "Cancel":
            cancel_button = elem
        elif role == "AXPopUpButton" and title.lower().startswith("where"):
            where = elem
        try:
            stack.extend(list(_copy(elem, AS.kAXChildrenAttribute) or []))
        except Exception:
            pass
    return name_field, save_button, cancel_button, where


def open_save_as(driver, win, rep):
    item = next((c for c in driver.controls(win, max_depth=12)
                 if c.role == "AXMenuItem"
                 and c.title.strip().lower() == "save project as..."), None)
    if item is None:
        return False
    return driver.click_control(item)


def find_save_window(driver, app, main, timeout_s=10.0):
    """The native save panel is its own CGWindow (title "Save", higher layer)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for w in driver.windows_for_pid(app.pid):
            if w.id == main.id or not w.on_screen:
                continue
            if (w.title or "").strip().lower() in ("save", "save as"):
                if w.handle is None:
                    driver._attach_ax_window(w)
                return w
        time.sleep(0.3)
    return None


def wait_widgets(win, timeout_s=10.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        widgets = save_widgets(win)
        if widgets[0] is not None and widgets[1] is not None:
            return widgets
        time.sleep(0.3)
    return save_widgets(win)


def set_field(field, text):
    ok = AS.AXUIElementSetAttributeValue(field, AS.kAXValueAttribute, text) == 0
    time.sleep(0.4)
    title, value = _title_value(field)
    return ok, title, value


def press(elem):
    return AS.AXUIElementPerformAction(elem, AS.kAXPressAction) == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    inputs = OUT / "inputs"
    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    if inputs.exists():
        shutil.rmtree(inputs, ignore_errors=True)
    inputs.mkdir(parents=True)
    model = inputs / "probe_model.3mf"
    shutil.copy2(MODEL, model)

    rep = Reporter(OUT)
    rep.log("=== macOS save-submit probe ===")
    rep.log(f"model={model} (panel default folder should be {inputs})")

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
        time.sleep(2.0)

        # ---------- experiment A: absolute path in the Save As field ----------
        rep.check("open Save Project as...", open_save_as(driver, win, rep))
        panel = find_save_window(driver, app, win)
        rep.check("save panel window found", panel is not None,
                  f"title={panel.title!r} rect={panel.rect.to_xywh()}"
                  if panel is not None else "")
        if panel is None:
            raise RuntimeError("save panel window not found")
        field, save, cancel, where = wait_widgets(panel)
        rep.check("save widgets found", field is not None and save is not None,
                  f"field={_title_value(field) if field is not None else None} "
                  f"where={_title_value(where) if where is not None else None}")
        if field is None or save is None:
            raise RuntimeError("save panel widgets not found")

        abs_target = inputs / "abs_path.3mf"
        abs_target.unlink(missing_ok=True)
        ok, before_title, before_value = set_field(field, str(abs_target))
        rep.log(f"[A] set abs path ok={ok} title={before_title!r} "
                f"value={before_value!r}")
        pressed = press(save)
        rep.log(f"[A] press Save -> {pressed}")
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and not abs_target.exists():
            time.sleep(0.4)
        rep.check("A absolute path committed", abs_target.exists(),
                  f"size={abs_target.stat().st_size if abs_target.exists() else 0}")
        if not abs_target.exists():
            # The sheet may still be open; cancel and reopen for B.
            field, save, cancel, where = wait_widgets(panel, timeout_s=3.0)
            if cancel is not None:
                press(cancel)
                time.sleep(1.5)

        # ---------- experiment B: bare filename into the default folder ----------
        if not abs_target.exists():
            rep.check("reopen Save Project as...",
                      open_save_as(driver, win, rep))
            panel = find_save_window(driver, app, win)
            if panel is None:
                raise RuntimeError("save panel did not reopen")
            field, save, cancel, where = wait_widgets(panel)
            if field is None or save is None:
                raise RuntimeError("save panel did not reopen")
            rep.log(f"[B] where={_title_value(where) if where is not None else None}")
            bare = "bare_name"
            ok, title, value = set_field(field, bare)
            rep.log(f"[B] set bare name ok={ok} title={title!r} value={value!r}")
            rep.log(f"[B] press Save -> {press(save)}")
            candidates = [inputs / f"{bare}.3mf", inputs / bare,
                          inputs / "bare_name.3mf"]
            deadline = time.monotonic() + 8.0
            found = None
            while time.monotonic() < deadline and found is None:
                found = next((p for p in candidates if p.exists()), None)
                time.sleep(0.4)
            rep.check("B bare name committed in default folder",
                      found is not None,
                      f"found={found} dir={sorted(p.name for p in inputs.iterdir())}")

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
