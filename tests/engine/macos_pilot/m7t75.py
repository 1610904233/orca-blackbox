#!/usr/bin/env python3
# m7t75.py — macOS port: Feishu #75 multi-model arrange/delete/slice.
# feishu: baseline#153 baseline#158  (macOS port; corresponds to the enabled
#         Windows m7t75, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   import x2 (overlap) -> arrange -> two separated blobs -> delete one ->
#   exactly one blob remains -> slice completes and exports gcode.
#
# macOS mapping:
#   overlap   -> launch the mixed fixture, add the built-in Cube (both build
#                items share transform (135.5,136,13.5)); a generated-gcode
#                Warning is cleared with Yes.
#   arrange   -> canvas focus + Shift+A (m8x_189's proven recipe).
#   oracle    -> Save Project as... P0/P1/P2 and parse with mac_3mf: P0 has
#                two objects at the same translation; P1 has two objects with
#                centres >=20mm apart (measured 29mm); P2 has one object.
#   delete    -> right-click the arranged cube and AXPress the object menu's
#                exact 'Delete' row.
#   slice     -> mac_common.slice_and_export + non-empty gcode.
#
# Artifacts: artifacts/mac/pilot/m7t75/{report.log,result.json,work/*.3mf,
#            *.gcode,*.png}.

from __future__ import annotations

import argparse
import math
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]       # repo root
ENGINE = Path(__file__).resolve().parents[1]     # tests/engine
PILOTS = Path(__file__).resolve().parent         # tests/engine/macos_pilot
for path in (str(HERE), str(ENGINE), str(PILOTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, recover_saved_file,
    slice_and_export, teal_fraction, wait_for_model,
)
import mac_3mf  # noqa: E402
import m7b_new_project as m7b  # noqa: E402
import m8x_202_save_as as c202  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m7t75"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
PREP = Rect(55, 31, 115, 29)
MIN_SEPARATION_MM = 20.0


def warning_window(driver, app):
    return next((w for w in driver.windows_for_pid(app.pid)
                 if w.on_screen and (w.title or "").lower() == "warning"), None)


def dismiss_warning(driver, app, win, rep) -> bool:
    w = warning_window(driver, app)
    if w is None:
        return False
    words = recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
             w.rect.w, w.rect.h))
    rep.log(f"[INFO] Warning: {[x.text for x in words]}")
    yes = next((x for x in words if x.text.strip().lower() == "yes"), None)
    if yes is None:
        return False
    driver.click(win.rect.x + yes.rect.center[0],
                 win.rect.y + yes.rect.center[1])
    time.sleep(1.5)
    return True


def ensure_prepare(driver, app, win, rep) -> bool:
    for _ in range(4):
        if warning_window(driver, app) is not None:
            dismiss_warning(driver, app, win, rep)
            time.sleep(1.0)
            continue
        driver.click(win.rect.x + 113, win.rect.y + 45)
        time.sleep(1.5)
        if warning_window(driver, app) is not None:
            dismiss_warning(driver, app, win, rep)
            time.sleep(1.0)
            continue
        if teal_fraction(driver.capture(win), PREP) > 0.5:
            return True
    return False


def save_project(driver, win, rep, path: Path) -> bool:
    started = time.time()
    if not c202.open_save_as(driver, win, rep):
        return False
    saved = driver.save_file_dialog(win, path, default_dir=path.parent)
    if saved and path.exists():
        return True
    recovered = recover_saved_file(
        path, started, [path.parent, HERE / "fixtures", OUT, ARTIFACTS])
    rep.log(f"[INFO] save recovery {path.name}: {recovered}")
    return recovered is not None


def object_items(path: Path):
    geo = mac_3mf.read_project(path)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    return [(names.get(oid, oid), t) for oid, t in geo.items]


def separation(items) -> float:
    best = 0.0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            best = max(best, math.hypot(items[i][1][9] - items[j][1][9],
                                        items[i][1][10] - items[j][1][10]))
    return best


