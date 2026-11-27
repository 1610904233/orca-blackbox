#!/usr/bin/env python3
# m8x_125_aux_mix_pref.py — macOS port: Feishu #125 painted auxiliary filament.
# feishu: baseline#125  (macOS port; corresponds to the enabled Windows
#         m8x_125_aux_mix_pref, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   A. cube main filament = PLA Silk (low temperature)
#   B. slot 1 = Generic ABS (the high-temperature auxiliary source)
#   C. a color-painting dab applies the auxiliary filament
#   D. with the preference OFF, Slice is disabled and a click does not slice
#   E. the warning banner mentions both high and low temperature filaments
#   F. enabling 'Allow high/low temperature filament mixing' raises the risk
#      dialog; Confirm applies it
#   G. with the preference ON, Slice raises the risk dialog again, Confirm
#      lets the slice finish, and the gcode uses both filaments
#   H. the preference is restored to OFF and the app stays alive
#
# macOS mapping:
#   fixture -> Delete All + built-in Cube; object context menu Change
#              Filament -> Snapmaker PLA Silk.
#   filaments -> System Filaments dialog (slot-2 combo -> Add/Remove
#              filament): Clear all, tick Generic ABS + Generic PLA.  The
#              library order maps slot 1=PLA (low) and slot 2=ABS (high); the
#              cube's own main stays PLA Silk.
#   paint   -> Color Painting toolbar (996,90); palette tile 1; dabs around
#              the cube centre (814,396).
#   gate    -> Slice pill teal fraction (m8c) + OCR banner.
#   pref    -> Snapmaker Orca > Settings…; AXCheckBox sharing the 'Allow
#              high/low temperature filament mixing' label row; Confirm on
#              the 'High and Low Temperature Material Mixing Risk' dialog.
#
# Artifacts: artifacts/mac/pilot/m8x_125/{report.log,result.json,work/*.gcode,
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
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, export_gcode_enabled, launch_and_focus,
    slice_and_export, wait_for_model,
)
import mac_gcode  # noqa: E402
import m7b_new_project as m7b  # noqa: E402
import m8c_temp_mix_gate as c8c  # noqa: E402
import m8d_purifier_gcode as c8d  # noqa: E402
from m4e_mixing_paint import tooltip_below  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_125"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MODEL_POINT = (814, 396)
PAINT_ICON = (996, 90)
PREF_LABEL = "allow high/low temperature filament mixing"


def focus_prepare(driver, win) -> bool:
    driver.click(win.rect.x + 113, win.rect.y + 45)
    time.sleep(1.5)
    return True


def slot1_row(driver, win) -> str:
    return " ".join(w.text for w in c8d.ocr_window(driver, win)
                    if 20 < w.rect.x < 230 and 395 <= w.rect.y <= 435).strip()


def select_filament_set(driver, win, rep):
    """Set the project filament set to Generic ABS via System Filaments.

    The inline sidebar vendor/type submenu is not expandable with synthetic
    hover/click on this build.  m8d's proven path is: slot-2 combo ->
    Add/Remove filament -> System Filaments -> Clear all -> tick Generic ABS
    + Generic PLA -> Confirm.  Two types give slot 1 PLA (low) and slot 2
    ABS (high); the cube's own main stays PLA Silk.
    """
    result = c8d.select_slot2_preset(driver, win, rep, "ABS",
                                     also=("PLA",))
    row1 = slot1_row(driver, win)
    rep.log(f"[INFO] System Filaments slot1={row1!r} slot2={result!r}")
    return row1, result


def selected_filament(driver, win) -> int | None:
    words = recognize_text(driver.capture(win))
    label = next((w for w in words
                  if "selected filament" in w.text.lower()), None)
    if label is None:
        return None
    row = [w for w in words
           if abs(w.rect.center[1] - label.rect.center[1]) < 12
           and w.rect.x > label.rect.right - 5]
    for w in sorted(row, key=lambda w: w.rect.x):
        if w.text.strip().isdigit():
            return int(w.text.strip())
    return None


