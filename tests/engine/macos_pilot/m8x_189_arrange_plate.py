#!/usr/bin/env python3
# m8x_189_arrange_plate.py — macOS port: Feishu #189 arrange current plate.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_189,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions (project 3mf geometry):
#   plate 1 = Prusa (spectator), plate 2 = two overlapping cube20 (current)
#   -> Shift+A -> only plate 2 is arranged:
#     plate map unchanged (no plate deleted / object migrated)
#     Prusa item transform bit-identical
#     >=1 cube moves >=2mm; the two cube AABBs are >=2mm apart
#     cubes stay inside the 270x270 plate window
#
# macOS mapping:
#   Shift+A -> real key with the shift modifier after focusing the canvas.
#   geometry -> mac_3mf: detailed plate map (ids+names), item transforms,
#               per-object-id world AABBs (two objects share the name).
#
# Artifacts: artifacts/mac/pilot/m8x_189/{report.log,result.json,work/*.3mf}.

from __future__ import annotations

import argparse
import math
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
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import mac_3mf  # noqa: E402
import m8x_186_add_plate as c186  # noqa: E402
import m8x_202_save_as as c202  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_189"
DEFAULT_MODEL = HERE / "fixtures" / "Prusa.stl"
DEFAULT_STL = HERE / "fixtures" / "cube20.stl"
BED = (0.5, 270.5, 1.0, 271.0)
MIN_GAP = 2.0
MIN_MOVE = 2.0
EPS = 1e-3


def find_add_plate_slot(driver, win):
    """Toolbar layout depends on the project; scan for 'Add plate' tooltip."""
    for x in range(460, 571, 10):
        driver.move(win.rect.x + x, win.rect.y + 75)
        time.sleep(1.0)
        words = recognize_text(
            driver.capture_screen(),
            Rect(win.rect.x + x - 120, win.rect.y + 85, 400, 80))
        text = " ".join(w.text for w in words).strip()
        if "add plate" in text.lower():
            return (x, 75), text
    return None, ""


def save_project(driver, win, rep, path: Path) -> bool:
    if not c202.open_save_as(driver, win, rep):
        return False
    return driver.save_file_dialog(win, path, default_dir=path.parent)


def transforms_by_name(path: Path) -> dict[str, list[tuple]]:
    geo = mac_3mf.read_project(path)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    out: dict[str, list[tuple]] = {}
    for oid, t in geo.items:
        out.setdefault(names.get(oid, oid), []).append(t)
    return out


def gap(a, b) -> float:
    (a0, a1), (b0, b1) = a, b
    dx = max(a0[0] - b1[0], b0[0] - a1[0], 0.0)
    dy = max(a0[1] - b1[1], b0[1] - a1[1], 0.0)
    return math.hypot(dx, dy)


