#!/usr/bin/env python3
# m8c_temp_mix_gate.py — macOS port: Feishu #111/#112 high/low temperature
# filament mixing gate.
# feishu: baseline#111 baseline#112  (macOS port; corresponds to the enabled
#         Windows m8c_temp_mix_gate, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   #112 two low-temperature filaments (PETG + PLA Silk) coexist -> slice
#        completes
#   #111 switching slot 2 to Generic ABS (high-temperature) makes the mixing
#        gate block the plate: the Slice click is swallowed / the button stays
#        disabled, and a "Detected both high and low temperature" banner shows
#   restore: slot 2 back to PLA Silk -> slicing works again
#
# macOS mapping:
#   fixture   -> fixtures/mixed_filament_test.3mf (slot 1 PETG, slot 2 PLA Silk)
#   scene     -> Delete All + two cubes; the second one is remapped to PLA Silk
#                via the object context menu Change Filament (m8d helper)
#   preset    -> sidebar combo: slot 2 -> Generic/ABS, restore via
#                Snapmaker/PLA Silk (self-drawn two-level menu, OCR clicks)
#   gate      -> the Slice plate button is teal when enabled and grey when the
#                gate disables it; teal_fraction() over the button rect is the
#                pixel oracle (same intent as the Windows template match).
#                A blocked click must leave the button grey for 8s.
#   slice     -> mac_common.slice_and_export (m8x_158 recipe); the gcode's
#                filament usage proves both slots are really used.
#
# Artifacts: artifacts/mac/pilot/m8c/{report.log,result.json,work/*.gcode,
#            *.png}.

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
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
    teal_fraction, wait_for_model,
)
import mac_gcode  # noqa: E402
import m7b_new_project as m7b  # noqa: E402
import m8d_purifier_gcode as c8d  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8c"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
# The text pill of the Slice plate button (the teal check badge sits to its
# left, so exclude it).  Measured 1200x800: enabled teal=0.70, gated teal=0.00.
SLICE_RECT = (950, 29, 82, 27)
TEAL_ON = 0.40
TEAL_OFF = 0.05


def slice_pill(driver, win):
    frame = driver.capture(win)
    sx = frame.width / 1200.0
    sy = frame.height / 800.0
    rect = Rect(SLICE_RECT[0] * sx, SLICE_RECT[1] * sy,
                SLICE_RECT[2] * sx, SLICE_RECT[3] * sy)
    return frame, rect


def slice_button_teal(driver, win) -> float:
    frame, rect = slice_pill(driver, win)
    return teal_fraction(frame, rect)


def prepare_tab(driver, win) -> bool:
    """The app jumps to Preview after a slice; the gate is on Prepare."""
    words = c8d.ocr_window(driver, win)
    tab = next((w for w in words
                if w.text.strip().lower() == "prepare" and w.rect.y < 70),
               None)
    if tab is None:
        return False
    driver.click(win.rect.x + tab.rect.center[0],
                 win.rect.y + tab.rect.center[1])
    time.sleep(1.2)
    return True


def banner_text(driver, win) -> str:
    words = c8d.ocr_window(driver, win)
    return " ".join(w.text for w in words)


