#!/usr/bin/env python3
# diag/macos_probe_export_menu.py — drive File > Export > STL with real clicks.
#
# Evidence: after AXPress on "Export all objects as one STL...", the File menu
# is still on screen (OCR) and the save panel beneath ignores AXPress/Escape.
# The dialog is opened while the native menu-tracking loop is active.
#
# This probe opens the File menu with a real click, then clicks the Export
# row and the STL row with real clicks, exactly like a user.

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
import Quartz  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import joined_text, recognize_text  # noqa: E402
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "export_menu"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


def _copy(elem, attr):
    err, value = AS.AXUIElementCopyAttributeValue(elem, attr, None)
    return value if err == 0 else None


def _role(elem):
    v = _copy(elem, AS.kAXRoleAttribute)
    return v if isinstance(v, str) else ""


def _title(elem):
    v = _copy(elem, AS.kAXTitleAttribute)
    return v if isinstance(v, str) else ""


def _rect(elem):
    try:
        pos = _copy(elem, AS.kAXPositionAttribute)
        size = _copy(elem, AS.kAXSizeAttribute)
        return (pos.origin.x, pos.origin.y, size.width, size.height)
    except Exception:
        return None


def walk(root, max_depth=10):
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


def menu_items(driver, win, needle=None):
    out = []
    for c in driver.controls(win, max_depth=14):
        if c.role != "AXMenuItem":
            continue
        if needle is None or needle.lower() in c.title.lower():
            out.append(c)
    return out


def click_control_rect(driver, ctl):
    rect = ctl.rect
    if rect is None or rect.area <= 0:
        return False
    cx, cy = rect.center
    driver.click(cx, cy)
    return True


def move_mouse(x, y, source):
    p = Quartz.CGPointMake(x, y)
    ev = Quartz.CGEventCreateMouseEvent(
        source, Quartz.kCGEventMouseMoved, p, Quartz.kCGMouseButtonLeft)
    if ev is not None:
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


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

        # 1) real click the File menu bar item
        file_item = next((c for c in driver.controls(win, max_depth=12)
                          if c.role == "AXMenuBarItem"
                          and c.title.strip().lower() == "file"), None)
        rep.check("File menu bar item", file_item is not None,
                  f"rect={file_item.rect if file_item else None}")
        click_control_rect(driver, file_item)
        time.sleep(1.0)
        driver.capture_screen().save_png(OUT / "file_menu.png")
        rep.log(f"[OCR file menu] "
                f"{joined_text(recognize_text(driver.capture_screen()))[:600]}")

        # 2) find the Export parent row and hover/click it
        exp = next((c for c in menu_items(driver, win, "export")
                    if c.title.strip().lower() == "export"), None)
        rep.log(f"[INFO] Export row={exp is not None} rect={exp.rect if exp else None}")
        if exp is not None and exp.rect is not None:
            cx, cy = exp.rect.center
            move_mouse(cx, cy, driver._event_source())
            time.sleep(1.2)
            driver.capture_screen().save_png(OUT / "export_submenu.png")
            rep.log(f"[OCR submenu] "
                    f"{joined_text(recognize_text(driver.capture_screen()))[:600]}")
            driver.click(cx, cy)
            time.sleep(0.8)

        # 3) click the STL row (real click on its AX rect)
        rows = menu_items(driver, win, "stl")
        rep.log(f"[INFO] STL rows: {[(c.title, c.rect) for c in rows]}")
        target_row = next((c for c in rows
                           if "export" in c.title.lower()
                           and "one" in c.title.lower()
                           and c.rect is not None), None)
        if target_row is None:
            target_row = next((c for c in rows
                               if "export" in c.title.lower()
                               and c.rect is not None), None)
        rep.check("STL export row with rect", target_row is not None,
                  f"row={target_row.title if target_row else None}")
        if target_row is not None:
            click_control_rect(driver, target_row)
        time.sleep(2.0)

        driver.capture_screen().save_png(OUT / "after_export_click.png")
        rep.log(f"[OCR after export click] "
                f"{joined_text(recognize_text(driver.capture_screen()))[:600]}")
        rep.log(f"[INFO] windows="
                f"{[(w.id, w.title, w.layer) for w in driver.windows_for_pid(app.pid) if w.on_screen]}")

        panel = driver.find_file_dialog(win.pid,
                                        titles=driver._SAVE_PANEL_TITLES,
                                        exclude_id=win.id, timeout_s=8.0)
        rep.check("save panel", panel is not None)
        if panel is None:
            raise RuntimeError("no panel")
        field, save, cancel, _replace = driver._dialog_widgets(panel)
        rep.log(f"[INFO] AXPress Save -> "
                f"{AS.AXUIElementPerformAction(save, AS.kAXPressAction) == 0}")
        time.sleep(2.0)
        rep.log(f"[INFO] windows after save="
                f"{[(w.id, w.title, w.layer) for w in driver.windows_for_pid(app.pid) if w.on_screen]}")
        rep.log(f"[INFO] work files={sorted(p.name for p in work.iterdir())}")
        rep.check("file exists", (work / "model.stl").exists(),
                  f"files={sorted(p.name for p in work.iterdir())}")
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
