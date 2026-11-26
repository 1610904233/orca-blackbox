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
#   filament scenario (A/B): two app sessions; each copies default.zip's
#   user presets byte-for-byte, starts an EMPTY project, adds the built-in
#   Cube, selects the 流量测试 process/filament through the UI, sets the
#   Nozzle Flow combo and exports a gcode.
#   process scenario (C, one session): the doc 流量测试 process copy starts
#   with Standard flow First layer speed=61 and High flow=60 (the High entry
#   keeps the doc value).  The video opens Process -> Speed and shows 61/60,
#   slices Standard, then restores Standard to 60 and sets only High flow to
#   61 before the High Flow slice.  The gcode arrays are 61,60 (Standard) and
#   60,61 (High Flow); each slice's ACTIVE flow value is 61, the inactive
#   flow keeps 60.  The same filament (流量测试, max volumetric speed 40) is
#   unchanged.
#   C-vs-D must have the same effective per-flow config (index-resolved),
#   differ in the high-flow mode fields, and only the initial_layer_speed
#   positions swap.  A-vs-C and B-vs-D each differ in exactly one numeric
#   config key and no mode field, proving each flow's own entry changed.
#   High Flow raises 'Custom Filament Grouping'; the PLA chip is moved with
#   the middle transfer button (synthetic drag does not fire), then Confirm.
#   compare -> tools/compare_gcode.py; parse the Chinese report counts.
#
# Artifacts: artifacts/mac/pilot/m8g/{report.log,result.json,
#            session_a/*.gcode,session_b/*.gcode,
#            session_c/*.gcode,session_d/*.gcode}.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
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
)
import m7b_new_project as m7b  # noqa: E402
import m8f_nozzle_flow as c8f  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8g"
COMPARE = HERE / "tools" / "compare_gcode.py"


PROC_CN = "0.24mm Standard @Snapmaker U1 (0.4 nozzle) - 流量测试"

# The process preset is verified through Process -> Speed.  That tab is
# only shown in advanced user mode (the user's setting); at the default 420px
# sidebar the six tabs are compressed, so the process session starts from the
# same minimal conf with a 520px sidebar.  Only the AUI layout string is
# copied -- no user project/preset state, so no Restore prompt.
WIDE_LAYOUT = (
    "layout2|name=sidebar;caption=;state=1996;dir=4;layer=0;row=0;pos=0;"
    "prop=100000;bestw=520;besth=900;minw=-1;minh=-1;maxw=-1;maxh=-1;"
    "floatx=-1;floaty=-1;floatw=-1;floath=-1|name=main;caption=;state=256;"
    "dir=5;layer=0;row=0;pos=0;prop=100000;bestw=20;besth=20;minw=-1;"
    "minh=-1;maxw=-1;maxh=-1;floatx=-1;floaty=-1;floatw=-1;floath=-1|"
    "dock_size(5,0,0)=20|dock_size(4,0,0)=522|")


def patch_process_first_layer(profile: Path,
                              values: tuple[str, str] = ("61", "60")) -> Path:
    """Set the doc 流量测试 process copy's per-flow initial_layer_speed.

    The user's single-variable process test does NOT set both flows to 61 at
    once: for the Standard slice only the Standard-flow entry is 61 while the
    High-flow entry keeps the doc value 60; after that slice the Standard
    entry is restored to 60 and only the High-flow entry is set to 61.  This
    preset copy starts in the first state (61,60); the running app's Speed
    tabs are used to switch to (60,61) before the High Flow slice.
    """
    proc_dir = profile / "user" / "default" / "process"
    matches = [p for p in proc_dir.glob("*.json")
               if "流量测试" in p.name and "0.24mm" in p.name]
    if not matches:
        raise FileNotFoundError(f"流量测试 process preset not found in {proc_dir}")
    path = matches[0]
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    data["initial_layer_speed"] = [str(v) for v in values]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4),
                    encoding="utf-8")
    return path


