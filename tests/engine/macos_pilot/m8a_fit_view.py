#!/usr/bin/env python3
# m8a_fit_view.py — macOS pilot: Feishu #16-#19 Fit view (partial).
# feishu: none  (macOS pilot probe; corresponds to the enabled Windows
#         m8a_fit_view, not registered in cases.py yet)
#
# This pilot covers:
#   #18 single model selected -> Fit -> zoom_to_selection (hard assertion)
#   #19 Select All -> Fit (evidence only, matching the Windows F-11 note)
#
# #16/#17 (plate switching + Fit) are NOT covered yet; they need the
# multi-plate navigation path.  The pilot is therefore explicitly PARTIAL.
#
# macOS entry: View > "Fit in all view" AXMenuItem (the toolbar Fit button is
# custom-drawn).  Blob geometry uses OpenCV on the captured BGRA frame.
#
# Artifacts: artifacts/mac/pilot/m8a/{before,selected,after_fit,
# after_select_all_fit}.png + report/result.

from __future__ import annotations

import argparse
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]       # repo root
ENGINE = Path(__file__).resolve().parents[1]     # tests/engine
for path in (str(HERE), str(ENGINE)):
    if path not in sys.path:
        sys.path.insert(0, path)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from harness.platform.base import Frame, Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, dismiss_dialogs, launch_and_focus,
)

OUT = ARTIFACTS / "pilot" / "m8a"
DEFAULT_MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"
VIEWPORT = Rect(420, 60, 780, 740)
MODEL_BLOB_MIN = 800.0


@dataclass(frozen=True)
class Blob:
    area: float
    cx: float
    cy: float
    bbox: tuple[int, int, int, int]


def blob_stats(frame: Frame) -> list[Blob]:
    arr = np.frombuffer(frame.data, dtype=np.uint8).reshape(
        frame.height, frame.width, 4)
    b = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    r = arr[:, :, 2].astype(int)
    spread = np.maximum(np.maximum(b, g), r) - np.minimum(np.minimum(b, g), r)
    mask = (spread > 24).astype(np.uint8)
    x0, y0 = int(VIEWPORT.x), int(VIEWPORT.y)
    x1, y1 = int(VIEWPORT.right), int(VIEWPORT.bottom)
    view = np.zeros_like(mask)
    view[y0:y1, x0:x1] = mask[y0:y1, x0:x1]
    n, _labels, stats, centroids = cv2.connectedComponentsWithStats(view, 8)
    blobs = []
    for i in range(1, n):
        area = float(stats[i, cv2.CC_STAT_AREA])
        if area < 100:
            continue
        blobs.append(Blob(
            area=area,
            cx=float(centroids[i][0]),
            cy=float(centroids[i][1]),
            bbox=tuple(int(v) for v in stats[i, :4])))
    blobs.sort(key=lambda x: x.area, reverse=True)
    return blobs


def _wait_model(driver, app, win, timeout_s: float = 60.0):
    deadline = time.monotonic() + timeout_s
    seen: set = set()
    last = None
    last_frame = None
    while time.monotonic() < deadline:
        seen = dismiss_dialogs(driver, app, win, seen)
        frame = driver.capture(win)
        blobs = blob_stats(frame)
        last, last_frame = blobs, frame
        if blobs and blobs[0].area >= MODEL_BLOB_MIN:
            time.sleep(1.0)
            frame2 = driver.capture(win)
            blobs2 = blob_stats(frame2)
            if blobs2 and blobs2[0].area >= MODEL_BLOB_MIN:
                return True, frame2, blobs2, seen
        time.sleep(1.0)
    return False, last_frame, last or [], seen


def _fit(driver, win) -> bool:
    item = driver.find_control(win, role="AXMenuItem",
                               title="Fit in all view", timeout_s=3)
    if item is None or not item.enabled:
        return False
    return driver.click_control(item)


