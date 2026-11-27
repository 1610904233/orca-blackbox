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
#   #135 (doc 标准测试 process + 标准测试 filament + Standard flow) and
#        (doc 高流量测试 process + 高流量测试 filament + High Flow) slice to
#        gcodes whose EFFECTIVE per-flow values are identical and whose mode
#        fields differ, proving the two-index preset values are read by mode
#
# macOS mapping:
#   preset menus -> process combo: doc User-presets rows (标准测试, 高流量测试,
#                   流量测试) at y=550/576/602; filament combo -> hover
#                   'Custom' -> doc rows (标准测试, 流量测试, 高流量测试)
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
# The gcode test plan's prepared user presets (doc default.zip), not the
# Windows test's ASCII STD-TEST/HF-TEST copies.  User process rows appear at
# y=550/576/602 in the order 标准测试 / 高流量测试 / 流量测试; the filament
# Custom list is 标准测试 / 流量测试 / 高流量测试.
PROC_ROW = {"STD": 0, "HF": 1, "FLOW": 2}
FIL_ROW = {"STD": 0, "FLOW": 1, "HF": 2}


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
        rep.log(f"[INFO] grouping window={w.rect.to_xywh()} "
                f"main={win.rect.to_xywh()}")
        rep.log(f"[INFO] grouping words="
                f"{[(x.text, x.rect.to_xywh()) for x in words][:24]}")
        try:
            ax = [(c.role, c.title, c.value, c.rect.to_xywh())
                  for c in driver.controls(w)]
            rep.log(f"[INFO] grouping AX={ax[:30]}")
        except Exception as exc:  # noqa: BLE001
            rep.log(f"[INFO] grouping AX error: {exc}")
        confirm = next((x for x in words
                        if x.text.strip().lower() == "confirm"), None)
        pla = next((x for x in words if x.text.strip().upper() == "PLA"), None)
        hf = next((x for x in words
                   if "high flow nozzle" in x.text.lower()), None)
        rep.log(f"[INFO] grouping dialog; confirm={confirm} "
                f"pla={pla.rect.to_xywh() if pla else None} "
                f"hf={hf.rect.to_xywh() if hf else None}")
        if pla is not None and hf is not None:
            def chip():
                ws2 = recognize_text(
                    driver.capture_screen().crop(win.rect),
                    Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
                         w.rect.w, w.rect.h))
                return next((x for x in ws2
                             if x.text.strip().upper() == "PLA"), None)

            # The header text is not a drop target; the column body starts
            # below it.  The old drop at the header y left the chip in the
            # Standard column (measured 2026-11-26).
            # The custom dialog does not accept synthetic drag-and-drop.
            # It has a transfer arrow between the two columns; select the
            # chip, click that button, then verify the chip moved right.
            driver.click(win.rect.x + pla.rect.center[0],
                         win.rect.y + pla.rect.y - 15)
            time.sleep(0.5)
            moved = False
            pla2 = None
            for ax, ay in ((hf.rect.x - 50, hf.rect.y + 90),
                           (hf.rect.x - 30, hf.rect.bottom + 70),
                           (hf.rect.x - 60, hf.rect.bottom + 80)):
                rep.log(f"[INFO] click transfer button @({ax},{ay})")
                driver.click(win.rect.x + ax, win.rect.y + ay)
                time.sleep(0.9)
                pla2 = chip()
                moved = pla2 is not None and pla2.rect.x > hf.rect.x
                rep.log(f"[INFO] PLA chip after transfer="
                        f"{pla2.rect.to_xywh() if pla2 else None} moved={moved}")
                if moved:
                    break
            rep.check("High Flow 分组（PLA -> High Flow Nozzle）", moved,
                      f"chip={pla2.rect.to_xywh() if pla2 else None}")
        if confirm is not None:
            driver.click(win.rect.x + confirm.rect.center[0],
                         win.rect.y + confirm.rect.center[1])
            time.sleep(1.5)
            return True
    return False


def prepare_doc_presets(datadir: Path) -> None:
    """Seed the gcode test plan's prepared user presets (default.zip).

    The repo fixture is the doc's default user folder: PLA SnapSpeed
    标准测试 / 流量测试 / 高流量测试 and the matching 0.20mm/0.24mm process
    presets.  Copying it before launch prevents the driver from seeding the
    Windows test's hand-made STD-TEST/HF-TEST packages.
    """
    src = HERE / "tests/engine/macos_pilot/fixtures/gcode_plan/default"
    dst = datadir / "user" / "default"
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


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


