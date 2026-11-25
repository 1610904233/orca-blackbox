#!/usr/bin/env python3
# m8x_192.py — macOS port: Feishu #192 uniform 150% scale.
# feishu: baseline#192  (macOS port; corresponds to the enabled Windows
#         m8x_192, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   a 20mm cube20 is selected; Uniform scale ON; 150% makes the AABB
#   30x30x30 (3 axes), XY centre unchanged, the cube stays on the bed, and
#   the Prusa spectator's item transform is bit-identical.
#
# macOS mapping:
#   scene  -> launch Prusa.stl; Import cube20.stl (it is auto-selected;
#             object-info says volume 8000mm³).
#   scale  -> Scale toolbar (796,90); the percentage field row is y=142
#             (x 971/1033/1097); the Uniform-scale checkbox is at (790,200).
#             Fields accept click + Cmd+A paste + Enter (no AX children).
#   oracle -> Save Project as P0/P1 and mac_3mf item transforms/AABBs.
#
# Artifacts: artifacts/mac/pilot/m8x_192/{report.log,result.json,work/*.3mf,
#            *.png}.

from __future__ import annotations

import argparse
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

import AppKit  # noqa: E402

from harness.platform.base import Rect  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, recover_saved_file,
    wait_for_model,
)
import mac_3mf  # noqa: E402
import m8x_202_save_as as c202  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_192"
PRUSA = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
SCALE_X = 825               # seeded-U1 layout; scan below absorbs drift
Y_PCT = 142
PCT_CENTERS = (971, 1033, 1097)
UNIFORM_CHECKBOX = (790, 200)


def find_scale_slot(driver, win):
    """The toolbar layout moves with the (seeded) printer; only a tooltip
    that literally says 'Scale' wins (fixed 796 opened Rotate on 2026-11-25)."""
    for x in range(720, 921, 10):
        driver.move(win.rect.x + x, win.rect.y + 75)
        time.sleep(1.0)
        words = recognize_text(
            driver.capture_screen(),
            Rect(win.rect.x + x - 120, win.rect.y + 85, 420, 80))
        text = " ".join(w.text for w in words).strip()
        if "scale" in text.lower():
            return (x, 75), text
    return None, ""


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


def paste(driver, win, x, y, text, rep):
    driver.click(win.rect.x + x, win.rect.y + y)
    time.sleep(0.4)
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
    driver.send_key("a", modifiers=("cmd",))
    time.sleep(0.2)
    driver.send_key("v", modifiers=("cmd",))
    time.sleep(0.4)
    driver.send_key("return")
    time.sleep(1.2)
    values = [w.text for w in recognize_text(driver.capture(win))
              if w.rect.y == Y_PCT or abs(w.rect.y - Y_PCT) < 4]
    rep.log(f"[INFO] set {text} @({x},{y}); row={values}")


