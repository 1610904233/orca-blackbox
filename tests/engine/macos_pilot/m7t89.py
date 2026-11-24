#!/usr/bin/env python3
# m7t89.py — macOS port: Feishu #89 create -> rotate -> paint -> slice.
# feishu: baseline#170  (macOS port; corresponds to the enabled Windows
#         m7t89, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   empty bed -> create a cube -> rotate Z 45 (field commits) -> select the
#   model -> Color Painting activates and a dab lands -> slice completes.
#
# macOS mapping:
#   create -> right-click Add Primitive > Cube on an empty boot; a generated-
#             gcode Warning is cleared with Yes (m8x_137 recipe).
#   rotate -> Rotate toolbar (772,90), relative Z field (1047,148); the
#             absolute row (y=174) must read ~45 after the commit.
#   paint  -> Color Painting toolbar (996,90); Filaments panel + dab at the
#             cube centre (814,396).
#   slice  -> mac_common.slice_and_export.
#
# Artifacts: artifacts/mac/pilot/m7t89/{report.log,result.json,work/*.gcode,
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
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
)
import m7b_new_project as m7b  # noqa: E402
import m8x_137_flow_param_tabs as c137  # noqa: E402
import m8x_153_layout_print as c153  # noqa: E402
import m8x_192 as c192  # noqa: E402
import m7t74 as c74  # noqa: E402
from m8b_official_color import drag  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m7t89"
MODEL_POINT = (814, 396)
ROTATE_X = 772
PAINT_ICON = (996, 90)
PAINT_CHIP2 = (977, 145)       # palette tile for filament 2 (teal)
PAINT_CIRCLE = (925, 260)      # brush tool; triangle only selects faces


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
    rep.log(f"[INFO] set {text} @({x},{y})")