def prepare_advanced_profile(profile: Path) -> None:
    """Fresh sandbox profile for the process scenario.

    - advanced user mode + 520px sidebar: Process -> Speed (the per-flow
      First layer speed tabs) is visible; only the AUI layout string is
      copied, no user project/preset state -> no Restore prompt.
    - the doc 流量测试 process copy starts with Standard flow 61 / High flow
      60; the High Flow slice later restores Standard to 60 and sets High to
      61 through the Speed tab.  The filament presets and every other process
      parameter stay byte-for-byte as the doc default.
    """
    prepare_flow_cn(profile)
    patch_process_first_layer(profile, ("61", "60"))
    conf = profile / "Snapmaker_Orca.conf"
    if conf.exists():
        data = json.loads(conf.read_text(encoding="utf-8")
                          .split("\n# MD5")[0])
    else:
        data = {
            "app": {
                "language": "en_US",
                "show_splash_screen": False,
                "single_instance": False,
                "default_page": "1",
                "privacy_policy_isagree": True,
                "backup_switch": False,
                "window_mainframe": os.environ.get(
                    "ORCA_BB_WINDOW_FRAME", "360; 80; 1200; 800; 0"),
            },
            "firstguide": {"finish": True},
            "models": [{
                "model": "Snapmaker U1",
                "nozzle_diameter": "0.2;0.4;0.6;0.8",
                "vendor": "Snapmaker",
            }],
            "presets": {
                "filaments": None,
                "machine": "Snapmaker U1 (0.4 nozzle)",
            },
        }
    app = data.setdefault("app", {})
    app["user_mode"] = "advanced"
    app["window_layout"] = WIDE_LAYOUT
    app["window_mainframe"] = os.environ.get(
        "ORCA_BB_WINDOW_FRAME", app.get("window_mainframe",
                                       "360; 80; 1200; 800; 0"))
    body = json.dumps(data, indent=4, ensure_ascii=False)
    digest = hashlib.md5((body + "\n").encode("utf-8")).hexdigest().upper()
    conf.write_text(body + "\n# MD5 checksum " + digest + "\n",
                    encoding="utf-8")


def _ocr_win(driver, win):
    from harness.platform.macos_ocr import recognize_text
    return recognize_text(driver.capture(win))


def _click_word(driver, win, word, pause=1.2):
    driver.click(win.rect.x + word.rect.center[0],
                 win.rect.y + word.rect.center[1])
    time.sleep(pause)


def _speed_value_words(words):
    return [w for w in words
            if w.rect.x > 150 and 615 <= w.rect.y <= 650
            and re.fullmatch(r"\d{2,3}(?:\.\d+)?", w.text.strip())]


def _flow_tab_points(words):
    """Return (standard_point, high_flow_point) in window coordinates."""
    for w in words:
        text = w.text.lower()
        if "standard flow" in text and "high flow" in text:
            x, y = w.rect.x, w.rect.y
            wid, hei = w.rect.w, w.rect.h
            return ((x + wid * 0.25, y + hei / 2),
                    (x + wid * 0.75, y + hei / 2))
    std = next((w for w in words
                if w.text.strip().lower() == "standard flow"), None)
    hf = next((w for w in words
               if w.text.strip().lower() == "high flow"), None)
    if std and hf:
        return std.rect.center, hf.rect.center
    return None


def verify_speed_tabs(driver, win, rep, tag: str,
                      std_value: int, hf_value: int) -> bool:
    """Process -> Speed evidence for the current per-flow preset state:
    Standard flow shows std_value and High flow shows hf_value."""
    words = _ocr_win(driver, win)
    tab = next((w for w in words if w.text.strip().lower() == "speed"
                and 480 <= w.rect.y <= 570), None)
    if tab is None:
        rep.log(f"[INFO] {tag} Speed tab not found")
        return False
    _click_word(driver, win, tab)
    words = _ocr_win(driver, win)
    points = _flow_tab_points(words)
    rep.log(f"[INFO] {tag} flow tabs={points} "
            f"values={[(w.text, w.rect.to_xywh()) for w in _speed_value_words(words)]}")
    if points is None:
        rep.log(f"[INFO] {tag} flow sub-tabs not found: "
                f"{[(w.text, w.rect.to_xywh()) for w in words if 550 < w.rect.y < 600]}")
        return False
    std_pt, hf_pt = points
    ok = True
    for label, pt, expected in (("Standard flow", std_pt, std_value),
                                ("High flow", hf_pt, hf_value)):
        driver.click(win.rect.x + pt[0], win.rect.y + pt[1])
        time.sleep(0.9)
        words = _ocr_win(driver, win)
        vals = _speed_value_words(words)
        good = any(w.text.strip() == str(expected) for w in vals)
        rep.log(f"[INFO] {tag} {label} First layer speed="
                f"{[(w.text, w.rect.to_xywh()) for w in vals]} "
                f"expect={expected} ok={good}")
        ok = ok and good
    driver.click(win.rect.x + std_pt[0], win.rect.y + std_pt[1])
    time.sleep(0.8)
    return ok


