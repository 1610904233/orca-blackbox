#!/usr/bin/env python3
# diag/macos_probe_filament_variants.py — identify the three Custom filament
# preset rows (save+read filament_settings_id) and dump the Nozzle Flow menu.

from __future__ import annotations

import json
import re
import shutil
import sys
import time
import traceback
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
for path in (str(HERE), str(HERE / "tests" / "engine"),
             str(HERE / "tests" / "engine" / "macos_pilot")):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, recover_saved_file,
)
import m7b_new_project as m7b  # noqa: E402
import m8x_186_add_plate as c186  # noqa: E402
import m8d_purifier_gcode as c8d  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "filament_variants"


def save(driver, win, rep, path):
    started = time.time()
    if c186.save_project(driver, win, rep, path):
        return True
    return recover_saved_file(
        path, started, [OUT.parent, ARTIFACTS / "pilot"]) is not None


def fil_ids(path):
    try:
        with zipfile.ZipFile(path) as z:
            ps = json.loads(z.read("Metadata/project_settings.config"))
            return ps.get("filament_settings_id"), ps.get("print_settings_id")
    except Exception as exc:  # noqa: BLE001
        return f"error {exc}", None


def open_custom(driver, win):
    ws = c8d.ocr_window(driver, win)
    fil = next((w for w in ws if w.rect.x < 200 and 400 <= w.rect.y <= 435
                and len(w.text) > 3), None)
    driver.click(win.rect.x + fil.rect.center[0],
                 win.rect.y + fil.rect.center[1])
    time.sleep(1.2)
    ws = c8d.ocr_window(driver, win)
    custom = next((w for w in ws if w.text.strip().lower() == "custom"
                   and w.rect.x < 200 and w.rect.y > 440), None)
    if custom is None:
        return []
    driver.move(win.rect.x + custom.rect.center[0],
                win.rect.y + custom.rect.center[1])
    time.sleep(1.8)
    ws = c8d.ocr_window(driver, win)
    return [(w.text, w.rect) for w in ws
            if w.rect.x > 280 and 460 < w.rect.y < 560
            and "snap" in w.text.lower()]


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    work = OUT / "work"
    work.mkdir(parents=True)
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
        rep.check("launch empty", True, f"pid={app.pid}")
        time.sleep(4.0)
        rep.check("add cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        for i in range(3):
            rows = open_custom(driver, win)
            rep.log(f"[INFO] rows={[(t, r.to_xywh()) for t, r in rows]}")
            if len(rows) <= i:
                break
            t, r = rows[i]
            driver.click(win.rect.x + r.center[0], win.rect.y + r.center[1])
            time.sleep(2.0)
            p = work / f"fil_{i}.3mf"
            ok = save(driver, win, rep, p)
            rep.log(f"[INFO] row {i} {t!r} save={ok} ids="
                    f"{fil_ids(p) if ok else None}")
            driver.send_key("escape")
            time.sleep(0.5)

        ws = c8d.ocr_window(driver, win)
        flow = next((w for w in ws if w.text.strip().lower() in
                     ("standard", "high flow") and w.rect.x > 200
                     and w.rect.y < 350), None)
        rep.log(f"[INFO] flow combo={flow}")
        if flow is not None:
            driver.click(win.rect.x + flow.rect.center[0],
                         win.rect.y + flow.rect.center[1])
            time.sleep(1.0)
            ws = c8d.ocr_window(driver, win)
            rep.log("[INFO] flow menu=" + repr(
                [(w.text, w.rect.to_xywh()) for w in ws
                 if 200 < w.rect.y < 500 and w.rect.x > 150][:20]))
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
