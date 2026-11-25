#!/usr/bin/env python3
# m8x_188_arrange_all.py — macOS port: Feishu #188 global arrange.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_188,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions (project 3mf geometry):
#   two objects on plate 1 + one empty plate -> press A (arrange all) ->
#   objects re-arranged (>=1 moves >=2mm), no overlap (AABB gap >=2mm),
#   inside the U1 printable area [0.5,270.5]x[1,271], empty plate removed.
#
# macOS mapping:
#   Arange all -> the "A" shortcut works once the canvas has focus (the
#                 toolbar icon only shows a tooltip; verified in a probe).
#   geometry   -> mac_3mf: plate map, item transforms, per-object world AABBs.
#
# Artifacts: artifacts/mac/pilot/m8x_188/{report.log,result.json,work/*.3mf}.

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

OUT = ARTIFACTS / "pilot" / "m8x_188"
DEFAULT_MODEL = HERE / "fixtures" / "Prusa.stl"
DEFAULT_STL = HERE / "fixtures" / "cube20.stl"
BED = (0.5, 270.5, 1.0, 271.0)     # xmin,xmax,ymin,ymax (U1)
MIN_GAP = 2.0
MIN_MOVE = 2.0


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


def transforms(path: Path) -> dict[str, tuple]:
    geo = mac_3mf.read_project(path)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    return {names.get(oid, oid): t for oid, t in geo.items}


def gap(a, b) -> float:
    (a0, a1) = a
    (b0, b1) = b
    dx = max(a0[0] - b1[0], b0[0] - a1[0], 0.0)
    dy = max(a0[1] - b1[1], b0[1] - a1[1], 0.0)
    return math.hypot(dx, dy)


def inside(bounds) -> bool:
    lo, hi = bounds
    return (lo[0] >= BED[0] - 1e-3 and hi[0] <= BED[1] + 1e-3
            and lo[1] >= BED[2] - 1e-3 and hi[1] <= BED[3] + 1e-3)


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
    p0 = work / "m8x_188_p0.3mf"
    p1 = work / "m8x_188_p1.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_188 macOS global arrange ===")
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

        rows = [c for c in driver.controls(win, max_depth=12)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("import ")
                and "3mf" in c.title.lower()]
        rep.check("导入入口可用", bool(rows))
        driver.click_control(rows[0])
        imported = driver.open_file_dialog(win, cube)
        rep.check("同盘导入 cube20（两对象）", imported)
        time.sleep(3.0)

        # Add an empty plate (toolbar icon; verify +1 by saving).
        slot, tip = find_add_plate_slot(driver, win)
        rep.log(f"[INFO] Add plate slot={slot} tip={tip!r}")
        if slot is None:
            slot = c186.ADD_PLATE_XY
        plates = None
        for attempt in range(1, 4):
            driver.click(win.rect.x + slot[0], win.rect.y + slot[1])
            time.sleep(2.0)
            cand = work / f"m8x_188_add{attempt}.3mf"
            if not save_project(driver, win, rep, cand):
                continue
            plates = mac_3mf.read_plates(cand)
            rep.log(f"[INFO] add attempt {attempt}: plates={len(plates)}")
            if len(plates) == 2:
                shutil.copy2(cand, p0)
                break
        rep.check("基线：两盘（其二为空）",
                  plates is not None and len(plates) == 2
                  and any(v == [] for v in plates.values()),
                  f"plates={ {k: len(v) for k, v in (plates or {}).items()} }")
        if not p0.exists():
            raise RuntimeError("baseline project missing")

        t0 = transforms(p0)
        rep.log(f"[INFO] P0 transforms={t0}")

        # Arrange all: focus the canvas, press A.
        driver.click(win.rect.x + 1000, win.rect.y + 300)
        time.sleep(0.5)
        driver.send_key("a")
        time.sleep(6.0)
        rep.check("整理后项目保存", save_project(driver, win, rep, p1)
                  and p1.exists())
        t1 = transforms(p1)
        plates1 = mac_3mf.read_plates(p1)
        rep.log(f"[INFO] P1 transforms={t1} "
                f"plates={ {k: len(v) for k, v in plates1.items()} }")

        moved = [name for name in t0
                 if name in t1
                 and math.hypot(t1[name][9] - t0[name][9],
                                t1[name][10] - t0[name][10]) >= MIN_MOVE]
        rep.check("对象重排（≥1 对象移动 ≥2mm）", bool(moved),
                  f"moved={moved}")

        rot_same = all(
            tuple(round(v, 3) for v in t1[name][:9])
            == tuple(round(v, 3) for v in t0[name][:9])
            for name in t0 if name in t1)
        rep.log(f"[INFO] rotation unchanged={rot_same} (evidence only)")

        aabbs = mac_3mf.object_world_aabbs(p1)
        rep.log(f"[INFO] P1 AABBs={aabbs}")
        names = list(aabbs)
        gaps = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                gaps.append((names[i], names[j],
                             gap(aabbs[names[i]], aabbs[names[j]])))
        rep.check("对象无重叠（AABB 间距 ≥2mm）",
                  bool(gaps) and all(g >= MIN_GAP - 1e-3
                                     for _a, _b, g in gaps),
                  f"gaps={[(a, b, round(g, 2)) for a, b, g in gaps]}")
        outside = [n for n, b in aabbs.items() if not inside(b)]
        rep.check("无越界（U1 可打印区）", not outside,
                  f"outside={outside}")

        rep.check("对象仍在 1 号盘",
                  sorted(plates1.get("1", [])) == sorted(t0.keys()),
                  f"plate1={plates1.get('1')} objects={sorted(t0)}")
        rep.check("空白盘被整理删除（1 个 plate 块）",
                  len(plates1) == 1, f"plates={sorted(plates1)}")

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
        exit_code = rep.save({"covered": ["#188"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
