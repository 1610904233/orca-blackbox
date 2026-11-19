#!/usr/bin/env python3
# m8x_185_toolbar_add.py — macOS port: Feishu #185 toolbar "Add" import.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_185,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   empty boot -> toolbar Add button (tooltip "Add [Ctrl+1]") -> file chooser
#   -> model arrives -> object list shows the model name -> it lands at the
#   plate centre.
#
# macOS mapping:
#   toolbar Add -> custom-drawn icon at window-relative (490,75); the hover
#                  tooltip is the only text ("Add [...]").  Click it, then the
#                  native open panel is driven by driver.open_file_dialog.
#   arrival     -> viewport coloured fraction + object-list OCR.
#   placement   -> save the project and parse the build-item transform with
#                  mac_3mf (centre near the (135.5,136) plate centre).
#
# Artifacts: artifacts/mac/pilot/m8x_185/{report.log,result.json,work/*.3mf}.

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

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import (  # noqa: E402
    joined_text, recognize_text,
)
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import mac_3mf  # noqa: E402
import m7b_new_project as m7b  # noqa: E402
import m8x_202_save_as as c202  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_185"
DEFAULT_STL = HERE / "fixtures" / "cube20.stl"
EMPTY_BED_MAX = 0.015
COLORED_GATE = 0.0025
ADD_XY = (490, 75)                # toolbar Add icon (tooltip "Add [...]")
PLATE_CENTER = (135.5, 136.0)
POS_TOL_MM = 25.0
SIDE_MM = 20.0
SIDE_TOL = 0.01


def tooltip(driver, win, x, y) -> str:
    for _ in range(4):
        driver.move(win.rect.x + x, win.rect.y + y)
        time.sleep(1.5)
        words = recognize_text(
            driver.capture_screen(),
            Rect(win.rect.x + x - 120, win.rect.y + y + 10, 400, 80))
        text = " ".join(w.text for w in words).strip()
        if text:
            return text
    return ""


def wait_arrival(driver, win, timeout_s: float = 90.0):
    deadline = time.monotonic() + timeout_s
    last = None
    last_vp = 0.0
    while time.monotonic() < deadline:
        last = driver.capture(win)
        last_vp = m7b._vp_colored(last)
        if last_vp >= COLORED_GATE:
            time.sleep(1.5)
            frame2 = driver.capture(win)
            vp2 = m7b._vp_colored(frame2)
            if vp2 >= COLORED_GATE:
                return True, frame2, max(last_vp, vp2)
        time.sleep(1.0)
    return False, last, last_vp


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
    proj = work / "m8x_185_proj.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_185 macOS toolbar Add import ===")
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
        vp0 = m7b._vp_colored(driver.capture(win))
        rep.check("空盘启动", vp0 < EMPTY_BED_MAX, f"viewport={vp0:.4f}")

        tip = tooltip(driver, win, *ADD_XY)
        rep.log(f"[INFO] Add slot tooltip={tip!r}")
        rep.check("工具栏「添加」按钮", "add" in tip.lower()
                  and "plate" not in tip.lower(), f"tip={tip!r}")

        driver.click(win.rect.x + ADD_XY[0], win.rect.y + ADD_XY[1])
        panel = driver.find_file_dialog(
            win.pid, titles=driver._OPEN_PANEL_TITLES,
            exclude_id=win.id, timeout_s=8.0)
        rep.check("点击后弹出文件选择框", panel is not None,
                  f"panel={panel.title if panel else None}")
        imported = driver.open_file_dialog(win, cube) if panel else False
        rep.check("导入流程走通", imported)

        arrived, frame, vp = wait_arrival(driver, win)
        if frame is not None:
            frame.save_png(OUT / "after_import.png")
        title = driver._refresh(win).title
        rep.check("模型导入出现在场景", arrived,
                  f"viewport={vp:.4f} title={title!r}")
        if not arrived:
            raise RuntimeError("model did not arrive")

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
        rep.check("对象信息面板显示模型名", list_ok, f"ocr={ocr_tail[:160]!r}")

        rep.check("打开另存为面板", c202.open_save_as(driver, win, rep))
        saved = driver.save_file_dialog(win, proj, default_dir=work)
        rep.check("另存项目（供几何解析）", saved and proj.exists())
        if not proj.exists():
            raise RuntimeError("project save failed")

        geo = mac_3mf.read_project(proj)
        detail = ""
        placement_ok = False
        if len(geo.objects) == 1 and geo.objects[0].components:
            obj = geo.objects[0]
            comp = obj.components[0]
            verts = mac_3mf.read_mesh_vertices(proj, comp.path)
            item_t = next((t for oid, t in geo.items if oid == obj.id),
                          mac_3mf.IDENTITY)
            bounds = mac_3mf.world_aabb(
                verts, mac_3mf.compose(item_t, comp.transform))
            if bounds:
                (x0, y0, z0), (x1, y1, z1) = bounds
                dims = (x1 - x0, y1 - y0, z1 - z0)
                cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                dist = ((cx - PLATE_CENTER[0]) ** 2
                        + (cy - PLATE_CENTER[1]) ** 2) ** 0.5
                placement_ok = (dist <= POS_TOL_MM
                                and all(abs(d - SIDE_MM) <= SIDE_TOL
                                        for d in dims))
                detail = (f"dims={dims} center=({cx:.1f},{cy:.1f}) "
                          f"dist={dist:.1f}")
        rep.check("模型落于打印板中心", placement_ok, detail)
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
        exit_code = rep.save({"covered": ["#185"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
