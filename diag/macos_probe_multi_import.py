#!/usr/bin/env python3
# diag/macos_probe_multi_import.py — m8x_158 pre-work: import three models
# into an empty project, inspect their placement, then try the object-list
# context menu "Center" (setup for a deterministic overlapping layout).

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

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    Reporter, close_app, launch_and_focus, recover_saved_file,
)
import mac_3mf  # noqa: E402
import m8x_186_add_plate as c186  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "multi_import"
MODELS = (HERE / "fixtures" / "Prusa.stl",
          HERE / "fixtures" / "cube20.stl",
          HERE / "fixtures" / "prism12.stl")


def import_model(driver, win, path: Path) -> bool:
    rows = [c for c in driver.controls(win, max_depth=12)
            if c.role == "AXMenuItem"
            and c.title.strip().lower().startswith("import ")
            and "3mf" in c.title.lower()]
    if not rows:
        print("[probe] no Import menu item")
        return False
    driver.click_control(rows[0])
    return driver.open_file_dialog(win, path)


def save_project(driver, win, rep, path: Path) -> bool:
    started = time.time()
    if c186.save_project(driver, win, rep, path):
        return True
    return recover_saved_file(path, started,
                              [OUT.parent]) is not None


def dump_objects(driver, win, tag):
    words = recognize_text(driver.capture_screen().crop(win.rect))
    print(f"[{tag}] window words:")
    for w in words:
        if w.rect.y > 480 or "object name" in w.text.lower():
            print("   ", repr(w.text), w.rect.to_xywh())


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    work = OUT / "work"
    work.mkdir(parents=True)
    models = []
    for src in MODELS:
        dst = work / src.name
        shutil.copy2(src, dst)
        models.append(dst)
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
        rep.check("launch (empty)", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"rect={win.rect.to_xywh()}")
        time.sleep(4.0)
        driver.capture(win).save_png(OUT / "empty.png")
        for path in models:
            ok = import_model(driver, win, path)
            print(f"[probe] import {path.name}: panel={ok}")
            time.sleep(3.0)
            dump_objects(driver, win, f"after-{path.stem}")
        driver.capture(win).save_png(OUT / "imported.png")
        p0 = work / "probe_multi.3mf"
        saved = save_project(driver, win, rep, p0)
        print(f"[probe] saved={saved} exists={p0.exists()}")
        if p0.exists():
            print("[probe] plates=", mac_3mf.read_plates(p0))
            geo = mac_3mf.read_project(p0)
            names = {o.id: o.name for o in geo.objects}
            for oid, t in geo.items:
                print("[probe] item", names.get(oid, oid),
                      "t=", tuple(round(v, 2) for v in t[9:12]))
            print("[probe] aabbs=", mac_3mf.object_world_aabbs(p0))

        # Try the Objects-tree context menu on the first object row.
        words = recognize_text(driver.capture_screen().crop(win.rect))
        tab = next((w for w in words
                    if w.text.strip().lower() == "objects"), None)
        if tab is not None:
            driver.click(win.rect.x + tab.rect.center[0],
                         win.rect.y + tab.rect.center[1])
            time.sleep(1.5)
        words = recognize_text(driver.capture_screen().crop(win.rect))
        dump_objects(driver, win, "objects-tab")
        plate1 = next((w for w in words
                       if "plate 1" in w.text.lower()), None)
        if plate1 is not None:
            row_y = plate1.rect.y + 23
            print(f"[probe] right-click tree child row (25,{row_y:.0f})")
            driver.click(win.rect.x + 25, win.rect.y + row_y,
                         button="right")
            time.sleep(1.0)
            driver.capture(win).save_png(OUT / "context_menu.png")
            for w in driver.windows_for_pid(app.pid):
                if w.id == win.id or not w.on_screen or w.rect.area < 1000:
                    continue
                try:
                    items = [(c.title, c.enabled) for c in driver.controls(w)
                             if c.role == "AXMenuItem"]
                except Exception:
                    continue
                if items:
                    print(f"[probe] menu {w.title!r}: {items[:40]}")
            # close the menu
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
