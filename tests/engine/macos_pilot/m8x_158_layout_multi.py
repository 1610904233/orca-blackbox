#!/usr/bin/env python3
# m8x_158_layout_multi.py — macOS port: Feishu #158 multi-model layout +
# slice + export (local segment; device binding/printing needs real hardware).
# feishu: baseline#158  (macOS port; corresponds to the enabled Windows
#         m8x_158, registered in cases.MACOS_BASELINE)
#
# Windows assertions (local segment):
#   1) start empty, import three different models
#   2) the imported layout needs arranging (Windows drags the last model to
#      build a messy layout because imports auto-avoid there)
#   3) "A" (arrange all) puts every object back on the plate, no overlaps
#   4) slice completes and the exported gcode reports filament usage
#   5) the app closes normally
#
# macOS mapping:
#   imports   -> File > Import 3MF/STL... + driver.open_file_dialog, one file
#                at a time from the case's work dir.  On this build all three
#                imports land at the SAME bed position (135.5,136.0) and the
#                app raises "… is too close to others"; that naturally gives
#                the messy layout, so no drag/gizmo is needed.  S0 proves the
#                overlap.
#   arrange   -> canvas focus + "A" (m8x_188 recipe); S1 must show ≥1 object
#                moved ≥2mm, pairwise world-AABB gaps ≥2mm and every object
#                inside the U1 printable area.
#   slice     -> Slice plate (1000,45 at 1200x800) then File > Export G-code…
#                with the native save panel (accept_anywhere + fresh-file
#                discovery, as the export panel remembers a global folder).
#   gcode     -> mac_gcode.used_filaments() (same regex as the Windows case).
#
# Artifacts: artifacts/mac/pilot/m8x_158/{report.log,result.json,work/*.3mf,
#            *.png,*.gcode}.

from __future__ import annotations

import argparse
import math
import re
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
    slice_and_export,
)
import mac_3mf  # noqa: E402
import mac_gcode  # noqa: E402
import m8x_186_add_plate as c186  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_158"
DEFAULT_MODELS = (HERE / "fixtures" / "Prusa.stl",
                  HERE / "fixtures" / "cube20.stl",
                  HERE / "fixtures" / "prism12.stl")
BED = (0.5, 270.5, 1.0, 271.0)     # U1 printable area (same as m8x_188)
MIN_GAP = 2.0
MIN_MOVE = 2.0
EMPTY_BED_MAX = 0.015
VIEWPORT = (430, 100, 1080, 700)   # window-relative 3D viewport (m7h recipe)


def _vp_colored(frame) -> float:
    import numpy as np
    arr = np.frombuffer(frame.data, dtype=np.uint8).reshape(
        frame.height, frame.width, 4)
    b = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    r = arr[:, :, 2].astype(int)
    spread = np.maximum(np.maximum(b, g), r) - np.minimum(np.minimum(b, g), r)
    x0, y0, x1, y1 = VIEWPORT
    return float((spread[y0:y1, x0:x1] > 24).mean())


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def import_model(driver, win, path: Path) -> bool:
    rows = [c for c in driver.controls(win, max_depth=12)
            if c.role == "AXMenuItem"
            and c.title.strip().lower().startswith("import ")
            and "3mf" in c.title.lower()]
    if not rows:
        return False
    driver.click_control(rows[0])
    return driver.open_file_dialog(win, path)


def info_panel_has(driver, win, stem: str, timeout_s: float = 60.0) -> bool:
    """Poll the right-hand object info panel for the imported file stem."""
    deadline = time.monotonic() + timeout_s
    want = norm(stem)
    while time.monotonic() < deadline:
        frame = driver.capture(win)
        region = Rect(frame.width * 0.58, frame.height * 0.68,
                      frame.width * 0.42, frame.height * 0.32)
        words = recognize_text(frame, region)
        if want in norm(" ".join(w.text for w in words)):
            return True
        time.sleep(1.5)
    return False


def save_project(driver, win, rep, path: Path) -> bool:
    started = time.time()
    if c186.save_project(driver, win, rep, path):
        return True
    recovered = recover_saved_file(path, started, [ARTIFACTS / "pilot"])
    rep.log(f"[INFO] save recovery {path.name}: {recovered}")
    return recovered is not None


def gap(a, b) -> float:
    (a0, a1), (b0, b1) = a, b
    dx = max(a0[0] - b1[0], b0[0] - a1[0], 0.0)
    dy = max(a0[1] - b1[1], b0[1] - a1[1], 0.0)
    return math.hypot(dx, dy)


def inside(bounds) -> bool:
    lo, hi = bounds
    return (lo[0] >= BED[0] - 1e-3 and hi[0] <= BED[1] + 1e-3
            and lo[1] >= BED[2] - 1e-3 and hi[1] <= BED[3] + 1e-3)


def item_positions(path: Path) -> dict[str, tuple]:
    geo = mac_3mf.read_project(path)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    return {names.get(oid, oid): tuple(round(v, 3) for v in t[9:12])
            for oid, t in geo.items}


