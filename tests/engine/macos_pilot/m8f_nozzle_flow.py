#!/usr/bin/env python3
# m8f_nozzle_flow.py — macOS high-flow nozzle presets: Feishu #133/#135.
# feishu: baseline#133 baseline#135  (macOS port; corresponds to the enabled
#         Windows m8f_nozzle_flow, registered in cases.MACOS_BASELINE)
#
# #133 (nozzle defaults 0.4mm/Standard) passes.  #135 uses the CURRENT Windows
# criterion, not raw compare rc=0: the gcode carries the packages' per-flow
# arrays in a fixed order (A inner_wall_speed 550,600 vs B 300,550), so the
# official comparator reports mode=2/numeric=39 even when the EFFECTIVE entry
# selected by each flow mode is identical.  The case therefore checks
# effective_diff()==0 (index-resolved, same helper as the Windows case) plus
# mode_diff>=1; numeric_diff is logged as evidence.
#
# Windows assertions:
#   #133 the nozzle panel defaults are Diameter '0.4mm' and Flow 'Standard'
#   #135 (STD-TEST process + STD-TEST filament + Standard flow) and
#        (HF-TEST process + HF-TEST filament + High Flow) slice to gcodes
#        whose EFFECTIVE per-flow values are identical and whose mode fields
#        differ, proving the two-index preset values are read by mode
#
# macOS mapping:
#   preset menus -> process combo: User-presets rows (HF-TEST, STD-TEST,
#                   FLOW-TEST) at y=616/640/668; filament combo -> hover
#                   'Custom' -> variant rows (FLOW, HF, STD) at y=474/500/526
#   flow combo   -> Nozzle Flow at (308,288); menu Standard (310,324) /
#                   High Flow (312,349)
#   readback     -> the exported gcode carries print_settings_id and
#                   filament_settings_id; both must name the target preset
#   compare      -> tools/compare_gcode.py (same authority as Windows)
#
# Artifacts: artifacts/mac/pilot/m8f/{report.log,result.json,work/*.gcode,
#            *.png}.

from __future__ import annotations

import argparse
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
    wait_for_model,
)
import m7b_new_project as m7b  # noqa: E402
import m8d_purifier_gcode as c8d  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8f"
COMPARE = HERE / "tools" / "compare_gcode.py"
PROC_ROW = {"HF": 0, "STD": 1, "FLOW": 2}      # menu order at y=616/640/668
FIL_ROW = {"FLOW": 0, "HF": 1, "STD": 2}       # variant order at y=474/500/526


def ocr(driver, win):
    return c8d.ocr_window(driver, win)


def confirm_grouping(driver, app, win, rep) -> bool:
    """The High Flow switch raises 'Custom Filament Grouping'.  The PLA chip
    must be dragged to the High Flow Nozzle column (the default Standard
    assignment leaves the high-flow preset inactive), then Confirm."""
    from harness.platform.base import Rect
    from harness.platform.macos_ocr import recognize_text
    from m8b_official_color import drag
    for w in driver.windows_for_pid(app.pid):
        if not w.on_screen or w.id == win.id or w.layer == 0:
            continue
        if "filament grouping" not in (w.title or "").lower():
            continue
        words = recognize_text(
            driver.capture_screen().crop(win.rect),
            Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
                 w.rect.w, w.rect.h))
        confirm = next((x for x in words
                        if x.text.strip().lower() == "confirm"), None)
        pla = next((x for x in words if x.text.strip().upper() == "PLA"), None)
        hf = next((x for x in words
                   if "high flow nozzle" in x.text.lower()), None)
        rep.log(f"[INFO] grouping dialog; confirm={confirm} "
                f"pla={pla.rect.to_xywh() if pla else None} "
                f"hf={hf.rect.to_xywh() if hf else None}")
        if pla is not None and hf is not None:
            drag(win.rect.x + pla.rect.center[0],
                 win.rect.y + pla.rect.center[1],
                 win.rect.x + hf.rect.center[0],
                 win.rect.y + pla.rect.center[1])
            time.sleep(1.0)
            words = recognize_text(
                driver.capture_screen().crop(win.rect),
                Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
                     w.rect.w, w.rect.h))
            pla2 = next((x for x in words
                         if x.text.strip().upper() == "PLA"), None)
            rep.log(f"[INFO] PLA chip after drag="
                    f"{pla2.rect.to_xywh() if pla2 else None}")
        if confirm is not None:
            driver.click(win.rect.x + confirm.rect.center[0],
                         win.rect.y + confirm.rect.center[1])
            time.sleep(1.5)
            return True
    return False