def item(path: Path, name: str):
    geo = mac_3mf.read_project(path)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    for oid, t in geo.items:
        if name in names.get(oid, ""):
            return t
    return None


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
    p0 = work / "m8x_192_p0.3mf"
    p1 = work / "m8x_192_p1.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_192 macOS uniform 150% scale ===")
    rep.log(f"datadir={args.datadir} prusa={PRUSA} cube={CUBE}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=PRUSA,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.01)
        frame.save_png(OUT / "prusa.png")
        rep.check("Prusa 载入", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        rows = [c for c in driver.controls(win, max_depth=12)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("import ")
                and "3mf" in c.title.lower()]
        rep.check("导入入口可用", bool(rows))
        if not rows:
            return rep.save({"stage": "import-item"})
        driver.click_control(rows[0])
        rep.check("导入 cube20", driver.open_file_dialog(win, CUBE))
        time.sleep(4.0)
        driver.capture(win).save_png(OUT / "imported.png")
        text = " ".join(w.text for w in recognize_text(driver.capture(win)))
        rep.check("cube20 已选中（体积 8000）", "8000" in text, text[-160:])
        rep.check("另存 P0", save_project(driver, win, rep, p0) and p0.exists())
        if not p0.exists():
            return rep.save({"stage": "save-p0"})

        t_cube0 = item(p0, "cube20")
        t_prusa0 = item(p0, "Prusa")
        rep.log(f"[INFO] P0 cube={t_cube0} prusa={t_prusa0}")
        if t_cube0 is None or t_prusa0 is None:
            return rep.save({"stage": "geometry-p0"})

        # --- Scale 150% uniform ------------------------------------------
        slot, tip = find_scale_slot(driver, win)
        rep.log(f"[INFO] Scale slot={slot} tip={tip!r}")
        if slot is None:
            slot = (SCALE_X, 75)
        driver.click(win.rect.x + slot[0], win.rect.y + slot[1])
        time.sleep(2.0)
        driver.capture(win).save_png(OUT / "scale_open.png")
        text = " ".join(w.text for w in recognize_text(driver.capture(win)))
        rep.check("Scale 面板打开（非 Rotate）",
                  "uniform scale" in text.lower(), f"tip={tip!r}")
        # Uniform scale should already be on; set the first percentage field.
        paste(driver, win, PCT_CENTERS[0], Y_PCT, "150", rep)
        words = [w for w in recognize_text(driver.capture(win))
                 if abs(w.rect.y - Y_PCT) < 5]
        got = [w.text for w in words if w.text.replace(".", "").isdigit()]
        rep.log(f"[INFO] percentage row after set={got}")
        if not got or sum("150" in v for v in got) < 3:
            label = next((w for w in recognize_text(driver.capture(win))
                          if "uniform" in w.text.lower()), None)
            ux, uy = ((label.rect.x - 20, label.rect.center[1])
                      if label else UNIFORM_CHECKBOX)
            rep.log(f"[INFO] uniform did not propagate; clicking checkbox "
                    f"({ux:.0f},{uy:.0f})")
            driver.click(win.rect.x + ux, win.rect.y + uy)
            time.sleep(0.8)
            paste(driver, win, PCT_CENTERS[0], Y_PCT, "150", rep)
            words = [w for w in recognize_text(driver.capture(win))
                     if abs(w.rect.y - Y_PCT) < 5]
            got = [w.text for w in words if w.text.replace(".", "").isdigit()]
        rep.check("三轴均为 150%", bool(got) and sum("150" in v for v in got) >= 3,
                  f"row={got}")
        driver.capture(win).save_png(OUT / "scaled.png")

        rep.check("另存 P1", save_project(driver, win, rep, p1) and p1.exists())
        if not p1.exists():
            return rep.save({"stage": "save-p1"})
        t_cube1 = item(p1, "cube20")
        t_prusa1 = item(p1, "Prusa")
        rep.log(f"[INFO] P1 cube={t_cube1} prusa={t_prusa1}")
        rep.check("Prusa 位姿逐位不变",
                  tuple(round(v, 6) for v in t_prusa0)
                  == tuple(round(v, 6) for v in t_prusa1),
                  f"{t_prusa0} -> {t_prusa1}")

        aabbs = mac_3mf.object_aabbs_by_id(p1)
        cube_box = next((b for _oid, (n, b) in aabbs.items()
                         if "cube20" in n.lower()), None)
        rep.check("cube AABB 30×30×30",
                  cube_box is not None
                  and all(abs((cube_box[1][i] - cube_box[0][i]) - 30.0) <= 0.2
                          for i in range(3)),
                  f"box={cube_box}")
        if cube_box is not None:
            c0 = t_cube0
            c1 = t_cube1
            rep.check("XY 中心不变 ±0.5mm",
                      c0 is not None and c1 is not None
                      and abs(c0[9] - c1[9]) <= 0.5
                      and abs(c0[10] - c1[10]) <= 0.5,
                      f"{c0[9:11] if c0 else None} -> {c1[9:11] if c1 else None}")
            rep.check("贴床（AABB min z=0）",
                      abs(cube_box[0][2]) <= 0.2, f"minz={cube_box[0][2]}")
            rep.check("行范数=1.5（三轴同步）",
                      all(abs((c1[i] ** 2 + c1[i + 3] ** 2 + c1[i + 6] ** 2) ** 0.5 - 1.5)
                          <= 0.02 for i in range(3)),
                      f"rows={[round((c1[i]**2+c1[i+3]**2+c1[i+6]**2)**0.5,4) for i in range(3)]}")

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
        exit_code = rep.save({"covered": ["#192"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