def _select_all(driver, win) -> bool:
    item = driver.find_control(win, role="AXMenuItem",
                               title="Select All", timeout_s=3)
    if item is None or not item.enabled:
        return False
    return driver.click_control(item)


def _nearest(blobs: list[Blob], cx: float, cy: float) -> Blob | None:
    if not blobs:
        return None
    return min(blobs, key=lambda b: (b.cx - cx) ** 2 + (b.cy - cy) ** 2)


def _centered(blob: Blob) -> bool:
    x0 = VIEWPORT.x + VIEWPORT.w * 0.05
    x1 = VIEWPORT.right - VIEWPORT.w * 0.05
    y0 = 100.0
    y1 = VIEWPORT.bottom - VIEWPORT.h * 0.10
    return x0 <= blob.cx <= x1 and y0 <= blob.cy <= y1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--model-timeout", default=60.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m8a macOS Fit-view pilot (PARTIAL: #18 hard, #19 evidence) ===")
    rep.log(f"datadir={args.datadir} model={args.model}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=args.model,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"blockers={app.extra.get('blockers')}")

        loaded, frame, blobs, _seen = _wait_model(
            driver, app, win, args.model_timeout)
        if frame is not None:
            frame.save_png(OUT / "before.png")
        rep.check("multi-plate project loads", loaded,
                  f"largest_blob={blobs[0].area if blobs else None} "
                  f"colored={frame.stats()['colored_fraction']:.4f}")
        if not loaded or not blobs:
            raise RuntimeError("model blob not found")

        # --- #18: select the largest model blob, then Fit ---------------
        target = blobs[0]
        rep.log(f"[INFO] click largest blob at ({target.cx:.0f},{target.cy:.0f}) "
                f"area={target.area:.0f}")
        driver.click(win.rect.x + target.cx, win.rect.y + target.cy)
        time.sleep(1.0)
        selected = driver.capture(win)
        selected.save_png(OUT / "selected.png")
        sel_blobs = blob_stats(selected)
        sel_model = _nearest(sel_blobs, target.cx, target.cy)
        sel_dist = (((sel_model.cx - target.cx) ** 2
                     + (sel_model.cy - target.cy) ** 2) ** 0.5
                    if sel_model else 1e9)
        rep.check("model selected",
                  sel_model is not None and sel_model.area >= MODEL_BLOB_MIN
                  and sel_dist < 80,
                  f"nearest_area={sel_model.area if sel_model else None} "
                  f"dist={sel_dist:.1f}")

        ok_fit = _fit(driver, win)
        time.sleep(1.5)
        fitted = driver.capture(win)
        fitted.save_png(OUT / "after_fit.png")
        fit_blobs = blob_stats(fitted)
        area1 = fit_blobs[0].area if fit_blobs else 0.0
        ratio = (area1 / target.area) if target.area else 0.0
        centered = bool(fit_blobs) and _centered(fit_blobs[0])
        diff18 = selected.difference(fitted)
        rep.check("#18 fit zooms to selection",
                  ok_fit and ratio >= 1.5 and centered,
                  f"fit_press={ok_fit} area {target.area:.0f}->{area1:.0f} "
                  f"ratio={ratio:.2f} centered={centered} diff={diff18:.4f}")

        # --- #19: Select All -> Fit (evidence only, Windows F-11 note) ---
        ok_all = _select_all(driver, win)
        time.sleep(1.0)
        ok_fit2 = _fit(driver, win)
        time.sleep(1.5)
        all_frame = driver.capture(win)
        all_frame.save_png(OUT / "after_select_all_fit.png")
        diff19 = fitted.difference(all_frame)
        rep.log(f"[INFO] #19 select_all={ok_all} fit={ok_fit2} "
                f"viewport_diff={diff19:.4f} (evidence only)")

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
        exit_code = rep.save({"partial": True,
                              "covered": ["#18"],
                              "evidence_only": ["#19"],
                              "not_covered": ["#16", "#17"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
