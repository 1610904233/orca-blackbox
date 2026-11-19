#!/usr/bin/env python3
# m7t74.py — macOS port: Feishu #74 single-model transform chain + slice.
# feishu: baseline#152 baseline#156 baseline#164  (macOS port; corresponds
#         to the enabled Windows m7t74, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   import -> Move X=60 -> Rotate Z=45 -> Scale 120 -> the model stays on
#   the plate and the slice completes.
#
# macOS mapping:
#   scene  -> the mixed fixture's single cube.
#   move   -> Move toolbar (736,90), Position X at (931,148).
#   rotate -> Rotate toolbar (772,90), relative Z at (1047,148).
#   scale  -> Scale toolbar (796,90), percentage X at (971,142).
#   fields -> click + Cmd+A paste + Enter (no AX children).
#   oracle -> Save Project as P1 and parse the cube item: tx=60, rotation
#             ~45° about Z, row norm 1.2, one object still present; then
#             slice+export.
#
# Artifacts: artifacts/mac/pilot/m7t74/{report.log,result.json,work/*.3mf,
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

import AppKit  # noqa: E402

from harness.platform.macos_ocr import recognize_text  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
    wait_for_model,
)
import mac_gcode  # noqa: E402
import m8x_192 as c192  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m7t74"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MODEL_POINT = (814, 396)
MOVE_X = 736
ROTATE_X = 772
SCALE_X = 796


def paste(driver, win, x, y, text, rep) -> str:
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
    row = [w.text for w in recognize_text(driver.capture(win))
           if abs(w.rect.y - y) < 6 and w.rect.x > 700]
    rep.log(f"[INFO] set {text} @({x},{y}); row={row}")
    return " ".join(row)


def mat_info(m):
    r = [m[0:3], m[3:6], m[6:9]]
    row_norm = [math.sqrt(sum(r[i][j] ** 2 for j in range(3)))
                for i in range(3)]
    scale = sum(row_norm) / 3.0 or 1.0
    rn = [[v / scale for v in row] for row in r]
    tr = sum(rn[i][i] for i in range(3))
    ang = math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1) / 2))))
    ax = (rn[2][1] - rn[1][2], rn[0][2] - rn[2][0],
          rn[1][0] - rn[0][1])
    n = math.sqrt(sum(v * v for v in ax)) or 1.0
    axis = [round(v / n, 2) for v in ax]
    return ang, axis, [round(v, 3) for v in row_norm]


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
    proj = work / "m7t74_transformed.3mf"
    gcode = work / "m7t74.gcode"

    rep = Reporter(OUT)
    rep.log("=== m7t74 macOS move/rotate/scale chain ===")
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

        driver.click(win.rect.x + MODEL_POINT[0],
                     win.rect.y + MODEL_POINT[1])
        time.sleep(1.0)
        driver.click(win.rect.x + MOVE_X, win.rect.y + 90)
        time.sleep(1.5)
        row = paste(driver, win, 931, 148, "60", rep)
        rep.log(f"[INFO] Move row OCR={row!r} (geometry checked below)")
        driver.capture(win).save_png(OUT / "moved.png")

        driver.click(win.rect.x + ROTATE_X, win.rect.y + 90)
        time.sleep(1.5)
        row = paste(driver, win, 1047, 148, "45", rep)
        rep.log(f"[INFO] Rotate row OCR={row!r} (geometry checked below)")
        driver.capture(win).save_png(OUT / "rotated.png")

        driver.click(win.rect.x + SCALE_X, win.rect.y + 90)
        time.sleep(1.5)
        row = paste(driver, win, 971, 142, "120", rep)
        rep.check("Scale 提交 120", "120" in row, row)
        driver.capture(win).save_png(OUT / "scaled.png")

        rep.check("另存变换后项目", c192.save_project(driver, win, rep, proj)
                  and proj.exists())
        if not proj.exists():
            return rep.save({"stage": "save"})
        t = c192.item(proj, "立方体")
        rep.check("模型仍在场景（项目中有对象）", t is not None)
        if t is not None:
            ang, axis, norms = mat_info(t)
            rep.log(f"[INFO] t={t} ang={ang:.1f} axis={axis} norms={norms}")
            rep.check("Move X=60（tx=60±0.5）",
                      abs(t[9] - 60.0) <= 0.5, f"tx={t[9]}")
            rep.check("Rotate Z≈45°",
                      abs(ang - 45.0) <= 2.0
                      and abs(axis[2]) >= 0.95, f"ang={ang:.1f} axis={axis}")
            rep.check("Scale 120%（行范数≈1.2）",
                      all(abs(n - 1.2) <= 0.02 for n in norms),
                      f"norms={norms}")
            driver.capture(win).save_png(OUT / "transformed.png")

        if not slice_and_export(
                driver, win, rep, gcode,
                [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"]):
            rep.check("切片完成并导出", False, "slice/export failed")
            return rep.save({"stage": "slice"})
        used = mac_gcode.used_filaments(gcode.read_bytes())
        rep.check("切片完成并导出", gcode.exists() and gcode.stat().st_size > 0,
                  f"used={used} size={gcode.stat().st_size}")
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
        exit_code = rep.save({"covered": ["#152", "#156", "#164"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
