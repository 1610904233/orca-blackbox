#!/usr/bin/env python3
# m8x_193.py — macOS port: Feishu #193 two-region paint + multicolor slice.
# feishu: baseline#193  (macOS port; corresponds to the enabled Windows
#         m8x_193, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   the Color Painting panel opens with >=2 filament tiles; a left-region
#   dab changes the sampled colour (>=10), a right-region dab with a
#   different filament changes its sample and the two regions differ
#   (>=15); the slice completes and the gcode uses >=2 filaments.
#
# macOS mapping:
#   scene  -> Delete All + built-in Cube on the mixed fixture's 5 slots.
#   paint  -> Color Painting toolbar (996,90); the panel's number-key
#             shortcuts select filaments ('2', '4' — the tooltips advertise
#             'Shortcut Key N'); dabs at (800,396) / (828,396).
#   oracle -> BGRA sample deltas + mac_gcode.used_filaments.
#
# Artifacts: artifacts/mac/pilot/m8x_193/{report.log,result.json,
#            work/*.gcode,*.png}.

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

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
    wait_for_model,
)
import mac_gcode  # noqa: E402
import m7b_new_project as m7b  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_193"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MODEL_CENTER = (814, 396)
PAINT_ICON = (996, 90)
LEFT = (800, 396)
RIGHT = (828, 396)


def pixel(frame, point):
    return frame.pixel(point[0], point[1])


def delta(a, b) -> int:
    return sum(abs(x - y) for x, y in zip(a[:3], b[:3]))


def dab(driver, win, point, rep):
    for dx, dy in ((0, 0), (0, -6), (0, 6)):
        driver.click(win.rect.x + point[0] + dx,
                     win.rect.y + point[1] + dy)
        time.sleep(0.5)
    time.sleep(1.0)
    rep.log(f"[INFO] dab at {point}")


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
    gcode = work / "m8x193.gcode"

    rep = Reporter(OUT)
    rep.log("=== m8x_193 macOS two-region paint + multicolor slice ===")
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

        item = driver.find_control(win, role="AXMenuItem",
                                   title="Delete All", timeout_s=3)
        rep.check("Delete All 可用", item is not None)
        if item is None:
            return rep.save({"stage": "delete"})
        driver.click_control(item)
        time.sleep(2.5)
        rep.check("添加 cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)

        driver.click(win.rect.x + MODEL_CENTER[0],
                     win.rect.y + MODEL_CENTER[1])
        time.sleep(1.0)
        driver.click(win.rect.x + PAINT_ICON[0],
                     win.rect.y + PAINT_ICON[1])
        time.sleep(2.0)
        text = " ".join(w.text for w in recognize_text(driver.capture(win))).lower()
        rep.check("涂色面板打开", "selected filament" in text
                  and "remap filaments" in text, text[:140])
        driver.capture(win).save_png(OUT / "palette.png")
        before = driver.capture(win)
        before_l = pixel(before, LEFT)
        before_r = pixel(before, RIGHT)

        # --- left region: filament 2 --------------------------------------
        driver.send_key("2")
        time.sleep(0.8)
        dab(driver, win, LEFT, rep)
        after_l_frame = driver.capture(win)
        left1 = pixel(after_l_frame, LEFT)
        right1 = pixel(after_l_frame, RIGHT)
        after_l_frame.save_png(OUT / "paint_left.png")
        rep.check("左区涂色落墨（Δ>=10）", delta(before_l, left1) >= 10,
                  f"{before_l} -> {left1} d={delta(before_l, left1)}")

        # --- right region: filament 4 -------------------------------------
        driver.send_key("4")
        time.sleep(0.8)
        dab(driver, win, RIGHT, rep)
        after_r_frame = driver.capture(win)
        left2 = pixel(after_r_frame, LEFT)
        right2 = pixel(after_r_frame, RIGHT)
        after_r_frame.save_png(OUT / "paint_right.png")
        rep.check("右区涂色落墨（Δ>=10）", delta(right1, right2) >= 10,
                  f"{right1} -> {right2} d={delta(right1, right2)}")
        rep.check("左右区域颜色不同（Δ>=15）", delta(left2, right2) >= 15,
                  f"left={left2} right={right2} d={delta(left2, right2)}")
        rep.check("左区未被右区覆盖", delta(left1, left2) < 20,
                  f"{left1} -> {left2} d={delta(left1, left2)}")

        driver.click(win.rect.x + PAINT_ICON[0],
                     win.rect.y + PAINT_ICON[1])
        time.sleep(1.0)
        if not slice_and_export(
                driver, win, rep, gcode,
                [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"]):
            rep.check("多色切片并导出", False, "slice/export failed")
            return rep.save({"stage": "slice"})
        used = mac_gcode.used_filaments(gcode.read_bytes())
        rep.log(f"[INFO] used filaments={used} size={gcode.stat().st_size}")
        rep.check("多色切片并导出", True,
                  f"size={gcode.stat().st_size}")
        rep.check("gcode 使用 >=2 种耗材（含 2/4 涂色）",
                  len(set(used)) >= 2 and 2 in used and 4 in used,
                  f"used={used}")
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
        exit_code = rep.save({"covered": ["#193"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
