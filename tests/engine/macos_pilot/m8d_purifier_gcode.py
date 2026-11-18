#!/usr/bin/env python3
# m8d_purifier_gcode.py — macOS port: Feishu #113/#122/#126/#127/#128
# purifier keep-warm / strong-cool gcode.
# feishu: baseline#113 baseline#122 baseline#126 baseline#127 baseline#128
#         (macOS port; corresponds to the enabled Windows m8d_purifier_gcode,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   A) a cube on PLA Silk (temperature_vitrification=45 <= 50) slices to the
#      strong-cooling branch: SET_PURIFIER_MODE MODE=1 with ALARM_TEMP=48
#      (#122 pre-state; the 45 in the old table was a typo, 48 is confirmed)
#   B) switching slot 2's preset to Generic ABS (high-temperature) flips to
#      keep-warm: MODE=3 DESIRE_TEMP=45, no ALARM_TEMP, all four params
#      present (#113/#122/#126/#128)
#   C) Generic PC also classifies as keep-warm (#127)
#
# macOS mapping:
#   fixture   -> fixtures/mixed_filament_test.3mf (5 slots; slot 1 PETG,
#                slot 2..5 Snapmaker PLA Silk)
#   scene     -> Edit > Delete All + bed right-click Add Primitive > Cube
#   remap     -> object context menu "Change Filament" -> Snapmaker PLA Silk
#                (real AXMenuItem tree, verified by PITFALLS 22.14 probe)
#   preset    -> the self-drawn sidebar combo: click slot 2 at (242,414),
#                click vendor "Generic" in the popup, then ABS/PC in the
#                submenu; read the row text back
#   slice     -> mac_common.slice_and_export (m8x_158 recipe)
#   oracle    -> mac_gcode.purifier_params / used_filaments
#
# Artifacts: artifacts/mac/pilot/m8d/{report.log,result.json,work/*.gcode,
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
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
    wait_for_model,
)
import mac_gcode  # noqa: E402
import m7b_new_project as m7b  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8d"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MODEL_POINT = (814, 396)          # canvas point that hits the cube
SLOT2_ROW_Y = 414
SEARCH_ROOTS = None                # filled in main()


def ocr_window(driver, win):
    return recognize_text(driver.capture_screen().crop(win.rect))


def menu_items(driver, app, win):
    """All (window, [(title, control)]) for on-screen popup windows."""
    out = []
    for w in driver.windows_for_pid(app.pid):
        if w.id == win.id or not w.on_screen or w.rect.area < 400:
            continue
        try:
            ctrls = [c for c in driver.controls(w) if c.role == "AXMenuItem"]
        except Exception:
            ctrls = []
        if ctrls:
            out.append((w, ctrls))
    return out


def find_menu_item(driver, app, win, needle):
    for w, ctrls in menu_items(driver, app, win):
        for c in ctrls:
            if needle in (c.title or "").lower():
                return w, c
    return None, None


def open_context_menu(driver, app, win, point):
    driver.click(win.rect.x + point[0], win.rect.y + point[1])
    time.sleep(0.6)
    driver.click(win.rect.x + point[0], win.rect.y + point[1],
                 button="right")
    time.sleep(1.0)
    return find_menu_item(driver, app, win, "change filament")