def export_project_gcode(driver, win, rep, gcode: Path, work: Path) -> bool:
    return slice_and_export(
        driver, win, rep, gcode,
        [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures",
         Path.home() / "Documents"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    models = []
    for src in DEFAULT_MODELS:
        dst = work / src.name
        shutil.copy2(src, dst)
        models.append(dst)
    p0 = work / "m8x_158_p0.3mf"
    p1 = work / "m8x_158_p1.3mf"
    gcode = work / "m8x_158.gcode"

    rep = Reporter(OUT)
    rep.log("=== m8x_158 macOS multi-model layout + slice ===")
    rep.log(f"datadir={args.datadir} models={[p.name for p in models]}")

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
        rep.check("launch (empty project)", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"rect={win.rect.to_xywh()}")
        time.sleep(4.0)
        empty_frame = driver.capture(win)
        empty_frame.save_png(OUT / "empty.png")
        empty_frac = _vp_colored(empty_frame)
        rep.check("启动 Orca（空盘）", empty_frac < EMPTY_BED_MAX,
                  f"viewport_colored={empty_frac:.4f}")

        names = []
        imported = 0
        for path in models:
            if import_model(driver, win, path):
                if info_panel_has(driver, win, path.stem):
                    imported += 1
                    names.append(path.stem)
                else:
                    rep.log(f"[INFO] import {path.name}: info panel missing")
            time.sleep(1.0)
        driver.capture(win).save_png(OUT / "imported.png")
        rep.check("导入多个模型（3 个）", imported >= 3,
                  f"imported={imported} names={names}")
        if imported < 3:
            return rep.save({"stage": "import"})

        if not save_project(driver, win, rep, p0):
            rep.check("另存 P0（导入后）", False, "save panel failed")
            return rep.save({"stage": "save-p0"})
        plates0 = mac_3mf.read_plates(p0)
        pos0 = item_positions(p0)
        rep.log(f"[INFO] P0 plates={plates0}")
        rep.log(f"[INFO] P0 positions={pos0}")
        rep.check("三个对象在同一盘（1 号盘）",
                  len(plates0.get("1", [])) == 3,
                  f"plate1={plates0.get('1')}")
        xy0 = {(round(t[0], 3), round(t[1], 3)) for t in pos0.values()}
        rep.check("导入后布局待整理（三个对象同一位姿）",
                  len(pos0) == 3 and len(xy0) == 1,
                  f"positions={pos0}")

        # Arrange all: focus the canvas, press A.
        driver.click(win.rect.x + 1000, win.rect.y + 300)
        time.sleep(0.5)
        driver.send_key("a")
        time.sleep(6.0)
        driver.capture(win).save_png(OUT / "after_arrange.png")
        if not save_project(driver, win, rep, p1):
            rep.check("另存 P1（整理后）", False, "save panel failed")
            return rep.save({"stage": "save-p1"})
        plates1 = mac_3mf.read_plates(p1)
        pos1 = item_positions(p1)
        rep.log(f"[INFO] P1 plates={plates1}")
        rep.log(f"[INFO] P1 positions={pos1}")
        rep.check("整理后三个对象仍存在", len(pos1) >= 3, f"objects={len(pos1)}")
        moved = [name for name in pos0 if name in pos1
                 and math.hypot(pos1[name][0] - pos0[name][0],
                                pos1[name][1] - pos0[name][1]) >= MIN_MOVE]
        rep.check("模型整理（≥1 对象移动 ≥2mm）", bool(moved),
                  f"moved={moved}")

        aabbs = mac_3mf.object_world_aabbs(p1)
        rep.log(f"[INFO] P1 AABBs={aabbs}")
        labels = list(aabbs)
        gaps = [(labels[i], labels[j],
                 gap(aabbs[labels[i]], aabbs[labels[j]]))
                for i in range(len(labels)) for j in range(i + 1, len(labels))]
        rep.check("整理后对象互不重叠（AABB 间距 ≥2mm）",
                  bool(gaps) and all(g >= MIN_GAP - 1e-3 for _a, _b, g in gaps),
                  f"gaps={[(a, b, round(g, 2)) for a, b, g in gaps]}")
        outside = [n for n, b in aabbs.items() if not inside(b)]
        rep.check("对象均在 U1 可打印区内", bool(aabbs) and not outside,
                  f"outside={outside}")

        # Slice + export; device upload/print is out of black-box scope.
        if not export_project_gcode(driver, win, rep, gcode, work):
            rep.check("切片完成并导出 G-code", False, "slice/export failed")
            return rep.save({"stage": "slice"})
        rep.check("切片完成并导出 G-code", True,
                  f"size={gcode.stat().st_size if gcode.exists() else 0}")
        rep.check("G-code 导出文件非空", gcode.exists()
                  and gcode.stat().st_size > 0,
                  f"size={gcode.stat().st_size if gcode.exists() else 0}")
        data = gcode.read_bytes() if gcode.exists() else b""
        used = mac_gcode.used_filaments(data)
        rep.log(f"[INFO] gcode filaments={used} bytes={len(data)}")
        rep.check("G-code 用量可读", bool(used), f"used={used}")

        alive_before = app.alive()
        closed = close_app(driver, app, win)
        app = None
        rep.check("软件正常关闭", alive_before and closed,
                  f"alive_before={alive_before} closed={closed}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None and not args.keep:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        exit_code = rep.save({"covered": ["#158"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
