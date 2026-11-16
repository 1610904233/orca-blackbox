#!/usr/bin/env python3
# diag/macos_probe_saveas_keys.py — which key step reaches the Save As field?
#
# Logs AXFocused for the panel and field, then:
#   1) click field, type "ZZZ"            -> does it append?
#   2) End + 20 Backspaces                -> does it clear?
#   3) type a new name                    -> does it replace?
#   4) real-click Save                    -> prompt / file?

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
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402
import m7b_new_project as m7b  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "saveas_keys"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


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


def field_of(panel):
    for elem, _d in walk(panel.handle):
        if _role(elem) == "AXTextField":
            title = _copy(elem, AS.kAXTitleAttribute) or ""
            value = _copy(elem, AS.kAXValueAttribute) or ""
            text = f"{title} {value}".lower()
            if "tag editor" in text or "search" in text:
                continue
            if text.strip():
                return elem
    return None


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
        m7b._add_cube(driver, app, win)
        driver.send_key("escape")
        time.sleep(1.0)

        file_bar = next((c for c in driver.controls(win, max_depth=12)
                         if c.role == "AXMenuBarItem"
                         and c.title.strip().lower() == "file"), None)
        driver.click(*file_bar.rect.center)
        time.sleep(0.9)
        item = next((c for c in driver.controls(win, max_depth=14)
                     if c.role == "AXMenuItem"
                     and c.title.strip().lower() == "save project as..."
                     and c.rect is not None and c.rect.area > 0), None)
        rep.log(f"[INFO] save-as row rect={item.rect if item else None}")
        driver.click(*item.rect.center)
        panel = driver.find_file_dialog(win.pid,
                                        titles=driver._SAVE_PANEL_TITLES,
                                        exclude_id=win.id, timeout_s=10.0)
        rep.check("panel", panel is not None)
        if panel is None:
            raise RuntimeError("no panel")
        field = field_of(panel)
        rep.check("field", field is not None)
        rep.log("[INFO] AXWindows=" + str([
            (_copy(w, AS.kAXTitleAttribute), _copy(w, AS.kAXRoleAttribute),
             _copy(w, AS.kAXSubroleAttribute), _copy(w, AS.kAXFocusedAttribute),
             _copy(w, AS.kAXMainAttribute), _copy(w, AS.kAXEnabledAttribute))
            for w in driver._ax_windows(app.pid)]))
        import Quartz
        for raw in (Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID) or []):
            try:
                if int(raw.get("kCGWindowOwnerPID", 0)) != app.pid:
                    continue
                rep.log(f"[CG] id={int(raw.get('kCGWindowNumber', 0))} "
                        f"layer={int(raw.get('kCGWindowLayer', 0))} "
                        f"alpha={float(raw.get('kCGWindowAlpha', 1))} "
                        f"onscreen={bool(raw.get('kCGWindowIsOnscreen', False))} "
                        f"name={raw.get('kCGWindowName', '')!r} "
                        f"bounds={dict(raw.get('kCGWindowBounds'))}")
            except Exception:
                continue
        import AppKit, Quartz
        front = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        rep.log(f"[INFO] frontmost={front.localizedName() if front else None} "
                f"pid={front.processIdentifier() if front else None}")
        fr = driver._ax_rect(field)
        pt = fr.center if fr else (930, 158)
        rep.log("[INFO] top windows at field point: " + str([
            (int(r.get('kCGWindowNumber', 0)),
             r.get('kCGWindowOwnerName', ''),
             int(r.get('kCGWindowLayer', 0)),
             dict(r.get('kCGWindowBounds')))
            for r in (Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID) or [])
            if (lambda b: b.get('X',0) <= pt[0] <= b.get('X',0)+b.get('Width',0)
                and b.get('Y',0) <= pt[1] <= b.get('Y',0)+b.get('Height',0))(
                    dict(r.get('kCGWindowBounds')) or {})][:4]))
        app_elem = driver._ax_app(app.pid)
        rep.log(f"[INFO] app focusedWindow before="
                f"{_role(_copy(app_elem, AS.kAXFocusedWindowAttribute) or 0)}")
        ok_fw = AS.AXUIElementSetAttributeValue(
            app_elem, AS.kAXFocusedWindowAttribute, panel.handle) == 0
        time.sleep(0.8)
        rep.log(f"[INFO] set AXFocusedWindow -> {ok_fw}; now="
                f"{_role(_copy(app_elem, AS.kAXFocusedWindowAttribute) or 0)}")
        rep.log(f"[INFO] panel_focused={_copy(panel.handle, AS.kAXFocusedAttribute)} "
                f"panel_main={_copy(panel.handle, AS.kAXMainAttribute)} "
                f"field_focused={_copy(field, AS.kAXFocusedAttribute)} "
                f"value={_copy(field, AS.kAXValueAttribute)!r}")

        # 1) click field + type ZZZ
        rect = driver._ax_rect(field)
        driver.click(*rect.center)
        time.sleep(0.6)
        driver.click(*rect.center)
        time.sleep(0.6)
        rep.log(f"[1] after 2 clicks: field_focused="
                f"{_copy(field, AS.kAXFocusedAttribute)}")
        driver.send_text("ZZZ")
        time.sleep(0.6)
        rep.log(f"[1] after type value={_copy(field, AS.kAXValueAttribute)!r}")

        # 2) End + Backspace x20
        driver.send_key("end")
        for _ in range(20):
            driver.send_key("delete")
        time.sleep(0.5)
        rep.log(f"[2] after clear value={_copy(field, AS.kAXValueAttribute)!r}")

        # 3) type new name
        driver.send_text("m8x_probe")
        time.sleep(0.6)
        rep.log(f"[3] after rename value={_copy(field, AS.kAXValueAttribute)!r}")

        # 4) real-click Save
        save = next((e for e, _d in walk(panel.handle)
                     if _role(e) == "AXButton"
                     and (_copy(e, AS.kAXTitleAttribute) or "") == "Save"), None)
        if save is not None:
            driver.click(*driver._ax_rect(save).center)
        time.sleep(2.0)
        cancel = next((e for e, _d in walk(panel.handle)
                       if _role(e) == "AXButton"
                       and (_copy(e, AS.kAXTitleAttribute) or "") == "Cancel"), None)
        if cancel is not None:
            driver.click(*driver._ax_rect(cancel).center)
            time.sleep(1.5)
        rep.log(f"[4] windows after cancel click="
                f"{[(w.id, w.title, w.layer) for w in driver.windows_for_pid(app.pid) if w.on_screen]}")
        rep.log(f"[4] windows="
                f"{[(w.id, w.title, w.layer) for w in driver.windows_for_pid(app.pid) if w.on_screen]}")
        rep.log(f"[4] files={sorted(p.name for p in work.iterdir())}")
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