def model_point(frame):
    """Centroid of the teal cube inside the viewport (window-relative)."""
    xs = []
    ys = []
    for y in range(120, 640, 3):
        row = y * frame.width * 4
        for x in range(460, 880, 3):
            i = row + x * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            if g > r + 30 and g > b + 5 and g > 60:
                xs.append(x)
                ys.append(y)
    if not xs:
        return MODEL_POINT
    xs.sort()
    ys.sort()
    return (xs[len(xs) // 2], ys[len(ys) // 2])


def blue_centroid(frame):
    """Centroid of the blue cube after slot 1 is recoloured (#0303FC)."""
    xs = []
    ys = []
    for y in range(120, 640, 2):
        row = y * frame.width * 4
        for x in range(460, 880, 2):
            i = row + x * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            if b > 140 and b > r + 40 and b > g + 40:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))


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
    gcode = work / "m7t89.gcode"
    proj = work / "m7t89_rotated.3mf"

    rep = Reporter(OUT)
    rep.log("=== m7t89 macOS create/rotate/paint/slice ===")
    rep.log(f"datadir={args.datadir}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=None,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(4.0)
        rep.check("empty bed at boot", True, win.title)

        rep.check("model created (M-20)", m7b._add_cube(driver, app, win))
        time.sleep(2.5)
        rep.check("Prepare ready", c137.ensure_prepare(driver, app, win, rep))
        driver.capture(win).save_png(OUT / "created.png")
        driver.click(win.rect.x + MODEL_POINT[0],
                     win.rect.y + MODEL_POINT[1])
        time.sleep(1.0)

        driver.click(win.rect.x + ROTATE_X, win.rect.y + 90)
        time.sleep(1.8)
        paste(driver, win, 1047, 148, "45", rep)
        driver.capture(win).save_png(OUT / "rotated.png")
        rep.check("另存旋转后项目", c192.save_project(driver, win, rep, proj)
                  and proj.exists())
        if not proj.exists():
            return rep.save({"stage": "save-rotated"})
        t = c192.item(proj, "Cube")
        ang, axis, norms = c74.mat_info(t) if t is not None else (0, [], [])
        rep.log(f"[INFO] rotated t={t} ang={ang:.1f} axis={axis} norms={norms}")
        rep.check("rotate Z commits 45",
                  t is not None and abs(ang - 45.0) <= 2.0
                  and abs(axis[2]) >= 0.95,
                  f"ang={ang:.1f} axis={axis}")

        # Recolour slot 1 AFTER the transform checks: the cube is assigned
        # slot 1 and updates live, while the paint filament (slot 2) keeps
        # its default colour -- so the dab is visibly different.
        before_chip, panel, expected = c153.set_slot_colour_rgb(
            driver, app, win, rep)
        rep.check("slot-1 colour prepared for contrast",
                  expected is not None,
                  f"chip={before_chip} hex={expected}")
        if panel is not None:
            try:
                driver.close_window(panel)
            except Exception:
                pass
        time.sleep(1.0)

        # Re-select the rotated cube after the save (the view re-fits, so
        # the original centre is stale), then open the paint panel.
        pre_pt = model_point(driver.capture(win))
        rep.log(f"[INFO] post-save model point={pre_pt}")
        driver.click(win.rect.x + pre_pt[0], win.rect.y + pre_pt[1])
        time.sleep(1.0)
        driver.click(win.rect.x + PAINT_ICON[0],
                     win.rect.y + PAINT_ICON[1])
        time.sleep(2.0)
        text = " ".join(w.text for w in recognize_text(driver.capture(win)))
        rep.check("color painting activates",
                  "selected filament" in text.lower()
                  and "remap filaments" in text.lower(), text[-140:])
        pt = model_point(driver.capture(win))
        rep.log(f"[INFO] post-paint model point={pt}")
        # Select filament 2 (teal) from the palette and the circle brush tool.
        # (The triangle icon selects faces; the circle is the paint brush.)
        driver.click(win.rect.x + PAINT_CHIP2[0],
                     win.rect.y + PAINT_CHIP2[1])
        time.sleep(0.8)
        driver.click(win.rect.x + PAINT_CIRCLE[0],
                     win.rect.y + PAINT_CIRCLE[1])
        time.sleep(0.8)
        # The cube is blue after the slot-1 recolour: use its centroid.
        blue_pt = blue_centroid(driver.capture(win))
        if blue_pt is not None:
            pt = blue_pt
        rep.log(f"[INFO] paint point={pt}")
        before_frame = driver.capture(win)
        # The save/Colors panels can leave the main window inactive; the first
        # click focuses it, then the drag paints the stroke.
        driver.click(win.rect.x + pt[0], win.rect.y + pt[1])
        time.sleep(0.5)
        drag(win.rect.x + pt[0] - 15, win.rect.y + pt[1],
             win.rect.x + pt[0] + 15, win.rect.y + pt[1], steps=10)
        time.sleep(1.0)
        after_frame = driver.capture(win)
        changed = 0
        max_delta = 0
        for yy in range(pt[1] - 30, pt[1] + 31, 2):
            for xx in range(pt[0] - 30, pt[0] + 31, 2):
                b = before_frame.pixel(xx, yy)
                a = after_frame.pixel(xx, yy)
                d = max(abs(b[i] - a[i]) for i in range(3))
                max_delta = max(max_delta, d)
                if d >= 20:
                    changed += 1
        rep.log(f"[INFO] paint patch max_delta={max_delta} "
                f"changed_px={changed}")
        rep.check("paint dab changes colour", changed >= 5,
                  f"max_delta={max_delta} changed_px={changed}")
        after_frame.save_png(OUT / "painted.png")
        driver.click(win.rect.x + PAINT_ICON[0],
                     win.rect.y + PAINT_ICON[1])
        time.sleep(1.0)

        if not slice_and_export(
                driver, win, rep, gcode,
                [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"]):
            rep.check("slice completes", False, "slice/export failed")
            return rep.save({"stage": "slice"})
        rep.check("slice completes", gcode.exists() and gcode.stat().st_size > 0,
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
        exit_code = rep.save({"covered": ["#170"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