def change_filament_to_silk(driver, app, win, rep) -> str:
    """Right-click the cube, Change Filament -> Snapmaker PLA Silk."""
    w, item = open_context_menu(driver, app, win, MODEL_POINT)
    if item is None:
        # Fall back to the Objects-tree row context menu.
        words = ocr_window(driver, win)
        tab = next((x for x in words
                    if x.text.strip().lower() == "objects"), None)
        if tab is not None:
            driver.click(win.rect.x + tab.rect.center[0],
                         win.rect.y + tab.rect.center[1])
            time.sleep(1.5)
            words = ocr_window(driver, win)
            row = next((x for x in words
                        if "cube" in x.text.lower() and x.rect.y > 540), None)
            if row is not None:
                rep.log(f"[INFO] tree row fallback: {row.text!r} "
                        f"{row.rect.to_xywh()}")
                w, item = open_context_menu(
                    driver, app, win, (row.rect.center[0], row.rect.center[1]))
    if item is None:
        return "no Change Filament item"
    rep.log(f"[INFO] Change Filament item {item.title!r}")
    driver.click_control(item)
    time.sleep(1.2)
    _w, silk = find_menu_item(driver, app, win, "silk")
    if silk is None:
        return "no Silk submenu row"
    rep.log(f"[INFO] submenu Silk item {silk.title!r}")
    driver.click_control(silk)
    time.sleep(1.5)
    return "ok"


def read_slot2(driver, win) -> str:
    words = ocr_window(driver, win)
    rows = [w for w in words
            if 200 < w.rect.x < 400 and 400 <= w.rect.y <= 435]
    return " ".join(w.text for w in rows).strip()


def select_slot2_preset(driver, win, rep, type_name: str,
                        vendor_name: str = "Generic",
                        contains: bool = False) -> str:
    """Open the slot-2 combo -> vendor -> type; return the row text.

    ``vendor_name`` defaults to Generic (ABS/PC); use "Snapmaker" for the
    original PLA Silk row.  ``contains`` matches the type as a substring
    (the submenu OCR prefixes the current entry with a bullet).
    """
    words = ocr_window(driver, win)
    combo = next((w for w in words
                  if 200 < w.rect.x < 400
                  and 400 <= w.rect.y <= 435), None)
    if combo is None:
        return "slot-2 combo not found"
    rep.log(f"[INFO] click slot-2 combo {combo.text!r} "
            f"@ {combo.rect.to_xywh()}")
    driver.click(win.rect.x + combo.rect.center[0],
                 win.rect.y + combo.rect.center[1])
    time.sleep(1.2)
    words = ocr_window(driver, win)
    vendor = next((w for w in words
                   if w.text.strip().lower() == vendor_name.lower()
                   and 200 < w.rect.x < 490 and w.rect.y > 440), None)
    if vendor is None:
        rep.log(f"[INFO] vendor popup words="
                f"{[(w.text, w.rect.to_xywh()) for w in words if w.rect.y > 430][:30]}")
        return f"no {vendor_name!r} vendor entry"
    rep.log(f"[INFO] click vendor {vendor.text!r} @ {vendor.rect.to_xywh()}")
    driver.click(win.rect.x + vendor.rect.center[0],
                 win.rect.y + vendor.rect.center[1])
    time.sleep(1.0)
    words = ocr_window(driver, win)
    if contains:
        target = next((w for w in words
                       if type_name.lower() in w.text.lower()
                       and w.rect.x > 450 and w.rect.y > 430), None)
    else:
        target = next((w for w in words
                       if w.text.strip().lower() == type_name.lower()
                       and w.rect.x > 450 and w.rect.y > 430), None)
    if target is None:
        rep.log(f"[INFO] type submenu words="
                f"{[(w.text, w.rect.to_xywh()) for w in words if w.rect.x > 450 and w.rect.y > 430][:20]}")
        return f"no {type_name} entry"
    rep.log(f"[INFO] click type {target.text!r} @ {target.rect.to_xywh()}")
    driver.click(win.rect.x + target.rect.center[0],
                 win.rect.y + target.rect.center[1])
    time.sleep(2.0)
    return read_slot2(driver, win)


def slice_export(driver, win, rep, gcode: Path):
    if not slice_and_export(driver, win, rep, gcode, SEARCH_ROOTS,
                            timeout_s=240.0):
        return None
    data = gcode.read_bytes()
    return mac_gcode.purifier_params(data), mac_gcode.used_filaments(data)