NOZZLE_TABS_RE = re.compile(r"nozzle\s*([1-4])$", re.I)
DIA_RE = re.compile(r"0\.[0-9]mm", re.I)


def _panel_dia(words):
    return next((w for w in words
                if DIA_RE.search(w.text) and w.rect.x < 200
                and 260 < w.rect.y < 315), None)


def _panel_flow(words):
    return next((w for w in words
                if _norm_combo(w.text) in ("standard", "high flow")
                and w.rect.x > 200 and 260 < w.rect.y < 315), None)


def _dismiss_diameter_dialog(driver, win) -> bool:
    """The first diameter change shows 'Set Nozzle Diameter' (syncs all
    nozzles).  Tick 'Don't show this again' once in the sandbox profile and
    press OK; later changes have no dialog."""
    ws = ocr(driver, win)
    ok = next((w for w in ws if w.text.strip().lower() == "ok"), None)
    if ok is None:
        return False
    dont = next((w for w in ws if "don't show this again" in w.text.lower()),
                None)
    if dont is not None:
        driver.click(win.rect.x + dont.rect.x - 15,
                     win.rect.y + dont.rect.center[1])
        time.sleep(0.4)
    driver.click(win.rect.x + ok.rect.center[0],
                 win.rect.y + ok.rect.center[1])
    time.sleep(0.9)
    return True


