#!/usr/bin/env python3
# m8x_156.py — macOS port: Feishu #156 drag transforms + slice.
# feishu: baseline#156  (macOS port; corresponds to the enabled Windows
#         m8x_156, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   s1 import STL -> Rotate Z=45 (drag preferred, field fallback)
#   s2 Move by dragging the object -> Position X changes 100 -> 154.77
#   s3 Scale by dragging a handle -> Scale changes 100 -> 83.35
#   s4 slice -> a readable single-filament usage in gcode
#
# macOS mapping (one gizmo per session, as on Windows):
#   s1 -> import Prusa.stl; the red Move arrow is dragged at (860,430),
#         Position X must increase while Y stays.
#   s2 -> CLI-load Prusa; Rotate row Z=45 (the arrow cone is not a stable
#         hit target; Windows also falls back to input).
#   s3 -> CLI-load Prusa; Scale corner handle at (848,444) is dragged out,
#         the first percentage must increase.
#   s4 -> CLI-load Prusa; slice_and_export + used_filaments.
#   Move/Rotate/Scale slots come from one tooltip scan (the seeded printer
#   moved them); Rotate's row is OCR-located.
#
# Artifacts: artifacts/mac/pilot/m8x_156/{report.log,result.json,*.png,
#            work/*.gcode,*.3mf}.

from __future__ import annotations

import argparse
import shutil
import sys
import time
import traceback
from pathlib import Path

import cv2
import numpy as np

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
import m8x_191 as c191  # noqa: E402
import m8x_192 as c192  # noqa: E402
import m7t74 as c74  # noqa: E402
from m8b_official_color import drag  # noqa: E402
from m8x_152 import find_transform_slots  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_156"
STL = HERE / "fixtures" / "Prusa.stl"
MODEL_POINT = (814, 481)
MOVE_ARROW = (860, 430)
SCALE_HANDLE = (848, 444)
SCALE_HANDLE_END = (868, 424)
MOVE_X = 761                # seeded-U1 layout; tooltip scan below
ROTATE_X = 793
SCALE_X = 825
_SLOTS = None


def transform_slots(driver, win):
    """Scan once per process; toolbar layout is identical across sessions."""
    global _SLOTS
    if _SLOTS is None:
        _SLOTS = find_transform_slots(driver, win)
    return _SLOTS


def ocr(driver, win):
    return recognize_text(driver.capture(win))


def numbers(driver, win, y, xmin=880):
    out = []
    for w in ocr(driver, win):
        if abs(w.rect.y - y) < 7 and w.rect.x > xmin:
            try:
                out.append(float(w.text.replace("%", "")))
            except ValueError:
                pass
    return out


def click_model(driver, win) -> bool:
    """Select the loaded Prusa; canvas hit-test, then the Objects tree.

    The object-info panel ("Object name: Prusa.stl") is the proof — a bare
    'prusa.stl' can also come from the tree or a tooltip.  A CLI-loaded
    model is not at the same screen point as a File>Import one, which made
    the old canvas-only hit-test miss in the rotate/scale sessions.
    """
    def selected() -> bool:
        text = " ".join(w.text for w in ocr(driver, win)).lower()
        # Full-window OCR can misread "Object" as "Obiect"; Size is the
        # second line of the same info panel.
        return "prusa.stl" in text and (
            "object name" in text or "obiect name" in text or "size:" in text)

    if selected():
        return True
    for x, y in ((814, 481), (814, 470), (814, 492), (800, 481),
                 (828, 481), (790, 485), (840, 485),
                 (814, 429), (814, 440), (814, 450), (814, 500),
                 (814, 510), (800, 460), (828, 460)):
        driver.click(win.rect.x + x, win.rect.y + y)
        time.sleep(0.7)
        if selected():
            return True
    words = ocr(driver, win)
    tab = next((w for w in words
                if w.text.strip().lower() == "objects"
                and w.rect.x < 450), None)
    point = tab.rect.center if tab else (152, 520)
    driver.click(win.rect.x + point[0], win.rect.y + point[1])
    time.sleep(1.5)
    words = ocr(driver, win)
    plate = next((w for w in words
                  if "plate 1" in w.text.lower()
                  and w.rect.x < 430 and w.rect.y > 500), None)
    if plate is not None:
        driver.click(win.rect.x + 30, win.rect.y + plate.rect.y + 23)
        time.sleep(2.0)
        if selected():
            return True
    row = next((w for w in words
                if "prusa" in w.text.lower()
                and w.rect.x < 430 and w.rect.y > 500), None)
    if row is not None:
        driver.click(win.rect.x + row.rect.center[0],
                     win.rect.y + row.rect.center[1])
        time.sleep(2.0)
    return selected()


