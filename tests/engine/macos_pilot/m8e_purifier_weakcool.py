#!/usr/bin/env python3
# m8e_purifier_weakcool.py — macOS port: Feishu #114/#129 purifier weak-cool
# gcode branch.
# feishu: baseline#114 baseline#129  (macOS port; corresponds to the enabled
#         Windows m8e_purifier_weakcool, registered in cases.MACOS_BASELINE)
#
# Windows case text (repo): weak cooling -> SET_PURIFIER_MODE MODE=3
# DESIRE_TEMP=0 FAN_SPEED=0.6 DELAY_OFF=600, no ALARM_TEMP.
#
# Current product behaviour (verified 2026-11-18): the app's 20260128 machine
# template has three branches:
#   chamber_cooling_mode==0 -> keep-warm MODE=3 DESIRE_TEMP=45 DELAY_OFF=600
#   chamber_cooling_mode==2 -> strong    MODE=1 DESIRE_TEMP=42 ALARM_TEMP=48
#   {else} (weak)           ->          MODE=1 DESIRE_TEMP=45 ALARM_TEMP=51
#                                        FAN_SPEED=0.6 DELAY_OFF=0
# A Generic PETG (vitrification 70) cube slices to the {else} branch.  The
# user provided a local Orca case-114 gcode with exactly
#   SET_PURIFIER_MODE MODE=1 DESIRE_TEMP=45 ALARM_TEMP=51 FAN_SPEED=0.6
#                      DELAY_OFF=0
# and confirmed it matches the Windows side, so this port asserts the current
# observed values (the repo's Windows case text predates this template and
# needs a Windows-side owner update; no Windows file is modified here).
#
# macOS path:
#   fixture -> fixtures/mixed_filament_test.3mf copied into work
#   scene   -> Edit > Delete All, bed right-click Add Primitive > Cube (slot 1
#              stays Generic PETG)
#   slice   -> mac_common.slice_and_export
#   oracle  -> mac_gcode.purifier_params / used_filaments
#
# Artifacts: artifacts/mac/pilot/m8e/{report.log,result.json,work/*.gcode,
#            *.png}; work/user_case114_weak.gcode is the user's reference.

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
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
    wait_for_model,
)
import mac_gcode  # noqa: E402
import m7b_new_project as m7b  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8e"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
EMPTY_BED_MAX = 0.015
VIEWPORT = (430, 100, 1080, 700)


def vp_colored(frame) -> float:
    import numpy as np
    arr = np.frombuffer(frame.data, dtype=np.uint8).reshape(
        frame.height, frame.width, 4)
    b = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    r = arr[:, :, 2].astype(int)
    spread = np.maximum(np.maximum(b, g), r) - np.minimum(np.minimum(b, g), r)
    x0, y0, x1, y1 = VIEWPORT
    return float((spread[y0:y1, x0:x1] > 24).mean())


def info_panel_has(driver, win, needle: str,
                   timeout_s: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frame = driver.capture(win)
        region = Rect(frame.width * 0.58, frame.height * 0.68,
                      frame.width * 0.42, frame.height * 0.32)
        words = recognize_text(frame, region)
        if needle.lower() in " ".join(w.text for w in words).lower():
            return True
        time.sleep(1.5)
    return False


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
    model = work / "m8e_mixed.3mf"
    shutil.copy2(DEFAULT_MODEL, model)
    gcode = work / "m8e_weak.gcode"

    rep = Reporter(OUT)
    rep.log("=== m8e macOS purifier weak-cooling (current template) ===")
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
            driver, app, win, timeout_s=120.0, threshold=0.03)
        frame.save_png(OUT / "loaded.png")
        rep.check("模型载入（mixed 夹具）", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        item = driver.find_control(win, role="AXMenuItem",
                                   title="Delete All", timeout_s=3)
        rep.check("Delete All 可用", item is not None)
        if item is None:
            return rep.save({"stage": "delete"})
        driver.click_control(item)
        time.sleep(2.5)
        emptied = driver.capture(win)
        emptied.save_png(OUT / "cleared.png")
        rep.check("清场（视口空盘）", vp_colored(emptied) < EMPTY_BED_MAX,
                  f"viewport={vp_colored(emptied):.4f}")

        rep.check("添加 cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        rep.check("cube 已选中（信息面板）",
                  info_panel_has(driver, win, "cube"))

        if not slice_and_export(driver, win, rep, gcode,
                                [work, OUT, ARTIFACTS / "pilot",
                                 HERE / "fixtures"]):
            rep.check("切片并导出 G-code", False, "slice/export failed")
            return rep.save({"stage": "slice"})
        rep.check("切片并导出 G-code", True,
                  f"size={gcode.stat().st_size}")
        data = gcode.read_bytes()
        used = mac_gcode.used_filaments(data)
        pa = mac_gcode.purifier_params(data)
        rep.log(f"[INFO] used={used} purifier={pa}")
        rep.check("cube 在 1 号槽（PETG，gcode 用量）", used == [1],
                  f"used={used}")
        # Current template's {else} (weak) branch; user-confirmed same line on
        # the Windows side for case 114.
        rep.check("弱冷分支 MODE=1", bool(pa) and pa.get("MODE") == "1",
                  f"params={pa}")
        rep.check("DESIRE_TEMP=45", bool(pa)
                  and pa.get("DESIRE_TEMP") == "45", f"params={pa}")
        rep.check("ALARM_TEMP=51", bool(pa)
                  and pa.get("ALARM_TEMP") == "51", f"params={pa}")
        rep.check("FAN_SPEED=0.6", bool(pa)
                  and pa.get("FAN_SPEED") == "0.6", f"params={pa}")
        rep.check("DELAY_OFF=0", bool(pa)
                  and pa.get("DELAY_OFF") == "0", f"params={pa}")

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
        exit_code = rep.save({"covered": ["#114", "#129"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
