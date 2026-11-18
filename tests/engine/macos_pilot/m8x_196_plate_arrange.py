#!/usr/bin/env python3
# m8x_196_plate_arrange.py — macOS port: Feishu #196 arrange parts on the
# current plate with the plate-side toolbar button.
# feishu: baseline#196  (macOS port; corresponds to the enabled Windows
#         m8x_196, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   1) two overlapping cubes are added to the current plate
#   2) the plate-side "Arrange objects on current plate" button is found by
#      tooltip and clicked
#   3) both parts still exist afterwards and are separated (centroid distance
#      > 120 screen px in the Windows oracle)
#
# macOS mapping:
#   rail      -> (952,271) at 1200x800 with two plates, tooltip
#                "Arrange objects on current plate" (right-side tooltip).
#   geometry  -> Save Project as S0/S1 and parse with mac_3mf: build-item
#                translations of the two Cube objects.  20mm cubes must be at
#                least 20mm apart after arrange (m8x_197 measured 29mm), and
#                identical before (they are added at the plate centre).
#   save      -> recover_saved_file() in case the shared save panel opens in
#                the previous case's work folder.
#
# Artifacts: artifacts/mac/pilot/m8x_196/{report.log,result.json,work/*.3mf,
#            *.png}.

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

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, recover_saved_file,
    wait_for_model,
)
import mac_3mf  # noqa: E402
import m7b_new_project as m7b  # noqa: E402
import m8x_186_add_plate as c186  # noqa: E402
import m8x_194_remove_plate as c194  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_196"
DEFAULT_MODEL = HERE / "fixtures" / "Prusa.stl"
ADD_PLATE_XY = (520, 75)
ARRANGE_SEED = (952, 271)
COLORED_GATE = 0.012
MIN_SEPARATION_MM = 20.0     # cube edge; measured 29mm after arrange


def save_project(driver, win, rep, path: Path) -> bool:
    started = time.time()
    if c186.save_project(driver, win, rep, path):
        return True
    recovered = recover_saved_file(path, started, [ARTIFACTS / "pilot"])
    rep.log(f"[INFO] save recovery {path.name}: {recovered}")
    return recovered is not None


def cube_positions(path: Path) -> dict[str, tuple]:
    geo = mac_3mf.read_project(path)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    out = {}
    for oid, transform in geo.items:
        name = names.get(oid, oid)
        if "cube" not in name.lower():
            continue
        out[f"{name}#{oid}"] = (round(transform[9], 3), round(transform[10], 3))
    return out


def max_separation(points: list[tuple]) -> float:
    best = 0.0
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            best = max(best, math.hypot(points[i][0] - points[j][0],
                                        points[i][1] - points[j][1]))
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    model = work / "m8x_196_prusa.stl"
    shutil.copy2(args.model, model)
    s0 = work / "m8x_196_s0.3mf"
    s1 = work / "m8x_196_s1.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_196 macOS plate-side arrange ===")
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
                  f"rect={win.rect.to_xywh()}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=COLORED_GATE)
        frame.save_png(OUT / "loaded.png")
        rep.check("载入模型", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        tip = c194.tooltip_below(driver, win, *ADD_PLATE_XY)
        rep.check("「添加新盘」按钮", "add plate" in tip.lower(), f"tip={tip!r}")
        driver.click(win.rect.x + ADD_PLATE_XY[0],
                     win.rect.y + ADD_PLATE_XY[1])
        time.sleep(3.0)
        rep.log("[INFO] add plate clicked")

        added = [m7b._add_cube(driver, app, win) for _ in range(2)]
        rep.check("两个零件已添加", all(added), f"results={added}")
        if not all(added):
            return rep.save({"stage": "add-cubes"})
        time.sleep(2.0)

        if not save_project(driver, win, rep, s0):
            rep.check("另存 S0（排列前）", False, "save panel failed")
            return rep.save({"stage": "save-s0"})
        pos0 = cube_positions(s0)
        plates0 = mac_3mf.read_plates(s0)
        rep.log(f"[INFO] S0 plates={ {k: v for k, v in plates0.items()} }")
        rep.log(f"[INFO] S0 cube positions={pos0}")
        rep.check("双盘布局（P0 有 2 盘）", len(plates0) == 2,
                  f"plates={sorted(plates0)}")
        rep.check("排列前两立方体重叠（同一位姿）",
                  len(pos0) == 2 and len(set(pos0.values())) == 1,
                  f"cubes={pos0}")
        if len(pos0) != 2:
            return rep.save({"stage": "baseline"})

        # Plate-side arrange, tooltip-verified.
        arr = c194.find_rail_icon(driver, win, "arrange", seed=ARRANGE_SEED)
        rep.check("「排列零件」按钮（tooltip 验证）", arr is not None,
                  f"@{arr}" if arr else "no 'arrange' tooltip near rail")
        if arr is None:
            return rep.save({"stage": "arrange-icon"})
        driver.click(win.rect.x + arr[0], win.rect.y + arr[1])
        time.sleep(6.0)
        driver.capture(win).save_png(OUT / "after_arrange.png")

        if not save_project(driver, win, rep, s1):
            rep.check("另存 S1（排列后）", False, "save panel failed")
            return rep.save({"stage": "save-s1"})
        pos1 = cube_positions(s1)
        rep.log(f"[INFO] S1 cube positions={pos1}")
        rep.check("两个零件仍然存在", len(pos1) >= 2, f"cubes={pos1}")
        sep = max_separation(list(pos1.values())) if pos1 else 0.0
        rep.log(f"[INFO] centroid separation={sep:.1f}mm")
        rep.check("零件排布后互不重叠（中心距 >= 20mm）",
                  len(pos1) >= 2 and sep >= MIN_SEPARATION_MM,
                  f"separation={sep:.1f}mm")
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
        exit_code = rep.save({"covered": ["#196"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