def inside(bounds) -> bool:
    lo, hi = bounds
    return (lo[0] >= BED[0] - EPS and hi[0] <= BED[1] + EPS
            and lo[1] >= BED[2] - EPS and hi[1] <= BED[3] + EPS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--stl", default=DEFAULT_STL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    model = work / "prusa.stl"
    shutil.copy2(args.model, model)
    cube = work / "cube20.stl"
    shutil.copy2(args.stl, cube)
    p0 = work / "m8x_189_p0.3mf"
    p1 = work / "m8x_189_p1.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_189 macOS arrange current plate ===")
    rep.log(f"datadir={args.datadir} model={model}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=model,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"blockers={app.extra.get('blockers')}")
        time.sleep(3.0)

        # Add plate 2 (current).  The toolbar Add-plate slot moves with the
        # project layout, so scan the tooltip instead of using a fixed x.
        slot, tip = find_add_plate_slot(driver, win)
        rep.log(f"[INFO] Add plate slot={slot} tip={tip!r}")
        if slot is None:
            slot = c186.ADD_PLATE_XY
        plate_ok = False
        last = None
        for attempt in range(1, 4):
            driver.click(win.rect.x + slot[0], win.rect.y + slot[1])
            time.sleep(2.0)
            cand = work / f"m8x_189_add{attempt}.3mf"
            last = cand
            if save_project(driver, win, rep, cand) and \
                    len(mac_3mf.read_plates(cand)) == 2:
                plate_ok = True
                break
        rep.check("添加 2 号盘", plate_ok,
                  f"last={last.name if last else None}")
        if not plate_ok:
            raise RuntimeError("plate 2 not created")

        rows = [c for c in driver.controls(win, max_depth=12)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("import ")
                and "3mf" in c.title.lower()]
        rep.check("导入入口可用", bool(rows))
        for i in range(2):
            ok = False
            for attempt in range(3):
                menu = [c for c in driver.controls(win, max_depth=12)
                        if c.role == "AXMenuItem"
                        and c.title.strip().lower().startswith("import ")
                        and "3mf" in c.title.lower()]
                if not menu:
                    break
                driver.click_control(menu[0])
                time.sleep(1.2)
                ok = driver.open_file_dialog(win, cube)
                if ok:
                    break
                driver.send_key("escape")
                time.sleep(1.0)
            rep.check(f"2 号盘导入 cube20 #{i + 1}", ok)
            time.sleep(2.5)

        rep.check("基线项目保存", save_project(driver, win, rep, p0)
                  and p0.exists())
        plates0 = mac_3mf.read_plates_detailed(p0)
        rep.log(f"[INFO] P0 plates={ {k: [n for _i, n in v] for k, v in plates0.items()} }")
        ok_base = (len(plates0) == 2
                   and len(plates0.get("1", [])) == 1
                   and len(plates0.get("2", [])) == 2)
        rep.check("P0 基线（1 盘 Prusa / 2 盘两 cube）", ok_base,
                  f"plates={ {k: len(v) for k, v in plates0.items()} }")
        if not p0.exists() or not ok_base:
            raise RuntimeError("baseline layout not reached")

        t0 = transforms_by_name(p0)
        rep.log(f"[INFO] P0 transforms={t0}")

        driver.click(win.rect.x + 1000, win.rect.y + 300)
        time.sleep(0.5)
        driver.send_key("a", modifiers=("shift",))
        time.sleep(6.0)
        rep.check("整理后项目保存", save_project(driver, win, rep, p1)
                  and p1.exists())
        t1 = transforms_by_name(p1)
        plates1 = mac_3mf.read_plates_detailed(p1)
        rep.log(f"[INFO] P1 transforms={t1} "
                f"plates={ {k: [n for _i, n in v] for k, v in plates1.items()} }")

        rep.check("盘映射不变（不删盘不迁对象）",
                  {k: sorted(n for _i, n in v) for k, v in plates0.items()}
                  == {k: sorted(n for _i, n in v) for k, v in plates1.items()},
                  f"plates={ {k: len(v) for k, v in plates1.items()} }")

        p0p = t0.get("prusa.stl", [None])[0]
        p1p = t1.get("prusa.stl", [None])[0]
        rep.check("1 号盘 Prusa 位姿逐位不变",
                  p0p is not None and p1p is not None
                  and tuple(round(v, 6) for v in p0p)
                  == tuple(round(v, 6) for v in p1p),
                  f"{p0p} -> {p1p}")

        cubes0 = t0.get("cube20.stl", [])
        cubes1 = t1.get("cube20.stl", [])
        moved = []
        for c0 in cubes0:
            dist = min((math.hypot(c1[9] - c0[9], c1[10] - c0[10])
                        for c1 in cubes1), default=0.0)
            if dist >= MIN_MOVE:
                moved.append(round(dist, 2))
        rep.check("≥1 个 cube 移动 ≥2mm", bool(moved), f"moves={moved}")

        aabbs = mac_3mf.object_aabbs_by_id(p1)
        cube_boxes = [b for _oid, (name, b) in aabbs.items()
                      if "cube20" in name.lower()]
        gaps = []
        for i in range(len(cube_boxes)):
            for j in range(i + 1, len(cube_boxes)):
                gaps.append(gap(cube_boxes[i], cube_boxes[j]))
        rep.check("两 cube 无重叠（AABB 间距 ≥2mm）",
                  len(cube_boxes) == 2
                  and all(g >= MIN_GAP - EPS for g in gaps),
                  f"gaps={[round(g, 2) for g in gaps]} n={len(cube_boxes)}")
        # Plates are laid out with an unknown pitch in global coordinates, so
        # (as on Windows) check that the cube cluster fits a 270x270 plate
        # window instead of absolute bed coordinates.
        cluster_ok = False
        if cube_boxes:
            lo = (min(b[0][0] for b in cube_boxes),
                  min(b[0][1] for b in cube_boxes))
            hi = (max(b[1][0] for b in cube_boxes),
                  max(b[1][1] for b in cube_boxes))
            width, height = hi[0] - lo[0], hi[1] - lo[1]
            cluster_ok = width <= 270.0 + EPS and height <= 270.0 + EPS
            detail = f"cluster={width:.1f}x{height:.1f}"
        else:
            detail = "no cube boxes"
        rep.check("cube 簇在 270×270 盘窗口内", cluster_ok, detail)

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
        exit_code = rep.save({"covered": ["#189"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