def _set_flow_value(driver, win, rep, tag: str, label: str,
                    tab_pt, verify_pt, value: int) -> bool:
    """Edit one flow tab's First layer speed, then verify by switching to
    the other flow tab and back.  The doc preset's per-flow entry is edited
    in the UI; this is the user's restore/High-61 step."""
    for attempt in range(2):
        driver.click(win.rect.x + tab_pt[0], win.rect.y + tab_pt[1])
        time.sleep(0.9)
        words = _ocr_win(driver, win)
        vals = _speed_value_words(words)
        if not vals:
            rep.log(f"[INFO] {tag} {label} value field not found")
            return False
        rect = vals[0].rect
        # focus with a center click, then click past the digits so the caret
        # lands after the last character (the right edge alone can miss the
        # text control after several app sessions).
        driver.click(win.rect.x + rect.center[0],
                     win.rect.y + rect.center[1])
        time.sleep(0.35)
        driver.click(win.rect.x + rect.x + rect.w + 10,
                     win.rect.y + rect.center[1])
        time.sleep(0.35)
        for _ in range(6):
            driver.send_key("backspace")
            time.sleep(0.12)
        for ch in str(value):
            driver.send_key(ch)
            time.sleep(0.18)
        driver.send_key("return")
        time.sleep(0.8)
        driver.click(win.rect.x + verify_pt[0], win.rect.y + verify_pt[1])
        time.sleep(0.8)
        driver.click(win.rect.x + tab_pt[0], win.rect.y + tab_pt[1])
        time.sleep(0.8)
        words = _ocr_win(driver, win)
        vals = _speed_value_words(words)
        good = any(w.text.strip() == str(value) for w in vals)
        rep.log(f"[INFO] {tag} set {label}={value}: "
                f"{[(w.text, w.rect.to_xywh()) for w in vals]} ok={good}")
        if good:
            return True
    return False


def set_two_flow_values(driver, win, rep, tag: str,
                        std_value: int, hf_value: int) -> bool:
    """User's method: after the Standard slice, restore Standard to its
    original value and only then set High flow to 61, before the High slice."""
    words = _ocr_win(driver, win)
    tab = next((w for w in words if w.text.strip().lower() == "speed"
                and 480 <= w.rect.y <= 570), None)
    if tab is None:
        rep.log(f"[INFO] {tag} Speed tab not found")
        return False
    _click_word(driver, win, tab)
    words = _ocr_win(driver, win)
    points = _flow_tab_points(words)
    if points is None:
        rep.log(f"[INFO] {tag} flow sub-tabs not found")
        return False
    std_pt, hf_pt = points
    ok_std = _set_flow_value(driver, win, rep, tag, "Standard flow",
                             std_pt, hf_pt, std_value)
    ok_hf = _set_flow_value(driver, win, rep, tag, "High flow",
                            hf_pt, std_pt, hf_value)
    driver.click(win.rect.x + std_pt[0], win.rect.y + std_pt[1])
    time.sleep(0.8)
    return ok_std and ok_hf


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


