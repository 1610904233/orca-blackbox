#!/usr/bin/env python3
# m8x_190.py — macOS port: Feishu #190 Move X/Y/Z=100.
# feishu: baseline#190  (macOS port; corresponds to the enabled Windows
#         m8x_190, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   cube20 selected -> Move X=100, Y=100, Z=100 -> the saved project has
#   cube (tx,ty)=(100,100)±0.5, tz unchanged (bed constraint), rotation
#   unchanged; the Prusa spectator is bit-identical.
#
# macOS mapping:
#   scene -> Prusa.stl + Import cube20.stl (auto-selected, volume 8000).
#   move  -> Move toolbar (736,90); Position fields at y=148,
#            x 931/993/1053; click + Cmd+A paste + Enter.  X/Y commit in
#            one session (the panel stays open); Z is bed-constrained.
#   oracle-> Save P0/P1 and compare mac_3mf item transforms.
#
# Artifacts: artifacts/mac/pilot/m8x_190/{report.log,result.json,work/*.3mf,
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

from harness.platform.macos_ocr import recognize_text  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)
import m8x_192 as c192  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_190"
PRUSA = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
MOVE_X = 736
Y_POS = 148
POS_CENTERS = (931, 993, 1053)


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
    row = [w.text for w in recognize_text(driver.capture(win))
           if abs(w.rect.y - y) < 4]
    rep.log(f"[INFO] set {text} @({x},{y}); row={row}")


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
    p0 = work / "m8x_190_p0.3mf"
    p1 = work / "m8x_190_p1.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_190 macOS Move X/Y/Z=100 ===")
    rep.log(f"datadir={args.datadir}")

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
        text = " ".join(w.text for w in recognize_text(driver.capture(win)))
        rep.check("cube20 已选中（体积 8000）", "8000" in text, text[-120:])
        rep.check("另存 P0", c192.save_project(driver, win, rep, p0)
                  and p0.exists())
        if not p0.exists():
            return rep.save({"stage": "save-p0"})
        t_cube0 = c192.item(p0, "cube20")
        t_prusa0 = c192.item(p0, "Prusa")
        rep.log(f"[INFO] P0 cube={t_cube0} prusa={t_prusa0}")
        if t_cube0 is None or t_prusa0 is None:
            return rep.save({"stage": "geometry-p0"})

        # --- Move X/Y/Z = 100 --------------------------------------------
        driver.click(win.rect.x + MOVE_X, win.rect.y + 90)
        time.sleep(2.0)
        driver.capture(win).save_png(OUT / "move.png")
        for x, label in zip(POS_CENTERS, ("X", "Y", "Z")):
            paste(driver, win, x, Y_POS, "100", rep)
        driver.capture(win).save_png(OUT / "moved.png")

        rep.check("另存 P1", c192.save_project(driver, win, rep, p1)
                  and p1.exists())
        if not p1.exists():
            return rep.save({"stage": "save-p1"})
        t_cube1 = c192.item(p1, "cube20")
        t_prusa1 = c192.item(p1, "Prusa")
        rep.log(f"[INFO] P1 cube={t_cube1} prusa={t_prusa1}")
        rep.check("cube (tx,ty)=(100,100)±0.5",
                  t_cube1 is not None
                  and abs(t_cube1[9] - 100.0) <= 0.5
                  and abs(t_cube1[10] - 100.0) <= 0.5,
                  f"t={t_cube1[9:11] if t_cube1 else None}")
        rep.check("Z 保持贴床约束（tz 不变）",
                  t_cube1 is not None
                  and abs(t_cube1[11] - t_cube0[11]) <= 0.01,
                  f"{t_cube0[11]} -> {t_cube1[11] if t_cube1 else None}")
        rep.check("旋转未变",
                  t_cube1 is not None
                  and tuple(round(v, 6) for v in t_cube1[:9])
                  == tuple(round(v, 6) for v in t_cube0[:9]),
                  f"{t_cube0[:9]} -> {t_cube1[:9] if t_cube1 else None}")
        rep.check("Prusa 位姿逐位不变",
                  tuple(round(v, 6) for v in t_prusa0)
                  == tuple(round(v, 6) for v in t_prusa1),
                  f"{t_prusa0} -> {t_prusa1}")

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
        exit_code = rep.save({"covered": ["#190"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