def prepare_tab(driver, win) -> bool:
    """The app jumps to Preview after a slice; preset edits and Slice need
    the Prepare page (the Preview Slice button stays grey)."""
    ws = ocr(driver, win)
    tab = next((w for w in ws if w.text.strip().lower() == "prepare"
                and w.rect.y < 70), None)
    if tab is None:
        return False
    driver.click(win.rect.x + tab.rect.center[0],
                 win.rect.y + tab.rect.center[1])
    time.sleep(1.2)
    return True


def click_word(driver, win, word):
    driver.click(win.rect.x + word.rect.center[0],
                 win.rect.y + word.rect.center[1])
    time.sleep(1.2)


def select_process(driver, win, rep, which: str) -> bool:
    ws = ocr(driver, win)
    combo = next((w for w in ws if "standard @" in w.text.lower()
                  and w.rect.x < 430), None)
    if combo is None:
        rep.log("[INFO] process combo not found")
        return False
    click_word(driver, win, combo)
    ws = ocr(driver, win)
    rows = [w for w in ws if w.rect.x < 430 and 600 <= w.rect.y <= 700
            and len(w.text) > 10 and "system" not in w.text.lower()]
    rows.sort(key=lambda w: w.rect.y)
    rep.log(f"[INFO] process rows={[(w.text, round(w.rect.y)) for w in rows]}")
    if which == "FLOW":
        # The menu truncates the "- FLOW-TEST" suffix; the FLOW-TEST process
        # is the only 0.24mm Standard row visible (the current is 0.20mm).
        match = next((w for w in rows
                      if "0.24mm standard" in w.text.lower()), None)
    else:
        needle = f"- {which.lower()}-test"
        match = next((w for w in rows if needle in w.text.lower()), None)
    if match is None:
        driver.send_key("escape")
        return False
    rep.log(f"[INFO] process {which} -> {match.text!r} "
            f"@ {match.rect.to_xywh()}")
    click_word(driver, win, match)
    return True


def select_filament(driver, win, rep, which: str) -> bool:
    ws = ocr(driver, win)
    combo = next((w for w in ws if w.rect.x < 200 and 400 <= w.rect.y <= 435
                  and len(w.text) > 3), None)
    if combo is None:
        rep.log("[INFO] filament combo not found")
        return False
    click_word(driver, win, combo)
    ws = ocr(driver, win)
    custom = next((w for w in ws if w.text.strip().lower() == "custom"
                   and w.rect.x < 200 and w.rect.y > 440), None)
    if custom is None:
        rep.log(f"[INFO] Custom row not found: "
                f"{[(w.text, w.rect.y) for w in ws if 440 < w.rect.y < 600][:12]}")
        driver.send_key("escape")
        return False
    driver.move(win.rect.x + custom.rect.center[0],
                win.rect.y + custom.rect.center[1])
    time.sleep(1.8)
    ws = ocr(driver, win)
    rows = [w for w in ws if w.rect.x > 280 and 460 < w.rect.y < 560
            and "snap" in w.text.lower()]
    rows.sort(key=lambda w: w.rect.y)
    idx = FIL_ROW[which]
    if len(rows) <= idx:
        rep.log(f"[INFO] filament variants={[(w.text, w.rect.y) for w in rows]}")
        driver.send_key("escape")
        return False
    rep.log(f"[INFO] filament {which} -> row {idx} {rows[idx].text!r} "
            f"@ {rows[idx].rect.to_xywh()}")
    click_word(driver, win, rows[idx])
    return True