def _check_export(rep, tag: str, gcode: Path, process_edit: bool,
                  expected_speed: tuple[str, str] | None = None) -> bool:
    fids, pid = c8f.gcode_ids(gcode)
    rep.log(f"[INFO] {tag} ids={fids} print={pid}")
    text = gcode.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^; filament_max_volumetric_speed = (.*)$",
                      text, re.M)
    maxv = match.group(1).strip() if match else ""
    speed = re.search(r"^; initial_layer_speed = (.*)$", text, re.M)
    speed_v = speed.group(1).strip() if speed else ""
    speed_vals = [v.strip() for v in speed_v.split(",") if v.strip()]
    rep.log(f"[INFO] {tag} initial_layer_speed={speed_v}")
    rep.check(f"{tag} 流量测试预设生效",
              pid is not None
              and ((pid == PROC_CN) if not process_edit
                   else (PROC_CN in pid))
              and any("流量测试" in f for f in fids),
              f"print={pid} filament={fids}")
    if process_edit and expected_speed is not None:
        exp = [str(v) for v in expected_speed]
        rep.check(f"{tag} 工艺参数 First layer speed = {','.join(exp)}",
                  speed_vals == exp,
                  f"initial_layer_speed={speed_v}")
    rep.check(f"{tag} max volumetric speed = 40（通用两页签）",
              bool(maxv) and all(v.strip() == "40"
                                 for v in maxv.split(",")),
              f"max_vol={maxv}")
    return True


