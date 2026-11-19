#!/usr/bin/env python3
# m8x_203_import_stl.py — macOS port: Feishu #203 import via File menu.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_203,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions (3mf geometry + render):
#   1) empty bed -> File > Import -> cube20.stl arrives in the scene
#   2) the saved project has exactly one item named cube20
#   3) vertex AABB = 20 x 20 x 20 mm
#   4) placed near the plate centre (|Δ| <= 25mm from (135.5,136))
#
# macOS mapping:
#   import       -> File > "Import 3MF/STL/STEP/SVG/OBJ/AMF..." + open dialog
#   object list  -> OCR the main window for "cube20" after the panel closes
#   geometry     -> save the project and parse 3D/3dmodel.model + the external
#                   mesh with mac_3mf.py (object name, build-item transform,
#                   vertices, world AABB)
#
# Artifacts: artifacts/mac/pilot/m8x_203/{report.log,result.json,work/*.3mf}.

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
from harness.platform.macos_ocr import (  # noqa: E402
    joined_text, recognize_text,
)
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, recover_saved_file,
)
import mac_3mf  # noqa: E402
import m7b_new_project as m7b  # noqa: E402
import m8x_202_save_as as c202  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_203"
DEFAULT_STL = HERE / "fixtures" / "cube20.stl"
EMPTY_BED_MAX = 0.015
COLORED_GATE = 0.0025
VIEWPORT = (430, 100, 1080, 700)
PLATE_CENTER = (135.5, 136.0)          # import placement measured on Windows
POS_TOL_MM = 25.0
SIDE_MM = 20.0
SIDE_TOL = 0.01


def blob_count(frame) -> int:
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


def wait_arrival(driver, win, before_vp: float, timeout_s: float = 90.0):
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
    cube = work / "cube20.stl"
    shutil.copy2(args.stl, cube)
    proj = work / "m8x_203_proj.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_203 macOS import via File menu ===")
    rep.log(f"datadir={args.datadir} stl={cube}")

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
        rep.check("开局空盘（无模型）", vp0 < EMPTY_BED_MAX,
                  f"viewport={vp0:.4f}")

        rows = [c for c in driver.controls(win, max_depth=12)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("import ")
                and "3mf" in c.title.lower()]
        rep.check("文件 → 导入入口存在", bool(rows),
                  f"rows={[c.title for c in rows]}")
        if not rows:
            raise RuntimeError("no Import menu row")
        driver.click_control(rows[0])
        imported = driver.open_file_dialog(win, cube)
        rep.check("文件 → 导入 → 选择 STL", imported)

        arrived, frame, vp, blobs = wait_arrival(driver, win, vp0)
        if frame is not None:
            frame.save_png(OUT / "after_import.png")
        title = driver._refresh(win).title
        rep.check("模型出现在场景", arrived,
                  f"viewport {vp0:.4f}->{vp:.4f} blobs={blobs} title={title!r}")
        if not arrived:
            raise RuntimeError("imported model did not arrive")

        # Object list name (poll only after the open panel is gone).
        deadline = time.monotonic() + 30.0
        list_ok = False
        ocr_tail = ""
        while time.monotonic() < deadline:
            panel_open = driver.find_file_dialog(
                win.pid, titles=driver._OPEN_PANEL_TITLES,
                exclude_id=win.id, timeout_s=0.0) is not None
            if not panel_open:
                ocr_tail = joined_text(
                    recognize_text(driver.capture_screen().crop(win.rect)))
                if "cube20" in ocr_tail.lower():
                    list_ok = True
                    break
            time.sleep(1.5)
        rep.check("对象列表新增（cube20）", list_ok, f"ocr={ocr_tail[:160]!r}")

        rep.check("打开另存为面板", c202.open_save_as(driver, win, rep))
        started = time.time()
        saved = driver.save_file_dialog(win, proj, default_dir=work)
        if not proj.exists():
            rec = recover_saved_file(
                proj, started,
                [work, ARTIFACTS / "pilot", HERE / "fixtures"])
            saved = rec is not None
        rep.check("另存项目（供几何解析）", saved and proj.exists(),
                  f"size={proj.stat().st_size if proj.exists() else 0}")
        if not proj.exists():
            raise RuntimeError("project save failed")

        geo = mac_3mf.read_project(proj)
        rep.log(f"[INFO] objects={[(o.id, o.name, len(o.components)) for o in geo.objects]} "
                f"items={geo.items}")
        named = [o for o in geo.objects if "cube20" in (o.name or "").lower()]
        rep.check("3mf 恰 1 项且名为 cube20",
                  len(geo.objects) == 1 and len(geo.items) == 1
                  and len(named) == 1,
                  f"objects={[o.name for o in geo.objects]} "
                  f"items={len(geo.items)}")

        aabb_ok = False
        pos_ok = False
        detail = ""
        if len(geo.objects) == 1 and geo.objects[0].components:
            obj = geo.objects[0]
            comp = obj.components[0]
            verts = mac_3mf.read_mesh_vertices(proj, comp.path)
            item_t = next((t for oid, t in geo.items if oid == obj.id),
                          mac_3mf.IDENTITY)
            world_t = mac_3mf.compose(item_t, comp.transform)
            bounds = mac_3mf.world_aabb(verts, world_t)
            detail = f"verts={len(verts)} aabb={bounds}"
            if bounds:
                (x0, y0, z0), (x1, y1, z1) = bounds
                dims = (x1 - x0, y1 - y0, z1 - z0)
                aabb_ok = all(abs(d - SIDE_MM) <= SIDE_TOL for d in dims)
                cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                dist = ((cx - PLATE_CENTER[0]) ** 2
                        + (cy - PLATE_CENTER[1]) ** 2) ** 0.5
                pos_ok = dist <= POS_TOL_MM
                detail += f" dims={dims} center=({cx:.1f},{cy:.1f}) dist={dist:.1f}"
        rep.check("20mm 立方体（顶点 AABB）", aabb_ok, detail)
        rep.check("落于打印板中心（|Δ|≤25mm）", pos_ok, detail)

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
        exit_code = rep.save({"covered": ["#203"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