def set_flow(driver, win, rep, target: str) -> bool:
    ws = ocr(driver, win)
    combo = next((w for w in ws if w.text.strip().lower() in
                  ("standard", "high flow") and w.rect.x > 200
                  and w.rect.y < 350), None)
    if combo is None:
        rep.log("[INFO] flow combo not found")
        return False
    if combo.text.strip().lower() == target.lower():
        rep.log(f"[INFO] flow already {target}")
        return True
    click_word(driver, win, combo)
    ws = ocr(driver, win)
    option = next((w for w in ws if w.text.strip().lower() == target.lower()
                   and w.rect.y > 310), None)
    if option is None:
        rep.log(f"[INFO] flow options={[(w.text, w.rect.y) for w in ws if 300 < w.rect.y < 400]}")
        driver.send_key("escape")
        return False
    click_word(driver, win, option)
    return True


def gcode_ids(path: Path) -> tuple[list[str], str | None]:
    text = path.read_text(encoding="utf-8", errors="replace")
    fil = re.search(r"^; filament_settings_id = (.*)$", text, re.M)
    proc = re.search(r"^; print_settings_id = (.*)$", text, re.M)
    fids = ([v.strip().strip('"') for v in fil.group(1).split(";") if v.strip()]
            if fil else [])
    pid = proc.group(1).strip().strip('"') if proc else None
    return fids, pid


