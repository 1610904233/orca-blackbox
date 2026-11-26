#!/usr/bin/env python3
# m8g_flow_single.py — macOS port: Feishu #136 single-variable high-flow check.
# feishu: baseline#136  (macOS port; corresponds to the enabled Windows
#         m8g_flow_single, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   with the stock process and a stock-derived filament preset whose max
#   volumetric speed is 21 in BOTH flow tabs, the Standard and High Flow
#   slices must differ ONLY in the high-flow mode fields: numeric config
#   differences = 0 and mode changes >= 1, using tools/compare_gcode.py.
#
# macOS mapping:
#   two separate app sessions: each launches a 0.4 U1 project with the stock
#   0.24mm Standard process and a user preset derived from stock SnapSpeed
#   (filament_max_volumetric_speed = [21, 21]), deletes the fixture object,
#   adds a cube, sets the Nozzle Flow combo and exports a gcode.
#   High Flow raises 'Custom Filament Grouping'; the PLA chip is moved with
#   the middle transfer button (synthetic drag does not fire), then Confirm.
#   compare -> tools/compare_gcode.py; parse the Chinese report counts.
#
# Artifacts: artifacts/mac/pilot/m8g/{report.log,result.json,
#            session_a/*.gcode,session_b/*.gcode}.

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
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
)
import m7b_new_project as m7b  # noqa: E402
import m8f_nozzle_flow as c8f  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8g"
COMPARE = HERE / "tools" / "compare_gcode.py"


STOCK21 = "Snapmaker PLA SnapSpeed @U1 0.4 nozzle - FLOW-21"


def prepare_stock21(profile: Path, work: Path) -> Path:
    """Seed the profile with a stock-derived SnapSpeed preset whose max
    volumetric speed is 21 in BOTH flow tabs, and build the 0.4 project:
    stock 0.24mm Standard process + stock SnapSpeed-derived filament.
    """
    stock_path = HERE / "resources" / "Snapmaker" / "filament" / \
        "Snapmaker PLA SnapSpeed @U1 0.4 nozzle.json"
    if not stock_path.exists():
        stock_path = Path(
            "/Applications/Snapmaker Orca.app/Contents/Resources/profiles/"
            "Snapmaker/filament/Snapmaker PLA SnapSpeed @U1 0.4 nozzle.json")
    stock = json.loads(stock_path.read_text())
    stock["name"] = STOCK21
    stock["from"] = "User"
    stock["instantiation"] = "true"
    stock["filament_max_volumetric_speed"] = ["21", "21"]
    preset_dir = profile / "user" / "default" / "filament"
    preset_dir.mkdir(parents=True, exist_ok=True)
    (preset_dir / f"{STOCK21}.json").write_text(
        json.dumps(stock, indent=4))

    project = work / "stock21.3mf"
    fixture = HERE / "fixtures" / "mixed_filament_test.3mf"
    with zipfile.ZipFile(fixture) as zin, \
            zipfile.ZipFile(project, "w", zipfile.ZIP_DEFLATED) as zout:
        for entry in zin.infolist():
            data = zin.read(entry.filename)
            if entry.filename == "Metadata/project_settings.config":
                cfg = json.loads(data.decode())
                n = len(cfg["filament_settings_id"])
                cfg["printer_settings_id"] = "Snapmaker U1 (0.4 nozzle)"
                cfg["printer_variant"] = "0.4"
                cfg["nozzle_diameter"] = ["0.4"] * 4
                cfg["print_compatible_printers"] = [
                    "Snapmaker U1 (0.4 nozzle)"]
                cfg["print_settings_id"] = (
                    "0.24mm Standard @Snapmaker U1 (0.4 nozzle)")
                cfg["filament_settings_id"] = [STOCK21] * n
                cfg["filament_max_volumetric_speed"] = ["21"] * n
                cfg["enable_pressure_advance"] = ["0"] * n
                cfg["filament_ids"] = ["119531393501"] * n
                cfg["filament_type"] = ["PLA"] * n
                cfg["filament_vendor"] = ["Snapmaker"] * n
                data = json.dumps(cfg, indent=4).encode()
            zout.writestr(entry, data)
    return project


