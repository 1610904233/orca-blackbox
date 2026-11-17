#!/usr/bin/env python3
# diag/macos_probe_open_scroll.py — how to scroll the NSOpenPanel file list.
#
# Failure mode: after entering artifacts/mac, "pilot" is below the visible
# rows and neither AXScrollDownByPage nor a synthetic wheel reveals it.
# This probe dumps the scroll widgets and tries page actions, wheel at several
# points, and a scrollbar-thumb drag.

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

OUT = HERE / "artifacts" / "mac" / "probe" / "open_scroll"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


def _copy(elem, attr):
    err, value = AS.AXUIElementCopyAttributeValue(elem, attr, None)
    return value if err == 0 else None


def _role(elem):
    v = _copy(elem, AS.kAXRoleAttribute)
    return v if isinstance(v, str) else ""


def _text(elem):
    out = []
    for attr in (AS.kAXTitleAttribute, AS.kAXValueAttribute,
                 AS.kAXDescriptionAttribute):
        v = _copy(elem, attr)
        if isinstance(v, str) and v:
            out.append(v)
    return " | ".join(out)


def _actions(elem):
    try:
        return [str(a) for a in
                (AS.AXUIElementCopyActionNames(elem, None)[1] or [])]
    except Exception:
        return []


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
            for c in reversed(list(children)):
                stack.append((c, depth + 1))


def panel_words(driver, panel):
    return recognize_text(driver.capture_screen(), panel.rect)


def pick(ws, token):
    token = token.lower()
    hits = [w for w in ws if w.text.strip().lower() == token] or \
        [w for w in ws if token in w.text.strip().lower()]
    return max(hits, key=lambda w: w.rect.x) if hits else None


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
        app, win = launch_and_focus(driver, OUT / "profile", model=MODEL,
                                    timeout_s=150.0,
                                    log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(2.0)
        item = next((c for c in driver.controls(win, max_depth=12)
                     if c.role == "AXMenuItem"
                     and c.title.strip().lower().startswith("import ")
                     and "3mf" in c.title.lower()), None)
        driver.click_control(item)
        panel = driver.find_file_dialog(win.pid,
                                        titles=driver._OPEN_PANEL_TITLES,
                                        exclude_id=win.id, timeout_s=10.0)
        rep.check("panel", panel is not None)
        if panel is None:
            raise RuntimeError("no panel")
        home = driver._find_sidebar_open(panel.handle, Path.home().name)
        if home is not None:
            AS.AXUIElementPerformAction(home, "AXOpen")
            time.sleep(1.2)
        for comp in ("code", "orca_blackbox", "orca-blackbox", "artifacts",
                     "mac"):
            w = pick(panel_words(driver, panel), comp)
            rep.log(f"[NAV] {comp!r} -> {w}")
            if w is None:
                break
            driver.click(*w.rect.center)
            time.sleep(1.2)
        ws = panel_words(driver, panel)
        rep.log(f"[NAV] at artifacts/mac: pilot={pick(ws, 'pilot')} "
                f"tail={joined_text(ws)[-160:]!r}")
        rep.log(f"[INFO] panel focused={_copy(panel.handle, AS.kAXFocusedAttribute)}")

        scrollbars = [(e, _role(e), _actions(e), driver._ax_rect(e))
                      for e, _d in walk(panel.handle)
                      if _role(e) in ("AXScrollBar", "AXScrollArea",
                                      "AXValueIndicator")]
        for e, role, acts, rect in scrollbars:
            rep.log(f"[SCROLL] {role} actions={acts} rect={rect}")
        bars = [e for e, role, _a, _r in scrollbars if role == "AXScrollBar"]
        for i, b in enumerate(bars):
            for action in ("AXIncrementPage", "AXDecrementPage",
                           "AXIncrementArrow"):
                code_ = AS.AXUIElementPerformAction(b, action)
                time.sleep(0.6)
                ws = panel_words(driver, panel)
                rep.log(f"[AX] bar{i} {action} code={code_} pilot={pick(ws, 'pilot')}")

        # wheel at a few points in the file list
        for xr, yr, notches in ((0.68, 0.55, -6), (0.85, 0.55, -6),
                                (0.68, 0.75, -10), (0.68, 0.35, -6),
                                (0.68, 0.55, 6)):
            px = panel.rect.x + panel.rect.w * xr
            py = panel.rect.y + panel.rect.h * yr
            driver.wheel(px, py, notches)
            time.sleep(0.8)
            ws = panel_words(driver, panel)
            rep.log(f"[WH] ({xr},{yr}) n={notches} pilot={pick(ws, 'pilot')}")

        # drag a vertical scrollbar thumb
        for b in bars:
            rect = driver._ax_rect(b)
            if rect is None or rect.h < 60:
                continue
            cx = rect.center[0]
            y0 = rect.y + 20
            y1 = rect.y + rect.h - 20
            rep.log(f"[DRAG] bar rect={rect} {y0}->{y1}")
            driver.click(cx, y0)
            time.sleep(0.3)
            # drag via mouse down/move/up
            src = driver._event_source()
            import Quartz
            p0 = Quartz.CGPointMake(cx, y0)
            p1 = Quartz.CGPointMake(cx, y1)
            down = Quartz.CGEventCreateMouseEvent(
                src, Quartz.kCGEventLeftMouseDown, p0,
                Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
            for step in range(1, 11):
                py = y0 + (y1 - y0) * step / 10.0
                mv = Quartz.CGEventCreateMouseEvent(
                    src, Quartz.kCGEventLeftMouseDragged,
                    Quartz.CGPointMake(cx, py), Quartz.kCGMouseButtonLeft)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, mv)
                time.sleep(0.05)
            up = Quartz.CGEventCreateMouseEvent(
                src, Quartz.kCGEventLeftMouseUp, p1,
                Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
            time.sleep(0.8)
            ws = panel_words(driver, panel)
            rep.log(f"[DRAG] pilot={pick(ws, 'pilot')}")

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
