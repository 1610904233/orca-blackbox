#!/usr/bin/env python3
# m7c_import_stl.py — macOS port: Feishu #11/#143 import a local STL.
# feishu: none  (macOS port; corresponds to the enabled Windows m7c_import_stl,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   empty boot -> File > Import STL -> native open dialog -> IDOK ->
#   the model must arrive (viewport chromatic fraction >= 0.25% plus a
#   chromatic blob; the small Prusa.stl measures ~0.35% vs ~0.06% empty).
#
# macOS mapping:
#   empty boot        -> launch without a model
#   Import menu row   -> AXMenuItem "Import 3MF/STL/STEP/SVG/OBJ/AMF..."
#   native open panel -> NSOpenPanel (separate AXDialog window).  Its file
#                        rows are not AX-exposed, so driver.open_file_dialog
#                        navigates via the sidebar and OCR (see macos.py).
#   arrival           -> viewport chromatic fraction + connected-component
#                        blob count on the captured BGRA frame.
#
# Artifacts: artifacts/mac/pilot/m7c/{report.log,result.json,before/after.png}.

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

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import m7b_new_project as m7b  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m7c"
DEFAULT_STL = HERE / "fixtures" / "Prusa.stl"
EMPTY_BED_MAX = 0.015
COLORED_GATE = 0.0025          # Windows gate: 0.25% of the viewport
VIEWPORT = (430, 100, 1080, 700)


def blob_count(frame) -> int:
    """Chromatic connected components of at least 100 px inside the viewport."""
    arr = np.frombuffer(frame.data, dtype=np.uint8).reshape(
        frame.height, frame.width, 4)
    b = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    r = arr[:, :, 2].astype(int)
    spread = np.maximum(np.maximum(b, g), r) - np.minimum(np.minimum(b, g), r)
    mask = (spread > 24).astype(np.uint8)
    view = np.zeros_like(mask)
    view[VIEWPORT[1]:VIEWPORT[3], VIEWPORT[0]:VIEWPORT[2]] = \
        mask[VIEWPORT[1]:VIEWPORT[3], VIEWPORT[0]:VIEWPORT[2]]
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(view, 8)
    return sum(1 for i in range(1, n)
               if float(stats[i, cv2.CC_STAT_AREA]) >= 100)


def wait_arrival(driver, win, before_vp: float, timeout_s: float = 120.0):
    """Two consecutive polls above the colored gate (rules out animation)."""
    deadline = time.monotonic() + timeout_s
    last_frame = None
    last_vp = 0.0
    last_blobs = 0
    while time.monotonic() < deadline:
        last_frame = driver.capture(win)
        last_vp = m7b._vp_colored(last_frame)
        last_blobs = blob_count(last_frame)
        if last_vp >= COLORED_GATE and last_blobs >= 1:
            time.sleep(1.5)
            frame2 = driver.capture(win)
            vp2 = m7b._vp_colored(frame2)
            if vp2 >= COLORED_GATE:
                return True, frame2, max(last_vp, vp2), blob_count(frame2)
        time.sleep(1.0)
    return False, last_frame, last_vp, last_blobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--stl", default=DEFAULT_STL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    stl = work / "m7c_import.stl"
    shutil.copy2(args.stl, stl)

    rep = Reporter(OUT)
    rep.log("=== m7c macOS import STL (#11/#143) ===")
    rep.log(f"datadir={args.datadir} stl={stl}")

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
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"blockers={app.extra.get('blockers')}")
        time.sleep(2.0)

        boot = driver.capture(win)
        boot.save_png(OUT / "before.png")
        vp0 = m7b._vp_colored(boot)
        rep.check("空盘启动", vp0 < EMPTY_BED_MAX, f"viewport={vp0:.4f}")

        rows = [c for c in driver.controls(win, max_depth=12)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("import ")
                and "3mf" in c.title.lower()]
        rep.log(f"[INFO] import rows: {[c.title for c in rows]}")
        entry_ok = bool(rows) and driver.click_control(rows[0])
        rep.check("导入入口可用（Import 3MF/STL）", entry_ok,
                  f"rows={[c.title for c in rows]}")

        opened = driver.open_file_dialog(win, stl)
        rep.check("原生打开面板选择 STL", opened)

        arrived, frame, vp, blobs = wait_arrival(driver, win, vp0)
        if frame is not None:
            frame.save_png(OUT / "after.png")
        title = driver._refresh(win).title
        rep.check("STL 导入并显示", arrived,
                  f"viewport {vp0:.4f}->{vp:.4f} blobs={blobs} title={title!r}")
        rep.check("app alive", app.alive())
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None and not args.keep:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        elif app is not None:
            rep.log(f"[INFO] --keep: app pid={app.pid} left running")
        exit_code = rep.save({"covered": ["#11", "#143"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