def compare(a: Path, b: Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(COMPARE), str(a), str(b)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    report = (r.stdout or "") + (r.stderr or "")
    return r.returncode, report


CONF_RE = re.compile(r"^;\s*([A-Za-z0-9_.]+)\s*=\s*(.*)$")
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?%?")


def read_config(path: Path):
    """{key: [values]} of the gcode's CONFIG_BLOCK (self-contained)."""
    out: dict = {}
    inside = False
    for line in path.read_text(encoding="utf-8-sig",
                               errors="replace").splitlines():
        s = line.strip()
        if s == "; CONFIG_BLOCK_START":
            inside = True
            continue
        if s == "; CONFIG_BLOCK_END":
            inside = False
            continue
        if not inside:
            continue
        m = CONF_RE.match(line)
        if m:
            out.setdefault(m.group(1), []).append(m.group(2).strip())
    return out


def flow_index(cfg) -> int:
    val = cfg.get("nozzle_volume_type") or cfg.get("filament_volume_type") or []
    return 1 if "high_flow" in ",".join(val).lower() else 0


def effective_diff(a: Path, b: Path):
    """Index-resolved comparison, same criterion as the Windows m8f case."""
    ca, cb = read_config(a), read_config(b)
    ia, ib = flow_index(ca), flow_index(cb)
    mismatches, checked = [], 0
    for key in sorted(set(ca) | set(cb)):
        va, vb = ca.get(key, []), cb.get(key, [])
        if va == vb or not va or not vb:
            continue
        pa = [p.strip() for p in ",".join(va).split(",")]
        pb = [p.strip() for p in ",".join(vb).split(",")]
        if len(pa) < 2 or len(pb) < 2:
            continue
        if not (all(NUM_RE.match(x) for x in pa)
                and all(NUM_RE.match(x) for x in pb)):
            continue
        checked += 1
        if pa[min(ia, len(pa) - 1)] != pb[min(ib, len(pb) - 1)]:
            mismatches.append((key, pa[min(ia, len(pa) - 1)],
                               pb[min(ib, len(pb) - 1)]))
    return mismatches, checked, ia, ib


def report_counts(report: str):
    def grab(pat):
        m = re.search(pat, report)
        return int(m.group(1)) if m else -1
    return (grab(r"高流量模式字段变化：(\d+) 项"),
            grab(r"数值配置变化：(\d+) 项"))


def select_state(driver, win, rep, proc: str, fil: str, flow: str,
                 tag: str) -> bool:
    ok_p = select_process(driver, win, rep, proc)
    ok_f = select_filament(driver, win, rep, fil)
    ok_fl = set_flow(driver, win, rep, flow)
    rep.log(f"[INFO] {tag} selections: process={ok_p} filament={ok_f} "
            f"flow={ok_fl}")
    return ok_p and ok_f and ok_fl


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
    g_a = work / "m8f_std.gcode"
    g_b = work / "m8f_hf.gcode"

    rep = Reporter(OUT)
    rep.log("=== m8f macOS high-flow nozzle presets ===")
    rep.log(f"datadir={args.datadir}")

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
                  f"rect={win.rect.to_xywh()}")
        time.sleep(4.0)
        ws = ocr(driver, win)
        text = " ".join(w.text for w in ws).lower()
        rep.check("#133 喷嘴默认 Diameter=0.4mm", "diameter" in text
                  and "0.4mm" in text,
                  " ".join(w.text for w in ws if "0.4" in w.text)[:60])
        rep.check("#133 喷嘴默认 Flow=Standard", "standard" in text,
                  " ".join(w.text for w in ws if "standard" in w.text.lower())[:60])
        rep.check("添加 cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        driver.capture(win).save_png(OUT / "cube.png")

        # -------- A: STD-TEST + Standard flow ------------------------------
        rep.check("A 选择 STD-TEST 包 + Standard",
                  select_state(driver, win, rep, "STD", "STD", "Standard", "A"))
        if not slice_and_export(driver, win, rep, g_a,
                                [work, OUT, ARTIFACTS / "pilot",
                                 HERE / "fixtures"]):
            rep.check("#135 STD 状态切片", False, "slice/export failed")
            return rep.save({"stage": "slice-a"})
        fids_a, pid_a = gcode_ids(g_a)
        rep.log(f"[INFO] A ids={fids_a} print={pid_a}")
        rep.check("#135 STD 预设已生效",
                  pid_a is not None and pid_a.endswith("- STD-TEST")
                  and any("std-test" in f.lower() for f in fids_a),
                  f"print={pid_a} filament={fids_a}")

        # -------- B: HF-TEST + High Flow -----------------------------------
        rep.check("回到 Prepare 页", prepare_tab(driver, win))
        rep.check("B 选择 HF-TEST 包 + High Flow",
                  select_state(driver, win, rep, "HF", "HF", "High Flow", "B"))
        rep.log(f"[INFO] grouping dialog before slice="
                f"{confirm_grouping(driver, app, win, rep)}")
        # A High Flow switch may raise a confirmation prompt.
        time.sleep(1.5)
        driver.capture(win).save_png(OUT / "after_highflow.png")
        if not slice_and_export(driver, win, rep, g_b,
                                [work, OUT, ARTIFACTS / "pilot",
                                 HERE / "fixtures"],
                                on_poll=lambda: confirm_grouping(
                                    driver, app, win, rep)):
            rep.check("#135 HF 状态切片", False, "slice/export failed")
            return rep.save({"stage": "slice-b"})
        fids_b, pid_b = gcode_ids(g_b)
        rep.log(f"[INFO] B ids={fids_b} print={pid_b}")
        rep.check("#135 HF 预设已生效",
                  pid_b is not None and pid_b.endswith("- HF-TEST")
                  and any("hf-test" in f.lower() for f in fids_b),
                  f"print={pid_b} filament={fids_b}")

        rc, report = compare(g_a, g_b)
        mode_diff, num_diff = report_counts(report)
        bad, checked, ia, ib = effective_diff(g_a, g_b)
        rep.log(f"[INFO] compare rc={rc} mode={mode_diff} numeric={num_diff} "
                f"flow_indices A={ia} B={ib} checked={checked} "
                f"mismatches={len(bad)}")
        for line in report.splitlines()[:12]:
            rep.log(f"[INFO]   {line}")
        if bad:
            rep.log(f"[INFO] effective mismatches: {bad[:8]}")
        rep.check("#135 标准/高流量 effective values identical "
                  "（口径同 Windows effective_diff + mode>=1）",
                  not bad and mode_diff >= 1,
                  f"checked={checked} mismatches={len(bad)} "
                  f"mode={mode_diff} numeric={num_diff}")

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
        exit_code = rep.save({"covered": ["#133", "#135"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
