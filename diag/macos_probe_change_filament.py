#!/usr/bin/env python3
# diag/macos_probe_change_filament.py — move a model to another filament slot
# via the object context menu (Windows m8d path) on macOS.

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

OUT = HERE / "artifacts" / "mac" / "probe" / "change_filament"
MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MODEL_POINT = (814, 396)


def menu_windows(driver, app, main):
    out = []
    for w in driver.windows_for_pid(app.pid):
        if w.id == main.id or not w.on_screen or w.rect.area < 400:
            continue
        try:
            items = [(c.title, c.enabled) for c in driver.controls(w)
                     if c.role == "AXMenuItem"]
        except Exception:
            items = []
        if items:
            out.append((w, items))
    return out


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
        ok, _f, frac, _s = wait_for_model(driver, app, win, timeout_s=120.0)
        rep.check("launch", True, f"pid={app.pid} loaded={ok} frac={frac:.3f}")
        driver.click(win.rect.x + MODEL_POINT[0], win.rect.y + MODEL_POINT[1])
        time.sleep(0.8)
        driver.click(win.rect.x + MODEL_POINT[0], win.rect.y + MODEL_POINT[1],
                     button="right")
        time.sleep(1.0)
        driver.capture(win).save_png(OUT / "context.png")
        menus = menu_windows(driver, app, win)
        for w, items in menus:
            rep.log(f"[INFO] menu {w.title!r} rect={w.rect.to_xywh()} "
                    f"items={items[:30]}")
        item = next((c for _w, items in menus for c in
                     driver.controls(_w) if c.role == "AXMenuItem"
                     and "change filament" in c.title.lower()), None)
        # The flattened loop above loses the window; search again properly.
        if item is None:
            for w, _items in menus:
                for c in driver.controls(w):
                    if (c.role == "AXMenuItem"
                            and "change filament" in c.title.lower()):
                        item = c
                        rep.log(f"[INFO] change-filament item in "
                                f"{w.title!r}: {c.title!r}")
                        break
                if item is not None:
                    break
        rep.check("Change Filament menu item", item is not None)
        if item is not None:
            driver.click_control(item)
            time.sleep(1.2)
            driver.capture(win).save_png(OUT / "submenu.png")
            submenus = menu_windows(driver, app, win)
            for w, items in submenus:
                rep.log(f"[INFO] sub {w.title!r} rect={w.rect.to_xywh()} "
                        f"items={items[:30]}")
            silk = None
            for w, _items in submenus:
                for c in driver.controls(w):
                    if (c.role == "AXMenuItem"
                            and "silk" in c.title.lower()):
                        silk = c
                        rep.log(f"[INFO] silk row in {w.title!r}: {c.title!r}")
                        break
                if silk is not None:
                    break
            rep.check("PLA Silk submenu row", silk is not None)
            if silk is not None:
                driver.click_control(silk)
                time.sleep(1.5)
                driver.capture(win).save_png(OUT / "after.png")
                rep.log("[INFO] clicked silk")
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