def check_nozzle_panel(driver, win, rep) -> bool:
    """#133: four nozzle tabs, every tab defaults to 0.4mm/Standard; the
    diameter list is 0.2/0.4/0.6/0.8; flow at 0.4mm is Standard + High Flow;
    flow at 0.2/0.6/0.8 is Standard only.  Restores Nozzle 1 to 0.4mm/
    Standard for the #135 slices."""
    ws = ocr(driver, win)
    tabs = [w for w in ws if NOZZLE_TABS_RE.match(w.text.strip())
            and 220 < w.rect.y < 280]
    tabs.sort(key=lambda w: w.rect.x)
    rep.log(f"[INFO] nozzle tabs={[(w.text, w.rect.to_xywh()) for w in tabs]}")
    rep.check("#133 四个喷嘴 Tab", len(tabs) >= 4,
              f"tabs={[w.text for w in tabs]}")
    if len(tabs) < 4:
        return False
    ok = True
    for tab in tabs[:4]:
        click_word(driver, win, tab)
        time.sleep(0.8)
        ws = ocr(driver, win)
        dia = _panel_dia(ws)
        flow = _panel_flow(ws)
        good = (dia is not None and "0.4mm" in dia.text
                and flow is not None
                and _norm_combo(flow.text) == "standard")
        rep.check(f"#133 {tab.text} 默认 0.4mm/Standard", good,
                  f"dia={dia.text if dia else None} "
                  f"flow={flow.text if flow else None}")
        ok = ok and good

    # Nozzle 1: diameter list, then 0.4 flow list.
    click_word(driver, win, tabs[0])
    time.sleep(0.8)
    ws = ocr(driver, win)
    dia = _panel_dia(ws)
    if dia is None:
        rep.check("#133 直径下拉", False, "diameter value missing")
        return False
    click_word(driver, win, dia)
    time.sleep(0.7)
    ws = ocr(driver, win)
    dia_opts = {w.text.strip().lower() for w in ws
                if re.fullmatch(r"0\.[0-9]mm", w.text.strip())
                and w.rect.y > 300 and w.rect.x < 300}
    want = {"0.2mm", "0.4mm", "0.6mm", "0.8mm"}
    rep.check("#133 0.4mm 直径选项 0.2/0.4/0.6/0.8",
              want <= dia_opts, f"opts={sorted(dia_opts)}")
    # Close the diameter popup without changing the current 0.4mm.
    driver.send_key("escape")
    time.sleep(0.8)

    ws = ocr(driver, win)
    flow = _panel_flow(ws)
    if flow is None:
        rep.check("#133 流量下拉", False, "flow value missing")
        return False
    click_word(driver, win, flow)
    time.sleep(0.7)
    ws = ocr(driver, win)
    rep.log(f"[INFO] 0.4 flow popup words="
            f"{[(w.text, w.rect.to_xywh()) for w in ws if 280 < w.rect.y < 390]}")
    flow_opts = {_norm_combo(w.text) for w in ws
                 if 300 < w.rect.y < 400 and w.rect.x > 200
                 and _norm_combo(w.text) in ("standard", "high flow")}
    rep.check("#133 0.4mm 流量选项 标准/高流量",
              {"standard", "high flow"} <= flow_opts,
              f"opts={sorted(flow_opts)}")
    opt_std = next((w for w in ws if _norm_combo(w.text) == "standard"
                    and 300 < w.rect.y < 400 and w.rect.x > 200), None)
    if opt_std is not None:
        click_word(driver, win, opt_std)
    else:
        driver.send_key("escape")
    time.sleep(0.8)

    for target in ("0.2mm", "0.6mm", "0.8mm"):
        ws = ocr(driver, win)
        dia = _panel_dia(ws)
        if dia is None:
            rep.check(f"#133 {target} 直径下拉", False, "missing")
            ok = False
            continue
        click_word(driver, win, dia)
        time.sleep(0.7)
        ws = ocr(driver, win)
        opt = next((w for w in ws if w.text.strip().lower() == target.lower()
                    and w.rect.y > 300 and w.rect.x < 300), None)
        if opt is None:
            rep.check(f"#133 {target} 直径选项", False,
                      f"words={[(w.text, w.rect.y) for w in ws if w.rect.y > 300][:8]}")
            driver.send_key("escape")
            ok = False
            continue
        click_word(driver, win, opt)
        time.sleep(0.8)
        dialog = _dismiss_diameter_dialog(driver, win)
        rep.log(f"[INFO] {target} sync dialog={dialog}")
        ws = ocr(driver, win)
        dia = _panel_dia(ws)
        flow = _panel_flow(ws)
        rep.check(f"#133 {target} 已选", dia is not None
                  and target.lower() in dia.text.lower(),
                  f"dia={dia.text if dia else None}")
        rep.check(f"#133 {target} 流量默认标准",
                  flow is not None and _norm_combo(flow.text) == "standard",
                  f"flow={flow.text if flow else None}")
        if flow is not None:
            click_word(driver, win, flow)
            time.sleep(0.7)
            ws = ocr(driver, win)
            fopts = [(w.text, w.rect.to_xywh()) for w in ws
                     if 300 < w.rect.y < 400 and w.rect.x > 200
                     and _norm_combo(w.text) in ("standard", "high flow")]
            rep.log(f"[INFO] {target} flow popup words="
                    f"{[(w.text, w.rect.to_xywh()) for w in ws if 280 < w.rect.y < 390]}")
            high = any(_norm_combo(w.text) == "high flow" for w, _r in fopts)
            std = any(_norm_combo(w.text) == "standard" for w, _r in fopts)
            # A disabled/single-value combo may not open; the visible value
            # must still be Standard and High Flow must not be offered.
            only_std = (std and not high) if fopts else (
                flow is not None and _norm_combo(flow.text) == "standard"
                and not high)
            rep.check(f"#133 {target} 流量仅标准", only_std,
                      f"opts={fopts} flow={flow.text if flow else None}")
            ostd = next((w for w in ws if _norm_combo(w.text) == "standard"
                         and 300 < w.rect.y < 400 and w.rect.x > 200), None)
            if ostd is not None:
                click_word(driver, win, ostd)
            else:
                driver.send_key("escape")
            time.sleep(0.8)
            ok = ok and only_std
        # restore 0.4mm
        ws = ocr(driver, win)
        dia = _panel_dia(ws)
        if dia is not None and "0.4mm" not in dia.text:
            click_word(driver, win, dia)
            time.sleep(0.7)
            ws = ocr(driver, win)
            opt4 = next((w for w in ws if w.text.strip().lower() == "0.4mm"
                         and w.rect.y > 300 and w.rect.x < 300), None)
            if opt4 is not None:
                click_word(driver, win, opt4)
            else:
                driver.send_key("escape")
            time.sleep(0.8)
            _dismiss_diameter_dialog(driver, win)
        ws = ocr(driver, win)
        flow = _panel_flow(ws)
        if flow is not None and _norm_combo(flow.text) != "standard":
            click_word(driver, win, flow)
            time.sleep(0.7)
            ws = ocr(driver, win)
            ostd = next((w for w in ws if _norm_combo(w.text) == "standard"
                         and 300 < w.rect.y < 400 and w.rect.x > 200), None)
            if ostd is not None:
                click_word(driver, win, ostd)
            else:
                driver.send_key("escape")
            time.sleep(0.8)

    ws = ocr(driver, win)
    dia = _panel_dia(ws)
    flow = _panel_flow(ws)
    final_ok = (dia is not None and "0.4mm" in dia.text
                and flow is not None and _norm_combo(flow.text) == "standard")
    rep.check("#133 恢复 Nozzle1 0.4mm/Standard", final_ok,
              f"dia={dia.text if dia else None} "
              f"flow={flow.text if flow else None}")
    return ok and final_ok