def delete_at(driver, app, win, x, y) -> bool:
    driver.click(win.rect.x + x, win.rect.y + y)
    time.sleep(0.8)
    driver.click(win.rect.x + x, win.rect.y + y, button="right")
    time.sleep(1.0)
    for w in driver.windows_for_pid(app.pid):
        if w.id == win.id or not w.on_screen or w.rect.area < 1000:
            continue
        try:
            for c in driver.controls(w):
                if (c.role == "AXMenuItem"
                        and c.title.strip().lower() == "delete"):
                    driver.click_control(c)
                    time.sleep(2.0)
                    return True
        except Exception:
            continue
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    p0 = work / "m7t75_p0.3mf"
    p1 = work / "m7t75_p1.3mf"
    p2 = work / "m7t75_p2.3mf"
    gcode = work / "m7t75.gcode"

    rep = Reporter(OUT)
    rep.log("=== m7t75 macOS multi-model arrange/delete/slice ===")
    rep.log(f"datadir={args.datadir} model={DEFAULT_MODEL}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=DEFAULT_MODEL,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        frame.save_png(OUT / "loaded.png")
        rep.check("模型载入", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        rep.check("second model added (overlap)",
                  m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        rep.check("Prepare ready", ensure_prepare(driver, app, win, rep))
        driver.capture(win).save_png(OUT / "overlap.png")

        rep.check("另存 P0（排列前）", save_project(driver, win, rep, p0))
        if not p0.exists():
            return rep.save({"stage": "save-p0"})
        items0 = object_items(p0)
        sep0 = separation(items0)
        rep.log(f"[INFO] P0 items={items0} sep={sep0:.1f}")
        rep.check("two models after add",
                  len(items0) >= 2, f"items={[n for n, _t in items0]}")
        rep.check("models overlap before arrange", sep0 < 1.0,
                  f"sep={sep0:.1f}mm")

        # --- arrange ------------------------------------------------------
        driver.click(win.rect.x + 1000, win.rect.y + 300)
        time.sleep(0.5)
        driver.send_key("a", modifiers=("shift",))
        time.sleep(6.0)
        driver.capture(win).save_png(OUT / "arranged.png")
        rep.check("另存 P1（排列后）", save_project(driver, win, rep, p1))
        if not p1.exists():
            return rep.save({"stage": "save-p1"})
        items1 = object_items(p1)
        sep1 = separation(items1)
        rep.log(f"[INFO] P1 items={items1} sep={sep1:.1f}")
        rep.check("two models after arrange", len(items1) >= 2,
                  f"items={[n for n, _t in items1]}")
        rep.check("models separated after arrange",
                  sep1 >= MIN_SEPARATION_MM,
                  f"sep={sep1:.1f}mm >= {MIN_SEPARATION_MM}")

        # --- delete one ---------------------------------------------------
        deleted = False
        for point in ((840, 396), (780, 396), (814, 396)):
            rep.log(f"[INFO] delete attempt at {point}")
            if delete_at(driver, app, win, *point):
                deleted = True
                break
        rep.check("delete row found and pressed", deleted)
        if not deleted:
            return rep.save({"stage": "delete"})
        driver.capture(win).save_png(OUT / "deleted.png")
        rep.check("另存 P2（删除后）", save_project(driver, win, rep, p2))
        if not p2.exists():
            return rep.save({"stage": "save-p2"})
        items2 = object_items(p2)
        rep.log(f"[INFO] P2 items={items2}")
        rep.check("delete one leaves one", len(items2) == 1,
                  f"items={[n for n, _t in items2]}")

        # --- slice + export ----------------------------------------------
        if not slice_and_export(driver, win, rep, gcode,
                                [work, OUT, ARTIFACTS / "pilot",
                                 HERE / "fixtures"]):
            rep.check("slice completes and exports gcode", False,
                      "slice/export failed")
            return rep.save({"stage": "slice"})
        rep.check("slice completes and exports gcode",
                  gcode.exists() and gcode.stat().st_size > 0,
                  f"size={gcode.stat().st_size}")
        rep.check("app alive", app.alive())

        alive_before = app.alive()
        closed = close_app(driver, app, win)
        app = None
        rep.check("software closed", alive_before and closed,
                  f"alive_before={alive_before} closed={closed}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        exit_code = rep.save({"covered": ["#153", "#158"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
