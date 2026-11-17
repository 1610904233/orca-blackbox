#!/usr/bin/env python3
# diag/macos_probe_pa_methods.py — PA Line / PA Pattern states.
#
# PA dialog: method radios are drawn at the "PA Tower / PA Line / PA Pattern"
# row (~y=150, x=60/120/200 dialog-relative).  #221/#222 need the checkbox
# (Print numbers) and field enabled/value changes per method.

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

OUT = HERE / "artifacts" / "mac" / "probe" / "pa_methods"


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


def window_by_title(driver, app, needle, timeout_s=6.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for w in driver.windows_for_pid(app.pid):
            if w.on_screen and needle.lower() in (w.title or "").lower():
                if w.handle is None:
                    driver._attach_ax_window(w)
                return w
        time.sleep(0.3)
    return None


def state(dlg):
    fields = [e for e, _d in walk(dlg.handle) if _role(e) == "AXTextField"]
    boxes = [e for e, _d in walk(dlg.handle) if _role(e) == "AXCheckBox"]
    return {
        "fields": [(str(_copy(f, AS.kAXValueAttribute)),
                    bool(_copy(f, AS.kAXEnabledAttribute))) for f in fields],
        "checkboxes": [(str(_copy(b, AS.kAXValueAttribute)),
                        bool(_copy(b, AS.kAXEnabledAttribute))) for b in boxes],
    }


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
                    and "pressure advance" in c.title.lower()), None)
        driver.click_control(row)
        time.sleep(2.0)
        dlg = window_by_title(driver, app, "PA Calibration")
        rep.check("PA dialog", dlg is not None)
        if dlg is None:
            raise RuntimeError("PA dialog missing")
        rep.log(f"[INFO] tower state={state(dlg)}")
        for name, (x, y) in (("line", (120, 150)),
                             ("pattern", (200, 150)),
                             ("tower", (60, 150))):
            driver.click(dlg.rect.x + x, dlg.rect.y + y)
            time.sleep(1.2)
            rep.log(f"[INFO] {name} state={state(dlg)}")
            words = recognize_text(driver.capture_screen().crop(dlg.rect))
            rep.log(f"[INFO] {name} OCR="
                    f"{' | '.join(w.text for w in words)[:260]!r}")
        driver.send_key("escape")
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