def run_session(driver, datadir: Path, work: Path, flow: str, gcode: Path,
                rep, tag: str):
    """One app session: stock 0.24mm + FLOW-21 preset -> flow -> export."""
    app = None
    win = None
    try:
        project = prepare_stock21(datadir, work)
        app, win = launch_and_focus(
            driver, datadir, model=project, timeout_s=150.0,
            log_path=work / f"app_launch_{tag}.log")
        rep.check(f"{tag} launch", True,
                  f"pid={app.pid} title={win.title!r}")
        time.sleep(4.0)
        item = driver.find_control(win, role="AXMenuItem",
                                   title="Delete All", timeout_s=3)
        if item is not None:
            driver.click_control(item)
            time.sleep(2.5)
        rep.check(f"{tag} add cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        rep.check(f"{tag} stock 0.24mm + FLOW-21 + {flow}",
                  c8f.set_flow(driver, win, rep, flow))
        if not slice_and_export(
                driver, win, rep, gcode,
                [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"],
                on_poll=lambda: c8f.confirm_grouping(driver, app, win, rep)):
            rep.check(f"{tag} 切片并导出", False, "slice/export failed")
            return None
        rep.check(f"{tag} 切片并导出", True,
                  f"size={gcode.stat().st_size}")
        fids, pid = c8f.gcode_ids(gcode)
        rep.log(f"[INFO] {tag} ids={fids} print={pid}")
        text = gcode.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^; filament_max_volumetric_speed = (.*)$",
                          text, re.M)
        maxv = match.group(1).strip() if match else ""
        rep.check(f"{tag} stock 预设生效",
                  pid == "0.24mm Standard @Snapmaker U1 (0.4 nozzle)"
                  and any("flow-21" in f.lower() for f in fids),
                  f"print={pid} filament={fids}")
        rep.check(f"{tag} max volumetric speed = 21",
                  bool(maxv) and all(v.strip() == "21"
                                     for v in maxv.split(",")),
                  f"max_vol={maxv}")
        return gcode
    finally:
        if app is not None:
            try:
                close_app(driver, app, win)
            except Exception:
                pass


def compare(a: Path, b: Path):
    r = subprocess.run([sys.executable, str(COMPARE), str(a), str(b)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def report_counts(report: str):
    def grab(pat):
        m = re.search(pat, report)
        return int(m.group(1)) if m else -1
    return (grab(r"高流量模式字段变化：(\d+) 项"),
            grab(r"数值配置变化：(\d+) 项"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    dir_a = OUT / "session_a"
    dir_b = OUT / "session_b"
    for path in (dir_a, dir_b):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True)
    g_a = dir_a / "m8g_standard.gcode"
    g_b = dir_b / "m8g_highflow.gcode"

    rep = Reporter(OUT)
    rep.log("=== m8g macOS single-variable flow check ===")
    driver = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        a = run_session(driver, dir_a / "profile", dir_a, "Standard", g_a,
                        rep, "A/Standard")
        b = run_session(driver, dir_b / "profile", dir_b, "High Flow", g_b,
                        rep, "B/High Flow")
        if a is None or b is None:
            return rep.save({"stage": "sessions"})
        rc, report = compare(g_a, g_b)
        mode, numeric = report_counts(report)
        rep.log(f"[INFO] compare rc={rc} mode={mode} numeric={numeric}")
        for line in report.splitlines()[:12]:
            rep.log(f"[INFO]   {line}")
        rep.check("#136 高流量模式字段有变化（mode >= 1）", mode >= 1,
                  f"mode={mode}")
        rep.check("#136 数值配置差异为 0", numeric == 0, f"numeric={numeric}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        pkill = subprocess.run(
            ["pkill", "-f", "Snapmaker_Orca --datadir"], capture_output=True)
        exit_code = rep.save({"covered": ["#136"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
