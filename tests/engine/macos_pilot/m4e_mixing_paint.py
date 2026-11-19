#!/usr/bin/env python3
# m4e_mixing_paint.py — macOS port: Feishu #39/#157 Color Painting gizmo
# palette (PARTIAL by design: per-tile painting is out of black-box scope).
# feishu: baseline#157  (macOS port; corresponds to the enabled Windows
#         m4e_mixing_paint, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   with a model selected and >1 filament, the Color Painting gizmo activates
#   from the 3D toolbar and renders the 'Filaments' palette with one colour
#   tile per physical AND mixed filament (>=5 tiles).  Per-tile painting is
#   documented out of scope (ImGui pixels).
#
# macOS mapping:
#   model select -> click the cube at (814,396)
#   toolbar      -> hover-scan the 3D toolbar row at y=90 for the tooltip
#                   'Color painting [N]' (measured at (996,90)); clicking it
#                   shows the right-side palette ('Filaments', 'Selected
#                   filament', 'Remap filaments', 'Erase all painting')
#   tiles        -> count saturated column runs in the band
#                   x 860..1200, y 120..190 (measured 5 runs)
#   toggle off   -> click the icon again; the palette disappears
#
# Artifacts: artifacts/mac/pilot/m4e/{report.log,result.json,*.png}.

from __future__ import annotations

import argparse
import colorsys
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
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m4e"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MODEL_POINT = (814, 396)
TOOLBAR_Y = 90
KNOWN_ICON_X = 996
TILE_BAND = (860, 120, 1200, 190)


def tooltip_below(driver, win, x, y, dwell=1.6):
    driver.move(win.rect.x + x, win.rect.y + y)
    time.sleep(dwell)
    words = recognize_text(
        driver.capture_screen(),
        Rect(win.rect.x + x - 90, win.rect.y + y + 8, 300, 70))
    return " ".join(w.text for w in words).strip()


def tile_runs(frame):
    x0, y0, x1, y1 = TILE_BAND
    cols = []
    for x in range(max(0, x0), min(frame.width, x1)):
        for y in range(max(0, y0), min(frame.height, y1), 2):
            i = (y * frame.width + x) * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            _h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if s > 0.45 and v > 0.25:
                cols.append(x)
                break
    runs = []
    start = prev = None
    for x in cols:
        if start is None:
            start = x
        elif prev is not None and x - prev > 3:
            runs.append((start, prev))
            start = x
        prev = x
    if start is not None:
        runs.append((start, prev))
    return [r for r in runs if r[1] - r[0] >= 8]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m4e macOS Color Painting palette ===")

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
        ok, _f, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        rep.check("multicolor project loads", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})
        driver.click(win.rect.x + MODEL_POINT[0], win.rect.y + MODEL_POINT[1])
        time.sleep(1.0)

        tip = tooltip_below(driver, win, KNOWN_ICON_X, TOOLBAR_Y)
        icon = (KNOWN_ICON_X, TOOLBAR_Y, tip) if "color" in tip.lower() \
            and "paint" in tip.lower() else None
        if icon is None:
            for x in range(480, 1101, 12):
                tip = tooltip_below(driver, win, x, TOOLBAR_Y)
                if "color" in tip.lower() and "paint" in tip.lower():
                    icon = (x, TOOLBAR_Y, tip)
                    break
        rep.check("Color Painting toolbar tooltip found", icon is not None,
                  f"@{icon}" if icon else "no 'Color painting' tooltip")
        if icon is None:
            return rep.save({"stage": "icon"})

        driver.click(win.rect.x + icon[0], win.rect.y + icon[1])
        time.sleep(2.0)
        frame = driver.capture(win)
        frame.save_png(OUT / "palette.png")
        words = recognize_text(frame)
        text = " ".join(w.text for w in words).lower()
        rep.log(f"[INFO] palette OCR={text[:180]!r}")
        rep.check("Color Painting gizmo activates",
                  "filaments" in text and "remap filaments" in text,
                  text[:140])
        runs = tile_runs(frame)
        rep.log(f"[INFO] tile runs={runs}")
        rep.check("palette renders >=5 filament tiles", len(runs) >= 5,
                  f"tiles={len(runs)} runs={runs}")

        # Toggle the gizmo off.
        driver.click(win.rect.x + icon[0], win.rect.y + icon[1])
        time.sleep(1.5)
        after = " ".join(w.text for w in recognize_text(driver.capture(win))).lower()
        rep.check("gizmo 关闭（面板消失）", "remap filaments" not in after,
                  after[:120])
        rep.check("app alive", app.alive())

        alive_before = app.alive()
        closed = close_app(driver, app, win)
        app = None
        rep.check("软件正常关闭", alive_before and closed,
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
        exit_code = rep.save({"covered": ["#39", "#157"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