def paint_auxiliary(driver, win, rep) -> tuple[bool, tuple, tuple]:
    driver.click(win.rect.x + MODEL_POINT[0], win.rect.y + MODEL_POINT[1])
    time.sleep(1.0)
    tip = tooltip_below(driver, win, *PAINT_ICON)
    rep.log(f"[INFO] paint tooltip={tip!r}")
    driver.click(win.rect.x + PAINT_ICON[0], win.rect.y + PAINT_ICON[1])
    time.sleep(2.0)
    frame = driver.capture(win)
    frame.save_png(OUT / "palette.png")
    # The palette opens with the active slot (5, Generic ABS) selected;
    # clicking the custom-drawn chips is unreliable (hit boxes are offset),
    # so paint with that ABS selection and assert the gate + gcode instead.
    rep.log(f"[INFO] selected on open={selected_filament(driver, win)}")
    before = driver.capture(win).pixel(MODEL_POINT[0], MODEL_POINT[1])
    for dx, dy in ((0, 0), (-6, 0), (6, 0), (0, -6), (0, 6)):
        driver.click(win.rect.x + MODEL_POINT[0] + dx,
                     win.rect.y + MODEL_POINT[1] + dy)
        time.sleep(0.6)
    time.sleep(1.5)
    after = driver.capture(win).pixel(MODEL_POINT[0], MODEL_POINT[1])
    driver.capture(win).save_png(OUT / "painted.png")
    driver.click(win.rect.x + PAINT_ICON[0], win.rect.y + PAINT_ICON[1])
    time.sleep(1.0)
    changed = sum(abs(a - b) for a, b in zip(before, after)) > 20
    return changed, before, after


def open_prefs(driver, app, win):
    item = next((c for c in driver.controls(win)
                 if c.role == "AXMenuItem" and (c.title or "").strip()
                 in ("Settings…", "Settings...")), None)
    if item is None:
        return None
    driver.click_control(item)
    time.sleep(2.0)
    return next((w for w in driver.windows_for_pid(app.pid)
                 if w.on_screen and (w.title or "").lower() == "preferences"),
                None)


def pref_box(driver, dlg):
    txt = next((c for c in driver.controls(dlg)
                if c.role == "AXStaticText" and PREF_LABEL in
                (str(c.value) + " " + c.title).lower()), None)
    if txt is None:
        return None
    return next((c for c in driver.controls(dlg)
                 if c.role == "AXCheckBox" and c.rect
                 and abs(c.rect.center[1] - txt.rect.center[1]) < 12
                 and c.rect.x < txt.rect.x), None)


def risk_dialog(driver, app):
    return next((w for w in driver.windows_for_pid(app.pid)
                 if w.on_screen
                 and any(k in (w.title or "").lower()
                         for k in ("mixing risk", "confirm slicing"))), None)


def confirm_risk(driver, app, win, rep) -> bool:
    w = risk_dialog(driver, app)
    if w is None:
        return False
    words = recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
             w.rect.w, w.rect.h))
    confirm = next((x for x in words
                    if x.text.strip().lower() == "confirm"), None)
    rep.log(f"[INFO] risk dialog confirm={confirm.rect.to_xywh() if confirm else None}")
    if confirm is None:
        return False
    driver.click(win.rect.x + confirm.rect.center[0],
                 win.rect.y + confirm.rect.center[1])
    time.sleep(1.5)
    return True


