#!/usr/bin/env python3
# m3e_preset_switch.py — macOS port: Feishu #166 print-preset switch ->
# gcode header follows.
# feishu: baseline#166  (macOS port; corresponds to the enabled Windows
#         m3e_preset_switch, registered in cases.MACOS_BASELINE)
#
# The Windows case is also mapped to #159 (login -> local print / pause /
# logout device chain) and #182 (Prepare -> compare process presets).  This
# macOS local sandbox only performs the #166 preset switch; #159/#182 are
# separate scenarios and are not claimed here.
#
# Windows assertions:
#   slice+export with the default print preset (0.40 Standard for the U1 0.8
#   nozzle) -> switch the print preset to 0.24 Standard -> reslice+export ->
#   the gcode's '; layer_height' moved from 0.4 to 0.24.
#
# macOS mapping:
#   preset combo -> OCR the '~ 0.40mm Standard @Snapmaker U1 (0.8 nozzle)'
#                   word in the Process panel, click it, OCR the flat preset
#                   popup rows and click the one containing '0.24' (scroll the
#                   popup if the row is below the fold).  The exported gcode's
#                   print_settings_id confirms the switch.
#   slice        -> mac_common.slice_and_export
#   oracle       -> '; layer_height' in the CONFIG_BLOCK.
#
# Artifacts: artifacts/mac/pilot/m3e/{report.log,result.json,work/*.gcode,
#            *.png}.

from __future__ import annotations

import argparse
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

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
    wait_for_model,
)
import m8d_purifier_gcode as c8d  # noqa: E402
import m8f_nozzle_flow as c8f  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m3e"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def layer_height(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^; layer_height = ([0-9.]+)", text, re.M)
    return m.group(1) if m else None


def print_id(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^; print_settings_id = (.*)$", text, re.M)
    return m.group(1).strip().strip('"') if m else None


def switch_to_024(driver, win, rep) -> bool:
    ws = c8d.ocr_window(driver, win)
    combo = next((w for w in ws if "standard @" in w.text.lower()
                  and w.rect.x < 430), None)
    if combo is None:
        rep.log("[INFO] process combo not found")
        return False
    rep.log(f"[INFO] process combo={combo.text!r} @ {combo.rect.to_xywh()}")
    driver.click(win.rect.x + combo.rect.center[0],
                 win.rect.y + combo.rect.center[1])
    time.sleep(1.2)
    pops = [w for w in driver.windows_for_pid(win.pid)
            if w.id != win.id and w.on_screen and w.layer != 0
            and w.rect.area > 3000]
    pop = max(pops, key=lambda w: w.rect.area) if pops else None
    for attempt in range(8):
        ws = c8d.ocr_window(driver, win)
        rows = [w for w in ws if w.rect.x < 430 and w.rect.y > 580
                and "standard @" in w.text.lower()]
        rep.log(f"[INFO] rows[{attempt}]="
                f"{[(w.text, w.rect.to_xywh()) for w in rows][:12]}")
        target = next((w for w in rows if "0.24" in w.text.lower()), None)
        if target is not None:
            rep.log(f"[INFO] click 0.24 row {target.text!r}")
            driver.click(win.rect.x + target.rect.center[0],
                         win.rect.y + target.rect.center[1])
            time.sleep(2.0)
            return True
        if pop is None:
            break
        driver.wheel(pop.rect.right - 8, pop.rect.y + 120, -10)
        time.sleep(0.5)
    driver.send_key("escape")
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
    model = work / "m3e_mixed.3mf"
    shutil.copy2(DEFAULT_MODEL, model)
    g_a = work / "m3e_040.gcode"
    g_b = work / "m3e_024.gcode"

    rep = Reporter(OUT)
    rep.log("=== m3e macOS print-preset switch ===")
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

        roots = [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"]
        if not slice_and_export(driver, win, rep, g_a, roots):
            rep.check("A 切片导出（0.40 预设）", False, "slice/export failed")
            return rep.save({"stage": "slice-a"})
        lh_a = layer_height(g_a)
        pid_a = print_id(g_a)
        rep.log(f"[INFO] A layer_height={lh_a} print={pid_a}")
        rep.check("基线预设为 0.40", lh_a == "0.4" and pid_a is not None
                  and "0.40" in pid_a, f"{lh_a} {pid_a}")

        rep.check("回到 Prepare 页", c8f.prepare_tab(driver, win))
        rep.check("切换到 0.24 预设", switch_to_024(driver, win, rep))
        time.sleep(1.5)
        if not slice_and_export(driver, win, rep, g_b, roots):
            rep.check("B 切片导出（0.24 预设）", False, "slice/export failed")
            return rep.save({"stage": "slice-b"})
        lh_b = layer_height(g_b)
        pid_b = print_id(g_b)
        rep.log(f"[INFO] B layer_height={lh_b} print={pid_b}")
        rep.check("预设切换生效（print_settings_id 0.24）",
                  pid_b is not None and "0.24" in pid_b, f"print={pid_b}")
        rep.check("gcode 头跟随预设（0.4 -> 0.24）", lh_b == "0.24",
                  f"{lh_a} -> {lh_b}")

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
        exit_code = rep.save({"covered": ["#166"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
