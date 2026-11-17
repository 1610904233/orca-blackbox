#!/usr/bin/env python3
# diag/macos_probe_plate_actions.py — are plate actions reachable without the
# custom-drawn plate rail?
#
# Dumps every AXMenuItem containing "plate" from the app (menus expose items
# even when closed), then right-clicks the bed and dumps the context menu.

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
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "plate_actions"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


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
        time.sleep(3.0)

        items = [c for c in driver.controls(win, max_depth=14)
                 if c.role == "AXMenuItem"]
        plate_items = [(c.title, c.enabled) for c in items
                       if "plate" in c.title.lower()]
        rep.log(f"[INFO] menu items with 'plate': {plate_items}")
        rep.check("plate menu entries exist", bool(plate_items))

        # Context menu on the bed.
        driver.click(win.rect.x + 1000, win.rect.y + 300, button="right")
        time.sleep(1.2)
        ctx = []
        for w in driver.windows_for_pid(app.pid):
            if w.id == win.id or not w.on_screen or w.rect.area < 1000:
                continue
            for c in driver.controls(w, max_depth=10):
                if c.role == "AXMenuItem" and c.title:
                    ctx.append(c.title)
        rep.log(f"[INFO] context items: {ctx}")
        rep.log("[INFO] context plate rows: "
                f"{[t for t in ctx if 'plate' in t.lower()]}")
        rep.check("context has plate rows",
                  any("plate" in t.lower() for t in ctx))
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
