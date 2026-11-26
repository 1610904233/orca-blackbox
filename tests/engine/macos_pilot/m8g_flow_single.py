#!/usr/bin/env python3
# m8g_flow_single.py — macOS port: Feishu #136 single-variable high-flow check.
# feishu: baseline#136  (macOS port; corresponds to the enabled Windows
#         m8g_flow_single, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   with the doc's default 流量测试 user presets (max volumetric speed 40 in
#   BOTH flow tabs, pressure advance 1) and its gcode参数测试.3mf cube, the
#   Standard and High Flow slices must differ ONLY in the high-flow mode
#   fields: numeric config differences = 0 and mode changes >= 1, using
#   tools/compare_gcode.py.
#
# macOS mapping:
#   two separate app sessions: each copies default.zip's user presets
#   BYTE-FOR-BYTE (no preset JSON is edited), starts an EMPTY project, adds
#   the built-in Cube, selects the 流量测试 process/filament through the UI,
#   sets the Nozzle Flow combo and exports a gcode.
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


FLOW_CN = "Snapmaker PLA SnapSpeed @U1 - 流量测试"
PROC_CN = "0.24mm Standard @Snapmaker U1 (0.4 nozzle) - 流量测试"


def _profile_src(kind: str, name: str) -> Path:
    path = HERE / "resources" / "Snapmaker" / kind / f"{name}.json"
    if path.exists():
        return path
    return Path("/Applications/Snapmaker Orca.app/Contents/Resources/"
                f"profiles/Snapmaker/{kind}/{name}.json")


def prepare_flow_cn(profile: Path) -> None:
    """Copy default.zip's user presets unchanged; no project/model is
    loaded.  The test starts from an empty project + the built-in Cube and
    selects the 流量测试 process/filament through the UI."""
    src = HERE / "tests/engine/macos_pilot/fixtures/gcode_plan/default"
    dst = profile / "user" / "default"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def run_session(driver, datadir: Path, work: Path, flow: str, gcode: Path,
                rep, tag: str):
    """One app session: empty -> Cube -> 流量测试 presets -> flow -> export."""
    app = None
    win = None
    try:
        prepare_flow_cn(datadir)
        app, win = launch_and_focus(
            driver, datadir, model=None, timeout_s=150.0,
            log_path=work / f"app_launch_{tag}.log")
        rep.check(f"{tag} launch", True,
                  f"pid={app.pid} title={win.title!r}")
        time.sleep(4.0)
        rep.check(f"{tag} add cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        rep.check(f"{tag} 流量测试预设 + {flow}",
                  c8f.select_state(driver, win, rep, "FLOW", "FLOW",
                                   flow, tag))
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
        rep.check(f"{tag} 流量测试预设生效",
                  pid == PROC_CN
                  and any("流量测试" in f for f in fids),
                  f"print={pid} filament={fids}")
        rep.check(f"{tag} max volumetric speed = 40（通用两页签）",
                  bool(maxv) and all(v.strip() == "40"
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