def set_preference(driver, app, win, rep, want_on: bool):
    dlg = open_prefs(driver, app, win)
    if dlg is None:
        return False, "preferences did not open"
    box = pref_box(driver, dlg)
    if box is None:
        return False, "checkbox row not found"
    was = int(box.value or 0)
    if was != int(want_on):
        driver.click_control(box)
        time.sleep(1.5)
        confirm_risk(driver, app, win, rep)
        time.sleep(0.8)
    now = int(pref_box(driver, dlg).value or 0)
    driver.click(dlg.rect.x + 10, dlg.rect.y + 8)
    time.sleep(1.5)
    return now == int(want_on), f"{was}->{now}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    gcode = work / "m8x_125.gcode"
    roots = [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"]

    rep = Reporter(OUT)
    rep.log("=== m8x_125 macOS painted auxiliary filament gate ===")
    rep.log(f"datadir={args.datadir} model={DEFAULT_MODEL}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=DEFAULT_MODEL,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        frame.save_png(OUT / "loaded.png")
        rep.check("模型载入", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        item = driver.find_control(win, role="AXMenuItem",
                                   title="Delete All", timeout_s=3)
        rep.check("Delete All 可用", item is not None)
        if item is None:
            return rep.save({"stage": "delete"})
        driver.click_control(item)
        time.sleep(2.5)
        rep.check("添加 cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        rep.check("主材 = PLA Silk",
                  c8d.change_filament_to_silk(driver, app, win, rep) == "ok")
        row1, slot2 = select_filament_set(driver, win, rep)
        rep.log(f"[INFO] slot1 row={row1!r} slot2 row={slot2!r}")
        abs_ok = ("pla" in row1.lower() and "abs" in slot2.lower()
                  and "not visible" not in (row1 + slot2).lower())
        rep.check("#125 耗材槽 = Generic PLA + Generic ABS（高/低温）",
                  abs_ok, f"slot1={row1} slot2={slot2}")
        if not abs_ok:
            return rep.save({"stage": "abs"})
        driver.capture(win).save_png(OUT / "abs.png")

        changed, before, after = paint_auxiliary(driver, win, rep)
        rep.check("涂色 dab 落墨（辅助耗材）", changed,
                  f"px {before} -> {after}")
        if not changed:
            return rep.save({"stage": "paint"})
        time.sleep(1.0)
        teal_gate = c8c.slice_button_teal(driver, win)
        banner = c8c.banner_text(driver, win).lower()
        rep.log(f"[INFO] gated teal={teal_gate:.3f}")
        rep.check("混用门禁：Slice 置灰", teal_gate < c8c.TEAL_OFF,
                  f"teal={teal_gate:.3f}")
        rep.check("警告横幅（high/low）",
                  "high and low" in banner or
                  ("temperature" in banner and "detected" in banner),
                  banner[:160])
        driver.capture(win).save_png(OUT / "gated.png")

        # --- D/E: a gated Slice click must not start slicing --------------
        driver.click(win.rect.x + 1000, win.rect.y + 45)
        time.sleep(6.0)
        blocked = not export_gcode_enabled(driver, win)
        teal_after = c8c.slice_button_teal(driver, win)
        rep.check("门禁下点击 Slice 不启动切片",
                  blocked and teal_after < c8c.TEAL_OFF,
                  f"export={not blocked} teal={teal_after:.3f}")

        # --- F: enable the preference -------------------------------------
        ok_pref, note = set_preference(driver, app, win, rep, True)
        rep.check("打开偏好后开关 = ON", ok_pref, note)
        if not ok_pref:
            return rep.save({"stage": "pref-on"})
        time.sleep(1.0)
        teal_on = c8c.slice_button_teal(driver, win)
        rep.check("偏好放行后 Slice 高亮", teal_on > c8c.TEAL_ON,
                  f"teal={teal_on:.3f}")

        # --- G: slice, confirm the delayed risk dialog, export -----------
        if not slice_and_export(
                driver, win, rep, gcode, roots,
                on_poll=lambda: confirm_risk(driver, app, win, rep)):
            rep.check("偏好开启后切片完成", False, "slice/export failed")
            return rep.save({"stage": "slice"})
        used = mac_gcode.used_filaments(gcode.read_bytes())
        rep.log(f"[INFO] used filaments={used} size={gcode.stat().st_size}")
        rep.check("偏好开启后切片完成", True,
                  f"used={used} size={gcode.stat().st_size}")
        rep.check("gcode 同时使用主材和辅材", 1 in used and 2 in used,
                  f"used={used}")

        # --- H: restore the preference ------------------------------------
        focus_prepare(driver, win)
        ok_off, note = set_preference(driver, app, win, rep, False)
        rep.check("偏好还原为 OFF", ok_off, note)
        rep.check("app alive", app.alive())

        alive_before = app.alive()
        closed = close_app(driver, app, win)
        app = None
        rep.check("software closed", alive_before and closed,
                  f"alive_before={alive_before} closed={closed}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        exit_code = rep.save({"covered": ["#125"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