def select_process(driver, win, rep, which: str) -> bool:
    ws = ocr(driver, win)
    combo = next((w for w in ws if "standard @" in w.text.lower()
                  and w.rect.x < 430), None)
    if combo is None:
        rep.log("[INFO] process combo not found")
        return False
    click_word(driver, win, combo)
    ws = ocr(driver, win)
    # The popup truncates the preset suffix, so select by the fixed order of
    # the user rows (HF / STD / FLOW) instead of matching the hidden text.
    # The current app lists them at y=550/576/602; the System header and
    # rows start below 630.
    rows = [w for w in ws if w.rect.x < 430 and 540 <= w.rect.y <= 620
            and len(w.text) > 10 and "system" not in w.text.lower()]
    rows.sort(key=lambda w: w.rect.y)
    rep.log(f"[INFO] process rows={[(w.text, round(w.rect.y)) for w in rows]}")
    idx = PROC_ROW[which]
    if len(rows) <= idx:
        rep.log(f"[INFO] user process rows missing (need {idx + 1})")
        driver.send_key("escape")
        return False
    match = rows[idx]
    rep.log(f"[INFO] process {which} -> row {idx} {match.text!r} "
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


def _norm_combo(text: str) -> str:
    """Combo values OCR as '- Standard' / '~ Standard' (icon glyphs leak
    into the word).  Compare the label itself, not the decoration."""
    return re.sub(r"^[^A-Za-z0-9]+", "", text.strip()).strip().lower()


def set_flow(driver, win, rep, target: str) -> bool:
    ws = ocr(driver, win)
    combo = next((w for w in ws if _norm_combo(w.text) in
                  ("standard", "high flow") and w.rect.x > 200
                  and w.rect.y < 350), None)
    if combo is None:
        rep.log("[INFO] flow combo not found")
        return False
    if _norm_combo(combo.text) == target.lower():
        rep.log(f"[INFO] flow already {target}")
        return True
    click_word(driver, win, combo)
    ws = ocr(driver, win)
    option = next((w for w in ws if _norm_combo(w.text) == target.lower()
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
    prepare_doc_presets(args.datadir)
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
        rep.check("#133 喷嘴面板完整检查", check_nozzle_panel(driver, win, rep))
        rep.check("添加 cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        driver.capture(win).save_png(OUT / "cube.png")

        # -------- A: doc 标准测试 + Standard flow --------------------------
        rep.check("A 选择标准测试包 + Standard",
                  select_state(driver, win, rep, "STD", "STD", "Standard", "A"))
        if not slice_and_export(driver, win, rep, g_a,
                                [work, OUT, ARTIFACTS / "pilot",
                                 HERE / "fixtures"]):
            rep.check("#135 STD 状态切片", False, "slice/export failed")
            return rep.save({"stage": "slice-a"})
        fids_a, pid_a = gcode_ids(g_a)
        rep.log(f"[INFO] A ids={fids_a} print={pid_a}")
        rep.check("#135 标准测试预设已生效",
                  pid_a is not None and pid_a.endswith("- 标准测试")
                  and any("标准测试" in f for f in fids_a),
                  f"print={pid_a} filament={fids_a}")

        # -------- B: doc 高流量测试 + High Flow ----------------------------
        rep.check("回到 Prepare 页", prepare_tab(driver, win))
        rep.check("B 选择高流量测试包 + High Flow",
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
        rep.check("#135 高流量测试预设已生效",
                  pid_b is not None and pid_b.endswith("- 高流量测试")
                  and any("高流量测试" in f for f in fids_b),
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
                  not bad and checked > 0 and mode_diff >= 1,
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