def scale_handles(driver, win):
    """Teal corner cubes of the Scale gizmo (the seeded layout moved them).

    The old fixed (848,444) was far outside the gizmo; detect the small
    teal squares in the viewport and let the caller drag the outermost one
    away from their centroid.
    """
    frame = driver.capture(win)
    arr = np.frombuffer(frame.data, dtype=np.uint8).reshape(
        frame.height, frame.width, 4)
    b, g, r = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    mask = ((b > 110) & (g > 120) & (r < 110)).astype(np.uint8)
    mask[:300, :] = 0          # exclude toolbar/paint icons
    mask[:, :650] = 0          # exclude the left panels
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        _x, _y, w, h, area = stats[i]
        if 60 <= area <= 600 and 8 <= w <= 30 and 8 <= h <= 30:
            out.append((int(cents[i][0]), int(cents[i][1])))
    ys, xs = np.nonzero(mask)
    center = (float(xs.mean()), float(ys.mean())) if len(xs) else None
    return out, center


def paste(driver, win, x, y, text):
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


def import_stl(driver, win, rep) -> bool:
    rows = [c for c in driver.controls(win, max_depth=12)
            if c.role == "AXMenuItem"
            and c.title.strip().lower().startswith("import ")
            and "3mf" in c.title.lower()]
    if not rows:
        return False
    driver.click_control(rows[0])
    return driver.open_file_dialog(win, STL)


def session_move(driver, datadir, rep):
    app = None
    win = None
    try:
        app, win = launch_and_focus(driver, datadir, model=None,
                                    timeout_s=150.0,
                                    log_path=OUT / "launch_move.log")
        time.sleep(3.0)
        rep.check("s1 导入 STL", import_stl(driver, win, rep))
        ok, _f, frac, _s = wait_for_model(driver, app, win,
                                          timeout_s=120.0, threshold=0.0025)
        rep.check("s1 模型落盘", ok, f"colored={frac:.4f}")
        if not ok:
            return False
        rep.check("s2 选中模型", click_model(driver, win))
        slot, tip = transform_slots(driver, win).get(
            "move", ((MOVE_X, 75), ""))
        rep.log(f"[INFO] Move slot={slot} tip={tip!r}")
        driver.click(win.rect.x + slot[0], win.rect.y + slot[1])
        time.sleep(1.5)
        before = numbers(driver, win, 142)
        rep.log(f"[INFO] move before={before}")
        drag(win.rect.x + MOVE_ARROW[0], win.rect.y + MOVE_ARROW[1],
             win.rect.x + MOVE_ARROW[0] + 35,
             win.rect.y + MOVE_ARROW[1])
        time.sleep(1.5)
        after = numbers(driver, win, 142)
        driver.capture(win).save_png(OUT / "move_drag.png")
        rep.log(f"[INFO] move after={after}")
        moved = (len(before) >= 2 and len(after) >= 2
                 and after[0] - before[0] >= 10.0
                 and abs(after[1] - before[1]) <= 0.5)
        rep.check("s2 Move 拖拽：X 增大、Y 不变", moved,
                  f"{before} -> {after}")
        return moved
    finally:
        if app is not None:
            close_app(driver, app, win)


def session_rotate(driver, datadir, rep):
    app = None
    win = None
    try:
        app, win = launch_and_focus(driver, datadir, model=STL,
                                    timeout_s=150.0,
                                    log_path=OUT / "launch_rotate.log")
        ok, _f, _frac, _s = wait_for_model(driver, app, win,
                                           timeout_s=120.0, threshold=0.01)
        rep.check("s3 模型载入", ok)
        if not ok:
            return False
        rep.check("s3 选中模型", click_model(driver, win))
        slot, tip = transform_slots(driver, win).get(
            "rotate", ((ROTATE_X, 75), ""))
        rep.log(f"[INFO] Rotate slot={slot} tip={tip!r}")
        driver.click(win.rect.x + slot[0], win.rect.y + slot[1])
        time.sleep(1.5)
        rows = c191.rotate_row_fields(driver, win)
        rel = rows.get("rel") or [(921, 148), (984, 148), (1047, 148)]
        rep.log(f"[INFO] Rotate rows={rows}")
        paste(driver, win, rel[2][0], rel[2][1], "45")
        proj = datadir / "rotate.3mf"
        rep.check("s3 另存旋转项目",
                  c192.save_project(driver, win, rep, proj) and proj.exists())
        t = c192.item(proj, "Prusa")
        ang, axis, _norms = c74.mat_info(t) if t is not None else (0, [], [])
        rep.log(f"[INFO] rotate t={t} ang={ang:.1f} axis={axis}")
        ok = (t is not None and abs(ang - 45.0) <= 2.0
              and abs(axis[2]) >= 0.95)
        rep.check("s1 Rotate Z=45（输入回退）", ok,
                  f"ang={ang:.1f} axis={axis}")
        return ok
    finally:
        if app is not None:
            close_app(driver, app, win)


