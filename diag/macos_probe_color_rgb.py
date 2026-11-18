#!/usr/bin/env python3
# diag/macos_probe_color_rgb.py — switch the Colors panel to RGB Sliders and
# find the R/G/B sliders + hex field.

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

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = HERE / "artifacts" / "mac" / "probe" / "color_rgb"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
CHIP_XY = (25, 415)


def dump(driver, panel, tag):
    rows = []
    for c in driver.controls(panel):
        if c.role in ("AXSlider", "AXTextField", "AXColorWell",
                      "AXPopUpButton", "AXRadioButton"):
            rows.append((c.role, c.title, c.description,
                         str(c.value)[:40],
                         c.rect.to_xywh() if c.rect else None))
    print(f"[{tag}]")
    for r in rows:
        print("   ", r)
    return rows


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
        ok, _f, _frac, _s = wait_for_model(driver, app, win, timeout_s=120.0)
        rep.check("launch", True, f"pid={app.pid} loaded={ok}")
        driver.click(win.rect.x + CHIP_XY[0], win.rect.y + CHIP_XY[1])
        time.sleep(2.0)
        panel = next((w for w in driver.windows_for_pid(app.pid)
                      if w.on_screen and "colors" in (w.title or "").lower()),
                     None)
        rep.check("Colors panel", panel is not None)
        if panel is None:
            return rep.save({})
        driver.click(916, 205)      # sliders mode
        time.sleep(1.0)
        dump(driver, panel, "sliders-mode")
        popup = next((c for c in driver.controls(panel)
                      if c.role == "AXPopUpButton"), None)
        rep.log(f"[INFO] popup={popup.value if popup else None} "
                f"rect={popup.rect.to_xywh() if popup and popup.rect else None}")
        if popup is not None and popup.rect is not None:
            driver.click(*popup.rect.center)
            time.sleep(1.0)
            for w in driver.windows_for_pid(app.pid):
                if not w.on_screen or w.id == panel.id or w.id == win.id:
                    continue
                try:
                    items = [(c.title, c.enabled) for c in driver.controls(w)
                             if c.role == "AXMenuItem"]
                except Exception:
                    items = []
                if items:
                    rep.log(f"[INFO] mode menu {w.title!r}: {items}")
            target = None
            for w in driver.windows_for_pid(app.pid):
                if not w.on_screen or w.id in (panel.id, win.id):
                    continue
                try:
                    for c in driver.controls(w):
                        if (c.role == "AXMenuItem"
                                and "rgb" in (c.title or "").lower()):
                            target = c
                            break
                except Exception:
                    pass
                if target is not None:
                    break
            if target is not None:
                rep.log(f"[INFO] click {target.title!r}")
                driver.click_control(target)
                time.sleep(1.2)
                dump(driver, panel, "rgb-mode")
                driver.capture_screen().save_png(OUT / "rgb_panel.png")
                import ApplicationServices as AS
                from harness.platform.macos import _ax_set
                ctrls = driver.controls(panel)
                hexf = next((c for c in ctrls if c.role == "AXTextField"
                             and c.value and len(str(c.value)) == 6
                             and all(ch in "0123456789ABCDEFabcdef"
                                     for ch in str(c.value))), None)
                rep.log(f"[INFO] hex field={hexf.rect.to_xywh() if hexf else None} "
                        f"value={hexf.value if hexf else None}")
                if hexf is not None and hexf.handle is not None:
                    ok = _ax_set(hexf.handle, AS.kAXValueAttribute, "0000FF")
                    rep.log(f"[INFO] set hex -> {ok}")
                    driver.send_key("return")
                    time.sleep(1.2)
                    well = next((c for c in driver.controls(panel)
                                 if c.role == "AXColorWell"), None)
                    rep.log(f"[INFO] well after hex={well.value if well else None}")
                if True:
                    sliders = [c for c in driver.controls(panel)
                               if c.role == "AXSlider"]
                    points = []
                    for i, target in enumerate(sliders[:3]):
                        if target.rect is None:
                            continue
                        x = (target.rect.x + 3 if i < 2
                             else target.rect.right - 3)
                        points.append((x, target.rect.center[1]))
                    rep.log(f"[INFO] slider click points={points}")
                    for x, y in points:
                        driver.click(x, y)
                        time.sleep(0.6)
                        vals = [str(c.value) for c in driver.controls(panel)
                                if c.role == "AXTextField"]
                        well = next((c for c in driver.controls(panel)
                                     if c.role == "AXColorWell"), None)
                        rep.log(f"[INFO] after click ({x:.0f},{y:.0f}) "
                                f"fields={vals[:4]} well={well.value if well else None}")
            else:
                rep.log("[INFO] no RGB Sliders menu item")
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
