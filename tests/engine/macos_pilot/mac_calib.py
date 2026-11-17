"""Shared helpers for the macOS calibration-dialog ports (#211-#214, #221/222).

All calibration dialogs on this build are native modal windows whose numeric
fields are AXTextFields; OK is custom-drawn and is clicked via OCR.  After OK
the tower/model lands on the plate, and the Slice button at (1000,45)
produces G-code that OCR can detect.
"""

from __future__ import annotations

import time
from pathlib import Path

import ApplicationServices as AS

from harness.platform.base import Rect
from harness.platform.macos_ocr import joined_text, recognize_text

__all__ = [
    "SLICE_XY",
    "open_calib",
    "window_by_title",
    "dialog_fields",
    "dialog_checkboxes",
    "dialog_closed",
    "click_ok",
    "wait_model",
    "object_info_text",
    "slice_plate",
    "wait_gcode",
    "export_gcode",
    "save_project_anywhere",
    "vp",
]

SLICE_XY = (1000, 45)
GCODE_MARKERS = ("stop printing object", "wipe_start", "wipe start")


def _copy(elem, attr):
    err, value = AS.AXUIElementCopyAttributeValue(elem, attr, None)
    return value if err == 0 else None


def _role(elem):
    value = _copy(elem, AS.kAXRoleAttribute)
    return value if isinstance(value, str) else ""


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
            for child in reversed(list(children)):
                stack.append((child, depth + 1))


def open_calib(driver, win, label: str) -> bool:
    calib = next((c for c in driver.controls(win, max_depth=12)
                  if c.role == "AXMenuBarItem"
                  and c.title.strip().lower() == "calibration"), None)
    if calib is None or not driver.click_control(calib):
        return False
    time.sleep(0.8)
    row = next((c for c in driver.controls(win, max_depth=14)
                if c.role == "AXMenuItem"
                and c.title.strip().lower() == label.lower()), None)
    return bool(row is not None and driver.click_control(row))


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


def dialog_closed(driver, app, win, title: str) -> bool:
    """True when no *separate* window with ``title`` is on screen.

    The main window title becomes "*<model>" (e.g. "*Retraction test"), so a
    plain title match would always hit it.
    """
    for w in driver.windows_for_pid(app.pid):
        if not w.on_screen or w.id == win.id:
            continue
        if title.lower() in (w.title or "").lower():
            return False
    return True


def dialog_fields(dlg):
    return [e for e, _d in walk(dlg.handle) if _role(e) == "AXTextField"]


def dialog_checkboxes(dlg):
    return [e for e, _d in walk(dlg.handle) if _role(e) == "AXCheckBox"]


def field_values(fields, n: int | None = None):
    picked = fields[:n] if n else fields
    return [str(_copy(f, AS.kAXValueAttribute)) for f in picked]


def click_ok(driver, dlg, attempts: int = 2) -> bool:
    for _ in range(attempts):
        words = recognize_text(driver.capture_screen().crop(dlg.rect))
        ok = next((w for w in words if w.text.strip().lower() == "ok"), None)
        if ok is None:
            return False
        driver.click(dlg.rect.x + ok.rect.center[0],
                     dlg.rect.y + ok.rect.center[1])
        time.sleep(0.6)
        if not any(w.on_screen and (w.title or "") == dlg.title
                   for w in driver.windows_for_pid(dlg.pid)):
            return True
    return True


def vp(frame) -> float:
    import numpy as np
    arr = np.frombuffer(frame.data, dtype=np.uint8).reshape(
        frame.height, frame.width, 4)
    b = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    r = arr[:, :, 2].astype(int)
    spread = np.maximum(np.maximum(b, g), r) - np.minimum(np.minimum(b, g), r)
    return float((spread[100:700, 430:1080] > 24).mean())


def wait_model(driver, win, before_vp: float, *, timeout_s: float = 60.0,
               delta: float = 0.005):
    deadline = time.monotonic() + timeout_s
    last_frame = None
    last_vp = 0.0
    while time.monotonic() < deadline:
        last_frame = driver.capture(win)
        last_vp = vp(last_frame)
        if last_vp > before_vp + delta:
            time.sleep(1.0)
            frame2 = driver.capture(win)
            vp2 = vp(frame2)
            if vp2 > before_vp + delta:
                return True, frame2, max(last_vp, vp2)
        time.sleep(1.0)
    return False, last_frame, last_vp