def main() -> int:
    global SEARCH_ROOTS
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
    model = work / "m8d_mixed.3mf"
    shutil.copy2(DEFAULT_MODEL, model)
    g_a = work / "m8d_pla.gcode"
    g_b = work / "m8d_abs.gcode"
    g_c = work / "m8d_pc.gcode"
    SEARCH_ROOTS = [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"]

    rep = Reporter(OUT)
    rep.log("=== m8d macOS purifier gcode ===")
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
        rep.check("添加 cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)

        result = change_filament_to_silk(driver, app, win, rep)
        rep.check("cube 换槽 PLA Silk（Change Filament）", result == "ok",
                  result)
        if result != "ok":
            return rep.save({"stage": "change-filament"})

        pa = slice_export(driver, win, rep, g_a)
        if pa is None:
            rep.check("A 态切片导出（PLA Silk）", False, "slice/export failed")
            return rep.save({"stage": "slice-a"})
        params_a, used_a = pa
        rep.log(f"[INFO] A params={params_a} used={used_a}")
        rep.check("A 态切片导出（PLA Silk）", True,
                  f"size={g_a.stat().st_size}")
        rep.check("cube 在 2 号槽（PLA Silk）", used_a == [2],
                  f"used={used_a}")
        rep.check("#122 强冷 MODE=1", bool(params_a)
                  and params_a.get("MODE") == "1", f"params={params_a}")
        rep.check("#122 强冷 ALARM_TEMP=48", bool(params_a)
                  and params_a.get("ALARM_TEMP") == "48",
                  f"params={params_a}")

        row_abs = select_slot2_preset(driver, win, rep, "ABS")
        rep.log(f"[INFO] slot-2 row after ABS={row_abs!r}")
        rep.check("slot2 -> Generic ABS", "abs" in row_abs.lower(), row_abs)
        if "abs" not in row_abs.lower():
            return rep.save({"stage": "select-abs"})
        pb = slice_export(driver, win, rep, g_b)
        if pb is None:
            rep.check("B 态切片导出（ABS）", False, "slice/export failed")
            return rep.save({"stage": "slice-b"})
        params_b, _used_b = pb
        rep.log(f"[INFO] B params={params_b}")
        rep.check("B 态切片导出（ABS）", True,
                  f"size={g_b.stat().st_size}")
        rep.check("#113/#122 强冷/保温翻转（1 -> 3）", bool(params_a)
                  and bool(params_b)
                  and params_a.get("MODE") == "1"
                  and params_b.get("MODE") == "3",
                  f"A={params_a} B={params_b}")
        rep.check("#113 保温 DESIRE_TEMP=45", bool(params_b)
                  and params_b.get("DESIRE_TEMP") == "45",
                  f"params={params_b}")
        rep.check("#113 无 ALARM_TEMP", bool(params_b)
                  and params_b.get("ALARM_TEMP") is None,
                  f"params={params_b}")
        rep.check("#128 四个参数齐全", bool(params_b) and all(
            params_b.get(k) is not None
            for k in ("MODE", "DESIRE_TEMP", "FAN_SPEED", "DELAY_OFF")),
            f"params={params_b}")

        row_pc = select_slot2_preset(driver, win, rep, "PC")
        rep.log(f"[INFO] slot-2 row after PC={row_pc!r}")
        rep.check("slot2 -> Generic PC",
                  "pc" in row_pc.lower() and "abs" not in row_pc.lower(),
                  row_pc)
        if "pc" in row_pc.lower() and "abs" not in row_pc.lower():
            pc = slice_export(driver, win, rep, g_c)
            if pc is not None:
                params_c, _used_c = pc
                rep.log(f"[INFO] C params={params_c}")
                rep.check("#127 PC 保温", bool(params_c)
                          and params_c.get("MODE") == "3"
                          and params_c.get("DESIRE_TEMP") == "45",
                          f"params={params_c}")
            else:
                rep.check("#127 PC 保温", False, "slice/export failed")

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
        exit_code = rep.save({"covered": ["#113", "#122", "#126",
                                          "#127", "#128"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