def session_scale(driver, datadir, rep):
    app = None
    win = None
    try:
        app, win = launch_and_focus(driver, datadir, model=STL,
                                    timeout_s=150.0,
                                    log_path=OUT / "launch_scale.log")
        ok, _f, _frac, _s = wait_for_model(driver, app, win,
                                           timeout_s=120.0, threshold=0.01)
        rep.check("s4 模型载入", ok)
        if not ok:
            return False
        rep.check("s4 选中模型", click_model(driver, win))
        slot, tip = transform_slots(driver, win).get(
            "scale", ((SCALE_X, 75), ""))
        rep.log(f"[INFO] Scale slot={slot} tip={tip!r}")
        driver.click(win.rect.x + slot[0], win.rect.y + slot[1])
        time.sleep(1.5)
        before = numbers(driver, win, 142, xmin=930)
        rep.log(f"[INFO] scale before={before}")
        pts, center = scale_handles(driver, win)
        rep.log(f"[INFO] scale handles={pts} center={center}")
        hx, hy = SCALE_HANDLE
        cx, cy = center or (820.0, 330.0)
        if pts:
            hx, hy = max(pts, key=lambda p: (p[0] - cx) ** 2
                         + (p[1] - cy) ** 2)
            dx, dy = hx - cx, hy - cy
            if abs(dx) + abs(dy) < 1.0:   # single handle: use up-right
                dx, dy = 1.0, -1.0
            norm = max(1.0, (dx * dx + dy * dy) ** 0.5)
            ex = int(round(hx + dx / norm * 25.0))
            ey = int(round(hy + dy / norm * 25.0))
        else:
            ex, ey = SCALE_HANDLE_END
        rep.log(f"[INFO] scale drag=({hx},{hy})->({ex},{ey})")
        drag(win.rect.x + hx, win.rect.y + hy,
             win.rect.x + ex, win.rect.y + ey)
        time.sleep(1.2)
        after = numbers(driver, win, 142, xmin=930)
        driver.capture(win).save_png(OUT / "scale_drag.png")
        rep.log(f"[INFO] scale after={after}")
        changed = (bool(before) and bool(after)
                   and abs(after[0] - before[0]) >= 5.0)
        rep.check("s3 Scale 拖拽手柄生效", changed, f"{before} -> {after}")
        return changed
    finally:
        if app is not None:
            close_app(driver, app, win)


def session_slice(driver, datadir, rep, gcode):
    app = None
    win = None
    try:
        app, win = launch_and_focus(driver, datadir, model=STL,
                                    timeout_s=150.0,
                                    log_path=OUT / "launch_slice.log")
        ok, _f, _frac, _s = wait_for_model(driver, app, win,
                                           timeout_s=120.0, threshold=0.01)
        rep.check("s5 模型载入", ok)
        if not ok:
            return False
        if not slice_and_export(driver, win, rep, gcode,
                                [datadir, OUT, ARTIFACTS / "pilot",
                                 HERE / "fixtures"]):
            rep.check("s4 切片完成", False, "slice/export failed")
            return False
        used = mac_gcode.used_filaments(gcode.read_bytes())
        rep.check("s4 切片完成", gcode.exists() and gcode.stat().st_size > 0,
                  f"used={used} size={gcode.stat().st_size}")
        rep.check("s4 单耗材用量可读", len(used) >= 1, f"used={used}")
        return bool(used)
    finally:
        if app is not None:
            close_app(driver, app, win)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    work = OUT / "work"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    gcode = work / "m8x_156.gcode"

    rep = Reporter(OUT)
    rep.log("=== m8x_156 macOS drag transforms + slice ===")
    rep.log(f"stl={STL}")

    driver = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        results = [
            session_move(driver, work / "move", rep),
            session_rotate(driver, work / "rotate", rep),
            session_scale(driver, work / "scale", rep),
            session_slice(driver, work / "slice", rep, gcode),
        ]
        rep.check("所有会话通过", all(results), f"results={results}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        pkill = __import__("subprocess").run(
            ["pkill", "-f", "Snapmaker_Orca --datadir"], capture_output=True)
        exit_code = rep.save({"covered": ["#156"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