def object_info_text(driver, win) -> str:
    return joined_text(recognize_text(
        driver.capture_screen().crop(win.rect)))


def slice_plate(driver, win) -> None:
    driver.click(win.rect.x + SLICE_XY[0], win.rect.y + SLICE_XY[1])


def save_project_anywhere(driver, win, target: Path, *, search_root: Path,
                          timeout_s: float = 20.0) -> bool:
    """File > Save Project as... with AX commit + fresh .3mf discovery."""
    import shutil
    item = next((c for c in driver.controls(win, max_depth=12)
                 if c.role == "AXMenuItem"
                 and c.title.strip().lower() == "save project as..."), None)
    if item is None or not item.enabled:
        print(f"[mac_calib] Save Project as... unavailable "
              f"(enabled={getattr(item, 'enabled', None)})")
        return False
    started = time.time()
    driver.click_control(item)
    panel = driver.find_file_dialog(
        win.pid, titles=driver._SAVE_PANEL_TITLES, exclude_id=win.id,
        timeout_s=10.0)
    if panel is None:
        print("[mac_calib] Save Project as...: no panel")
        return False
    field = save = None
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        field, save, _c, _r = driver._dialog_widgets(panel)
        if field is not None and save is not None:
            break
        time.sleep(0.3)
    if field is None or save is None:
        print("[mac_calib] Save Project as...: widgets missing")
        return False
    AS.AXUIElementSetAttributeValue(field, AS.kAXValueAttribute, target.name)
    time.sleep(0.4)
    AS.AXUIElementPerformAction(save, AS.kAXPressAction)
    driver._wait_panel_closed(win.pid, panel.id, 12.0)
    if target.exists():
        return True
    fresh = []
    if search_root.is_dir():
        for cand in search_root.rglob("*.3mf"):
            try:
                if cand.stat().st_mtime >= started - 2.0 and cand != target:
                    fresh.append(cand)
            except OSError:
                continue
    fresh.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"[mac_calib] fresh project={[str(p) for p in fresh[:3]]}")
    if fresh:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(fresh[0]), str(target))
    return target.exists()


def export_gcode(driver, win, target: Path, *, search_root: Path,
                 timeout_s: float = 20.0) -> bool:
    """File > Export G-code... -> save panel -> AX commit; find/move the file.

    The panel's folder follows the app's last-used directory, so the fresh
    .gcode is discovered under ``search_root`` when it lands elsewhere.
    """
    import shutil
    item = next((c for c in driver.controls(win, max_depth=12)
                 if c.role == "AXMenuItem"
                 and c.title.strip().lower().startswith("export g-code")), None)
    if item is None or not item.enabled:
        print(f"[mac_calib] Export G-code unavailable "
              f"(item={item is not None}, enabled={getattr(item, 'enabled', None)})")
        return False
    started = time.time()
    driver.click_control(item)
    panel = driver.find_file_dialog(
        win.pid, titles=("save", "save as", "export"), exclude_id=win.id,
        timeout_s=10.0)
    if panel is None:
        print("[mac_calib] Export G-code: no save panel")
        return False
    field = save = None
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        field, save, _cancel, _rep = driver._dialog_widgets(panel)
        if field is not None and save is not None:
            break
        time.sleep(0.3)
    if field is None or save is None:
        print("[mac_calib] Export G-code: save widgets missing")
        return False
    AS.AXUIElementSetAttributeValue(field, AS.kAXValueAttribute, target.name)
    time.sleep(0.4)
    AS.AXUIElementPerformAction(save, AS.kAXPressAction)
    driver._wait_panel_closed(win.pid, panel.id, 12.0)
    if target.exists():
        return True
    fresh = []
    if search_root.is_dir():
        for cand in search_root.rglob("*.gcode"):
            try:
                if cand.stat().st_mtime >= started - 2.0 and cand != target:
                    fresh.append(cand)
            except OSError:
                continue
    fresh.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"[mac_calib] fresh gcode={[str(p) for p in fresh[:3]]}")
    if fresh:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(fresh[0]), str(target))
    return target.exists()


def wait_gcode(driver, win, timeout_s: float = 90.0):
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        last = object_info_text(driver, win)
        low = last.lower()
        if any(k in low for k in GCODE_MARKERS):
            return True, last
        time.sleep(2.0)
    return False, last