def restore_pla_silk(driver, win, rep) -> str:
    """Slot-2 combo -> Snapmaker -> scroll the type submenu -> PLA Silk."""
    words = c8d.ocr_window(driver, win)
    combo = next((w for w in words
                  if 200 < w.rect.x < 400 and 400 <= w.rect.y <= 435), None)
    if combo is None:
        return "slot-2 combo not found"
    driver.click(win.rect.x + combo.rect.center[0],
                 win.rect.y + combo.rect.center[1])
    time.sleep(1.2)
    words = c8d.ocr_window(driver, win)
    vendor = next((w for w in words
                   if w.text.strip().lower() == "snapmaker"
                   and 200 < w.rect.x < 490 and w.rect.y > 440), None)
    if vendor is None:
        return "no Snapmaker vendor entry"
    driver.click(win.rect.x + vendor.rect.center[0],
                 win.rect.y + vendor.rect.center[1])
    time.sleep(1.0)
    pops = [w for w in driver.windows_for_pid(win.pid)
            if w.id != win.id and w.on_screen and w.layer != 0
            and w.rect.area > 3000]
    if not pops:
        return "no type submenu window"
    sub = max(pops, key=lambda w: w.rect.x)
    for step in range(15):
        words = c8d.ocr_window(driver, win)
        silk = next((w for w in words
                     if "silk" in w.text.lower() and w.rect.x > 450), None)
        if silk is not None:
            rep.log(f"[INFO] PLA Silk found after {step} scrolls @ "
                    f"{silk.rect.to_xywh()}")
            driver.click(win.rect.x + silk.rect.center[0],
                         win.rect.y + silk.rect.center[1])
            time.sleep(2.0)
            return c8d.read_slot2(driver, win)
        driver.wheel(sub.rect.center[0], sub.rect.center[1], -3)
        time.sleep(0.4)
    return "PLA Silk not found after scrolling"


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
    model = work / "m8c_mixed.3mf"
    shutil.copy2(DEFAULT_MODEL, model)
    g_a = work / "m8c_lowlow.gcode"
    g_c = work / "m8c_restored.gcode"
    roots = [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"]

    rep = Reporter(OUT)
    rep.log("=== m8c macOS high/low temperature mixing gate ===")
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
        rep.check("添加 cube A", m7b._add_cube(driver, app, win))
        time.sleep(1.0)
        rep.check("添加 cube B", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        result = c8d.change_filament_to_silk(driver, app, win, rep)
        rep.check("cube B 换槽 PLA Silk", result == "ok", result)
        if result != "ok":
            return rep.save({"stage": "change-filament"})

        # --- #112: low + low -> slice completes --------------------------
        if not slice_and_export(driver, win, rep, g_a, roots):
            rep.check("#112 低+低切片完成", False, "slice/export failed")
            return rep.save({"stage": "slice-lowlow"})
        used_a = mac_gcode.used_filaments(g_a.read_bytes())
        rep.log(f"[INFO] low+low used={used_a} size={g_a.stat().st_size}")
        rep.check("#112 低+低切片完成", True, f"used={used_a}")
        rep.check("两槽都在用（PETG + PLA Silk）", used_a == [1, 2],
                  f"used={used_a}")
        # The app auto-switches to Preview after slicing; the gate lives on
        # the Prepare page, so measure the button there.
        rep.check("回到 Prepare 页", prepare_tab(driver, win))
        time.sleep(1.0)
        teal_ok = slice_button_teal(driver, win)
        # After a completed slice the pill is grey (done state) even though
        # the plate is slicable again; only a plate change re-renders it teal.
        rep.log(f"[INFO] Slice button pill teal after low+low slice={teal_ok:.3f} "
                f"(done state)")

        # --- #111: slot 2 -> ABS -> gate blocks --------------------------
        row_abs = c8d.select_slot2_preset(driver, win, rep, "ABS")
        rep.log(f"[INFO] slot-2 row after ABS={row_abs!r}")
        rep.check("slot2 -> Generic ABS", "abs" in row_abs.lower(), row_abs)
        if "abs" not in row_abs.lower():
            return rep.save({"stage": "select-abs"})
        time.sleep(1.0)
        teal_blocked = slice_button_teal(driver, win)
        rep.log(f"[INFO] Slice button pill teal under ABS gate={teal_blocked:.3f}")
        driver.capture(win).save_png(OUT / "gated.png")
        text = banner_text(driver, win)
        has_banner = ("high and low" in text.lower()
                      or ("temperature" in text.lower()
                          and "detected" in text.lower()))
        rep.log(f"[INFO] mixing banner OCR={'PASS' if has_banner else 'absent'}")
        rep.log(f"[INFO] pill teal under the gate={teal_blocked:.3f} "
                f"(done state was {teal_ok:.3f}); the blocked-click diff "
                f"below is the hard oracle")
        rep.check("#111 混用横幅（证据）", has_banner,
                  "OCR 'high and low'" if has_banner else "not found (evidence)")
        # Click Slice: a blocked click must not start slicing (Windows checks
        # that the button's rendered state does not change after the click).
        before_frame, pill = slice_pill(driver, win)
        before = before_frame.crop(pill)
        sx = win.rect.w / 1200.0
        sy = win.rect.h / 800.0
        driver.click(win.rect.x + 1000 * sx, win.rect.y + 45 * sy)
        time.sleep(6.0)
        after_frame, pill = slice_pill(driver, win)
        after = after_frame.crop(pill)
        click_diff = before.difference(after)
        teal_after_click = slice_button_teal(driver, win)
        rep.log(f"[INFO] blocked click: pill diff={click_diff:.4f} "
                f"teal={teal_after_click:.3f}")
        rep.check("#111 点击 Slice 被拦（按钮未变）",
                  click_diff < 0.02 and teal_after_click < TEAL_OFF,
                  f"diff={click_diff:.4f} teal={teal_after_click:.3f}")

        # --- restore PLA Silk -> gate lifts -------------------------------
        row_silk = restore_pla_silk(driver, win, rep)
        rep.log(f"[INFO] slot-2 row after restore={row_silk!r}")
        rep.check("slot2 恢复 PLA Silk", "silk" in row_silk.lower(), row_silk)
        if "silk" not in row_silk.lower():
            return rep.save({"stage": "restore-silk"})
        time.sleep(1.0)
        teal_restored = slice_button_teal(driver, win)
        rep.log(f"[INFO] Slice button pill teal after restore={teal_restored:.3f}")
        rep.check("门解除（Slice 按钮恢复 teal）", teal_restored > TEAL_ON,
                  f"teal={teal_restored:.3f}")

        # A restored click must really start a slice (button changes), then
        # export the fresh result.
        before_frame, pill = slice_pill(driver, win)
        before = before_frame.crop(pill)
        driver.click(win.rect.x + 1000 * sx, win.rect.y + 45 * sy)
        time.sleep(2.5)
        after_frame, pill = slice_pill(driver, win)
        after = after_frame.crop(pill)
        started_diff = before.difference(after)
        rep.log(f"[INFO] restored click: pill diff={started_diff:.4f}")
        rep.check("恢复后点击 Slice 启动切片", started_diff > 0.02,
                  f"diff={started_diff:.4f}")
        time.sleep(20.0)
        rows = [c for c in driver.controls(win, max_depth=12)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("export g-code")]
        exported = bool(rows) and rows[0].enabled
        if exported:
            driver.click_control(rows[0])
            time.sleep(1.5)
            exported = driver.save_file_dialog(
                win, g_c, default_dir=g_c.parent, accept_anywhere=True,
                search_roots=roots) and g_c.exists()
        rep.check("恢复后可切片（gcode 落盘）", exported,
                  f"exists={g_c.exists()}")
        if g_c.exists():
            used_c = mac_gcode.used_filaments(g_c.read_bytes())
            rep.log(f"[INFO] restored used={used_c} size={g_c.stat().st_size}")
            rep.check("恢复后 gcode 用量可读", bool(used_c), f"used={used_c}")

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
        exit_code = rep.save({"covered": ["#111", "#112"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