def run_session(driver, datadir: Path, work: Path, flow: str, gcode: Path,
                rep, tag: str, process_edit: bool = False,
                second_flow: str | None = None,
                second_gcode: Path | None = None):
    """One app session: empty -> Cube -> 流量测试 presets -> flow -> export.

    process_edit=True is the second #136 scenario.  The doc 流量测试 process
    copy starts at (Standard 61, High 60); the Standard slice uses that
    state.  Before the High Flow slice the user's method is applied: restore
    Standard to 60, set High to 61 in Process -> Speed, then switch the
    printer to High Flow.  The gcode arrays are therefore 61,60 and 60,61 --
    only the active flow's First layer speed is 61 in each slice."""
    app = None
    win = None
    try:
        if process_edit:
            prepare_advanced_profile(datadir)
        else:
            prepare_flow_cn(datadir)
        app, win = launch_and_focus(
            driver, datadir, model=None, timeout_s=150.0,
            log_path=work / f"app_launch_{tag}.log")
        rep.check(f"{tag} launch", True,
                  f"pid={app.pid} title={win.title!r}")
        time.sleep(4.0)
        rep.check(f"{tag} add cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        selected = c8f.select_state(driver, win, rep, "FLOW", "FLOW",
                                    flow, tag)
        rep.check(f"{tag} 流量测试预设 + {flow}", selected)
        if process_edit:
            rep.check(f"{tag} 工艺 Standard=61 / High=60（高流保持原值）",
                      selected and verify_speed_tabs(
                          driver, win, rep, tag, 61, 60))
        if not slice_and_export(
                driver, win, rep, gcode,
                [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"],
                on_poll=lambda: c8f.confirm_grouping(driver, app, win, rep)):
            rep.check(f"{tag} 切片并导出", False, "slice/export failed")
            return None
        rep.check(f"{tag} 切片并导出", True,
                  f"size={gcode.stat().st_size}")
        _check_export(rep, tag, gcode, process_edit,
                      ("61", "60") if process_edit else None)

        if second_flow and second_gcode is not None:
            tag2 = f"{tag}/{second_flow}"
            rep.check(f"{tag2} 回到 Prepare 页",
                      c8f.prepare_tab(driver, win))
            if process_edit:
                rep.check(f"{tag2} 还原 Standard=60 后改 High=61",
                          set_two_flow_values(driver, win, rep, tag2, 60, 61))
                rep.check(f"{tag2} 工艺 Standard=60 / High=61",
                          verify_speed_tabs(driver, win, rep, tag2, 60, 61))
            rep.check(f"{tag2} 切到 {second_flow} 流",
                      c8f.set_flow(driver, win, rep, second_flow))
            if not slice_and_export(
                    driver, win, rep, second_gcode,
                    [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"],
                    on_poll=lambda: c8f.confirm_grouping(
                        driver, app, win, rep)):
                rep.check(f"{tag2} 切片并导出", False,
                          "second slice/export failed")
                return gcode
            rep.check(f"{tag2} 切片并导出", True,
                      f"size={second_gcode.stat().st_size}")
            _check_export(rep, tag2, second_gcode, process_edit,
                          ("60", "61") if process_edit else None)
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
    ap.add_argument("--only", choices=("all", "filament", "process"),
                    default="all",
                    help="dev helper: run one #136 scenario")
    args = ap.parse_args()

    dir_a = OUT / "session_a"
    dir_b = OUT / "session_b"
    dir_c = OUT / "session_c"
    dir_d = OUT / "session_d"
    run_fil = args.only in ("all", "filament")
    run_proc = args.only in ("all", "process")
    for path, active in ((dir_a, run_fil), (dir_b, run_fil),
                         (dir_c, run_proc), (dir_d, run_proc)):
        if active:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
            path.mkdir(parents=True)
    g_a = dir_a / "m8g_standard.gcode"
    g_b = dir_b / "m8g_highflow.gcode"
    g_c = dir_c / "m8g_proc_standard.gcode"
    g_d = dir_d / "m8g_proc_highflow.gcode"

    rep = Reporter(OUT)
    rep.log("=== m8g macOS single-variable flow check ===")
    driver = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        # Process scenario first: its Speed-tab edits are reliable in the
        # first app session; the filament sessions do not use keyboard input.
        if run_proc:
            c = run_session(driver, dir_c / "profile", dir_c, "Standard", g_c,
                            rep, "C/Standard-Proc", process_edit=True,
                            second_flow="High Flow", second_gcode=g_d)
            d = g_d if g_d.exists() else None
            if c is None or d is None:
                return rep.save({"stage": "process-sessions"})
            rc, report = compare(g_c, g_d)
            mode, numeric = report_counts(report)
            bad, checked, ia, ib = c8f.effective_diff(g_c, g_d)
            rep.log(f"[INFO] process compare rc={rc} mode={mode} "
                    f"numeric={numeric} effective_bad={len(bad)} "
                    f"checked={checked} idx={ia}/{ib}")
            for line in report.splitlines()[:12]:
                rep.log(f"[INFO]   {line}")
            rep.check("#136 工艺场景 高流量模式字段有变化（mode >= 1）",
                      mode >= 1, f"mode={mode}")
            rep.check("#136 工艺场景 两流道生效值一致（effective == 0）",
                      not bad and checked > 0,
                      f"bad={bad[:3]} checked={checked} idx={ia}/{ib}")
            rep.check("#136 工艺场景 原始配置只差 initial_layer_speed"
                      "（numeric == 1）", numeric == 1,
                      f"numeric={numeric}")
        if run_fil:
            a = run_session(driver, dir_a / "profile", dir_a, "Standard", g_a,
                            rep, "A/Standard")
            b = run_session(driver, dir_b / "profile", dir_b, "High Flow", g_b,
                            rep, "B/High Flow")
            if a is None or b is None:
                return rep.save({"stage": "sessions"})
            rc, report = compare(g_a, g_b)
            mode, numeric = report_counts(report)
            rep.log(f"[INFO] filament compare rc={rc} mode={mode} "
                    f"numeric={numeric}")
            for line in report.splitlines()[:12]:
                rep.log(f"[INFO]   {line}")
            rep.check("#136 耗材场景 高流量模式字段有变化（mode >= 1）",
                      mode >= 1, f"mode={mode}")
            rep.check("#136 耗材场景 数值配置差异为 0", numeric == 0,
                      f"numeric={numeric}")
        if run_proc and run_fil:
            # Standard slice: A(60,60) -> C(61,60) changes only the Standard
            # entry; High slice: B(60,60) -> D(60,61) changes only the High
            # entry.  The comparator must see exactly one numeric key each.
            for label, base, proc in (("Standard", g_a, g_c),
                                      ("High", g_b, g_d)):
                rc2, rep2 = compare(base, proc)
                mode2, numeric2 = report_counts(rep2)
                rep.log(f"[INFO] {label} baseline-vs-process compare "
                        f"rc={rc2} mode={mode2} numeric={numeric2}")
                for line in rep2.splitlines()[:8]:
                    rep.log(f"[INFO]   {line}")
                rep.check(f"#136 工艺场景 {label} 流单变量变化"
                          "（numeric == 1）", numeric2 == 1,
                          f"numeric={numeric2}")
                rep.check(f"#136 工艺场景 {label} 流模式字段不变"
                          "（mode == 0）", mode2 == 0, f"mode={mode2}")
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
