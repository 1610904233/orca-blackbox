#!/usr/bin/env python3
# diag/macos_probe_process_preset.py — select a User process preset row by
# click+save+readback (print_settings_id) and dump the filament Custom->PLA
# variant list.

from __future__ import annotations

import re
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
    ARTIFACTS, Reporter, close_app, launch_and_focus, recover_saved_file,
)
import m7b_new_project as m7b  # noqa: E402
import m8x_186_add_plate as c186  # noqa: E402
import m8d_purifier_gcode as c8d  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "process_preset"


def save(driver, win, rep, path):
    started = time.time()
    if c186.save_project(driver, win, rep, path):
        return True
    return recover_saved_file(
        path, started, [OUT.parent, ARTIFACTS / "pilot"]) is not None


def preset_ids(path):
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            text = z.read("Metadata/project_settings.config").decode(
                "utf-8", "replace")
            return re.findall(r'"(?:print_settings_id|filament_settings_id)"\s*:\s*"([^"]*)"',
                              text)[:4], text
    except Exception as exc:  # noqa: BLE001
        return [], f"error: {exc}"


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
        ws = c8d.ocr_window(driver, win)
        proc = next((w for w in ws if "standard @" in w.text.lower()
                     and w.rect.x < 430), None)
        rep.log(f"[INFO] process combo={proc.text if proc else None}")
        driver.click(win.rect.x + proc.rect.center[0],
                     win.rect.y + proc.rect.center[1])
        time.sleep(1.2)
        ws = c8d.ocr_window(driver, win)
        rows = [(w.text, w.rect) for w in ws
                if w.rect.x < 430 and 600 <= w.rect.y <= 700
                and len(w.text) > 10]
        rep.log(f"[INFO] user rows={[(t, r.to_xywh()) for t, r in rows]}")
        for i, (text, rect) in enumerate(rows[:3]):
            driver.send_key("escape")
            time.sleep(0.5)
            driver.click(win.rect.x + proc.rect.center[0],
                         win.rect.y + proc.rect.center[1])
            time.sleep(1.0)
            ws = c8d.ocr_window(driver, win)
            cand = [(w.text, w.rect) for w in ws
                    if w.rect.x < 430 and 600 <= w.rect.y <= 700
                    and len(w.text) > 10]
            if len(cand) <= i:
                break
            t, r = cand[i]
            rep.log(f"[INFO] click row {i}: {t!r} @ {r.to_xywh()}")
            driver.click(win.rect.x + r.center[0], win.rect.y + r.center[1])
            time.sleep(2.0)
            p = work / f"proc_{i}.3mf"
            if not save(driver, win, rep, p):
                rep.log(f"[INFO] row {i}: save failed")
                continue
            ids, text = preset_ids(p)
            m = re.search(r'"print_settings_id"\s*:\s*"([^"]*)"', text)
            rep.log(f"[INFO] row {i} ids={ids} print_id="
                    f"{m.group(1) if m else None}")

        # Filament: Custom -> PLA -> variants.
        ws = c8d.ocr_window(driver, win)
        fil = next((w for w in ws if w.rect.x < 200 and 400 <= w.rect.y <= 435
                    and len(w.text) > 3), None)
        rep.log(f"[INFO] filament combo={fil.text if fil else None}")
        driver.click(win.rect.x + fil.rect.center[0],
                     win.rect.y + fil.rect.center[1])
        time.sleep(1.2)
        ws = c8d.ocr_window(driver, win)
        custom = next((w for w in ws if w.text.strip().lower() == "custom"
                       and w.rect.x < 200 and w.rect.y > 440), None)
        rep.log(f"[INFO] Custom={custom}")
        if custom is not None:
            driver.move(win.rect.x + custom.rect.center[0],
                        win.rect.y + custom.rect.center[1])
            time.sleep(1.8)
            ws = c8d.ocr_window(driver, win)
            driver.capture_screen().save_png(OUT / "custom_hover.png")
            rep.log("[INFO] after Custom=" + repr(
                [(w.text, w.rect.to_xywh()) for w in ws
                 if w.rect.y > 440 and w.rect.x < 700][:30]))
            pla = next((w for w in ws if "pla" in w.text.lower()
                        and 250 < w.rect.x < 500 and 440 < w.rect.y < 520), None)
            rep.log(f"[INFO] PLA type={pla}")
            if pla is not None:
                driver.click(win.rect.x + pla.rect.center[0],
                             win.rect.y + pla.rect.center[1])
                time.sleep(1.2)
                ws = c8d.ocr_window(driver, win)
                rep.log("[INFO] variants=" + repr(
                    [(w.text, w.rect.to_xywh()) for w in ws
                     if w.rect.x > 430 and w.rect.y > 430][:20]))
                driver.capture(win).save_png(OUT / "variants.png")
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
