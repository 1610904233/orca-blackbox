#!/usr/bin/env python3
# diag/macos_probe_open_nav.py — navigate NSOpenPanel via sidebar + OCR.
#
# v3 finding: the panel opens on "Recents"; AXBrowser columns are empty
# AXScrollAreas, so file rows can only be addressed visually.
#
# This probe:
#   1) AXOpen the sidebar "home" row (snapmaker_test)
#   2) OCR the panel and double-click each path component under $HOME,
#      always taking the right-most match (the freshly opened column)
#   3) double-click the target STL and verify the import arrives
#
# Artifacts: artifacts/mac/probe/open_nav/...

from __future__ import annotations

import argparse
import os
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
import numpy as np  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import (  # noqa: E402
    find_text, joined_text, recognize_text,
)
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "open_nav"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"
STL = HERE / "fixtures" / "cube20.stl"


def _copy(element, attr):
    err, value = AS.AXUIElementCopyAttributeValue(element, attr, None)
    return value if err == 0 else None


def _role(elem):
    value = _copy(elem, AS.kAXRoleAttribute)
    return value if isinstance(value, str) else ""


def _text(elem):
    out = []
    for attr in (AS.kAXRoleAttribute, AS.kAXTitleAttribute,
                 AS.kAXDescriptionAttribute, AS.kAXValueAttribute):
        value = _copy(elem, attr)
        if isinstance(value, str) and value:
            out.append(value)
    return " | ".join(out)


def _actions(elem):
    try:
        return [str(a) for a in (AS.AXUIElementCopyActionNames(elem, None)[1] or [])]
    except Exception:
        return []


def walk(root, max_depth=16):
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
            for child in reversed(list(_copy(elem, AS.kAXChildrenAttribute) or [])):
                stack.append((child, depth + 1))
        except Exception:
            pass


def find_dialog(driver, pid, titles, exclude_id=None, timeout_s=12.0):
    wanted = {t.lower() for t in titles}
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for w in driver.windows_for_pid(pid):
            if not w.on_screen or (exclude_id is not None and w.id == exclude_id):
                continue
            if (w.title or "").strip().lower() in wanted:
                if w.handle is None:
                    driver._attach_ax_window(w)
                if w.handle is not None:
                    return w
        time.sleep(0.3)
    return None


def find_sidebar_open(root, label):
    """AXOpen action on the sidebar row whose static text == label."""
    for elem, _depth in walk(root):
        if _role(elem) != "AXCell" or "AXOpen" not in _actions(elem):
            continue
        for child, _d in walk(elem, max_depth=2):
            value = _copy(child, AS.kAXValueAttribute)
            if isinstance(value, str) and value.strip().lower() == label.lower():
                return elem
    return None


def panel_words(driver, panel):
    frame = driver.capture_screen().crop(panel.rect)
    return frame, recognize_text(frame)


def pick_rightmost(words, token):
    token = token.lower()
    hits = [w for w in words if w.text.strip().lower() == token]
    if not hits:
        hits = [w for w in words if token in w.text.strip().lower()]
    if not hits:
        return None
    return max(hits, key=lambda w: w.rect.x)


def vp_colored(frame) -> float:
    arr = np.frombuffer(frame.data, dtype=np.uint8).reshape(
        frame.height, frame.width, 4)
    b = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    r = arr[:, :, 2].astype(int)
    spread = np.maximum(np.maximum(b, g), r) - np.minimum(np.minimum(b, g), r)
    return float((spread[100:700, 430:1080] > 24).mean())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    work = OUT / "work"
    work.mkdir(parents=True)
    model = work / "probe_model.3mf"
    target = work / "probe_import.stl"
    shutil.copy2(MODEL, model)
    shutil.copy2(STL, target)
    components = list(work.relative_to(Path.home()).parts)
    rep = Reporter(OUT)
    rep.log("=== macOS Open-panel navigation probe ===")
    rep.log(f"work={work} target={target.name} components={components}")

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
        boot_vp = vp_colored(driver.capture(win))
        time.sleep(2.0)

        rows = [c for c in driver.controls(win, max_depth=12)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("import ")
                and "3mf" in c.title.lower()]
        if not rows:
            raise RuntimeError("no 3MF/STL import row")
        driver.click_control(rows[0])
        panel = find_dialog(driver, app.pid, ("open", "import"),
                            exclude_id=win.id, timeout_s=12.0)
        rep.check("open panel found", panel is not None)
        if panel is None:
            raise RuntimeError("open panel missing")
        driver.set_foreground(win)

        home = find_sidebar_open(panel.handle, Path.home().name)
        rep.check("sidebar home row found", home is not None,
                  f"label={Path.home().name!r}")
        if home is not None:
            rep.log(f"[INFO] AXOpen home -> "
                    f"{AS.AXUIElementPerformAction(home, 'AXOpen') == 0}")
            time.sleep(1.5)

        for index, component in enumerate(components):
            frame, words = panel_words(driver, panel)
            frame.save_png(OUT / f"step{index:02d}_{component}.png")
            rep.log(f"[INFO] step {index} OCR: {joined_text(words)[:400]}")
            hit = pick_rightmost(words, component)
            rep.check(f"folder row {component!r} visible", hit is not None,
                      f"hit={hit}" if hit else "")
            if hit is None:
                break
            cx = panel.rect.x + hit.rect.center[0]
            cy = panel.rect.y + hit.rect.center[1]
            rep.log(f"[INFO] double-click {component!r} at ({cx:.0f},{cy:.0f})")
            driver.click(cx, cy, clicks=2)
            time.sleep(1.8)

        frame, words = panel_words(driver, panel)
        frame.save_png(OUT / "target_list.png")
        rep.log(f"[INFO] target OCR: {joined_text(words)[:400]}")
        hit = pick_rightmost(words, target.name)
        if hit is None:
            hit = pick_rightmost(words, target.stem)
        rep.check("target file visible", hit is not None,
                  f"hit={hit}" if hit else "")
        if hit is not None:
            cx = panel.rect.x + hit.rect.center[0]
            cy = panel.rect.y + hit.rect.center[1]
            rep.log(f"[INFO] click target at ({cx:.0f},{cy:.0f})")
            driver.click(cx, cy)
            time.sleep(1.0)
            open_btn = next((e for e, _d in walk(panel.handle)
                             if _role(e) == "AXButton"
                             and str(_copy(e, AS.kAXValueAttribute)
                                     or _copy(e, AS.kAXTitleAttribute)
                                     or "").strip().lower() == "open"), None)
            genabled = (_copy(open_btn, AS.kAXEnabledAttribute)
                        if open_btn is not None else None)
            rep.log(f"[INFO] Open button found={open_btn is not None} "
                    f"enabled={genabled}")
            if open_btn is not None:
                pressed = AS.AXUIElementPerformAction(
                    open_btn, AS.kAXPressAction) == 0
                rep.log(f"[INFO] press Open -> {pressed}")
            time.sleep(5.0)
            after_vp = vp_colored(driver.capture(win))
            title = driver._refresh(win).title
            rep.check("import arrives", after_vp > boot_vp + 0.002 or title.startswith("*"),
                      f"vp {boot_vp:.4f}->{after_vp:.4f} title={title!r}")
            rep.log(f"[INFO] windows="
                    f"{[(w.id, w.title, w.layer) for w in driver.windows_for_pid(app.pid) if w.on_screen]}")

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
