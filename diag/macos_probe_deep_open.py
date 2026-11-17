#!/usr/bin/env python3
# diag/macos_probe_deep_open.py — deep NSOpenPanel navigation.
#
# m8x_204's re-import failed in the full run: after navigating to .../work/export
# the target STL was not visible (the file column may be clipped at the panel's
# right edge).  This probe reproduces the deep path and tries:
#   1) OCR right after clicking the last folder
#   2) AXScrollRightByPage on the browser's scroll areas
#   3) the panel's view-mode AXMenuButton(s)

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

OUT = HERE / "artifacts" / "mac" / "probe" / "deep_open"
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


def words(driver, panel):
    return recognize_text(driver.capture_screen(), panel.rect)


def pick(ws, token):
    token = token.lower()
    hits = [w for w in ws if w.text.strip().lower() == token] or \
        [w for w in ws if token in w.text.strip().lower()]
    return max(hits, key=lambda w: w.rect.x) if hits else None


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    work = OUT / "work"
    export = work / "export"
    inputs = work / "inputs"
    inputs.mkdir(parents=True)
    export.mkdir(parents=True)
    shutil.copy2(MODEL, inputs / "model.3mf")
    target = export / "m8x_deep_export.stl"
    shutil.copy2(HERE / "fixtures" / "cube20.stl", target)

    rep = Reporter(OUT)
    driver = None
    app = None
    win = None
    code = 2
    try:
        driver = get_driver()
        app, win = launch_and_focus(driver, OUT / "profile",
                                    model=inputs / "model.3mf",
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
        rep.check("panel", panel is not None,
                  f"{panel.rect.to_xywh()}" if panel else "")
        if panel is None:
            raise RuntimeError("no panel")

        # home
        home = driver._find_sidebar_open(panel.handle, Path.home().name)
        rep.log(f"[INFO] home cell={home is not None}")
        if home is not None:
            AS.AXUIElementPerformAction(home, "AXOpen")
            time.sleep(1.2)

        components = list(target.parent.relative_to(Path.home()).parts)
        rep.log(f"[INFO] components={components}")
        for comp in components:
            w = pick(words(driver, panel), comp)
            rep.log(f"[INFO] {comp!r}: hit={w}")
            if w is None:
                break
            driver.click(*w.rect.center)
            time.sleep(1.4)
            ws = words(driver, panel)
            rep.log(f"[INFO] after {comp!r} OCR: {joined_text(ws)[-160:]!r}")
            time.sleep(0.2)

        # Is the target visible?
        ws = words(driver, panel)
        rep.log(f"[INFO] target visible={pick(ws, target.name) is not None}")
        driver.capture_screen().crop(panel.rect).save_png(OUT / "after_nav.png")

        # 1) scroll right on browser scroll areas
        browser = next((e for e, _d in walk(panel.handle)
                        if _role(e) == "AXBrowser"), None)
        rep.log(f"[INFO] browser={browser is not None}")
        if browser is not None:
            for i in range(6):
                areas = [e for e, _d in walk(browser) if _role(e) == "AXScrollArea"]
                for a in areas:
                    AS.AXUIElementPerformAction(a, "AXScrollRightByPage")
                time.sleep(0.4)
                w = pick(words(driver, panel), target.name)
                rep.log(f"[INFO] scroll {i}: target={w}")
                if w is not None:
                    break

        # 2) view mode buttons
        btns = [e for e, _d in walk(panel.handle)
                if _role(e) == "AXMenuButton"]
        rep.log("[INFO] menu buttons: " + str([_text(b) for b in btns]))
        for b in btns:
            rep.log(f"[INFO] AXPress {_text(b)!r} -> "
                    f"{AS.AXUIElementPerformAction(b, AS.kAXPressAction) == 0}")
            time.sleep(1.2)
            rep.log(f"[INFO] OCR after press: "
                    f"{joined_text(words(driver, panel))[-160:]!r}")
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
