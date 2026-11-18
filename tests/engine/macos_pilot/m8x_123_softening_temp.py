#!/usr/bin/env python3
# m8x_123_softening_temp.py — macOS port: Feishu #123 softening temperature
# changes the temperature class and the purifier gcode.
# feishu: baseline#123  (macOS port; corresponds to the enabled Windows
#         m8x_123_softening_temp, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   A) vitrification 45 -> strong cooling (MODE=1 + ALARM_TEMP=45 in the old
#      case text; the 2.4.2 template actually writes ALARM_TEMP=48 — the
#      Windows 2.4.2 check confirmed 48, so this is the current baseline)
#   B) vitrification 80 -> keep-warm (MODE=3 + DESIRE_TEMP=45, no ALARM)
#   A != B: the softening temperature really flips the classifier/gcode
#
# macOS mapping:
#   entry  -> filament row menu (196,418) -> Edit (198,446) opens the
#             'Material settings' window (AXTextFields; Softening is the
#             field at x<900, 300<=y<=340)
#   commit -> AXSetValue + AXConfirm on the field (AXSetValue alone changes
#             only the AX value; AXConfirm fires the wx change event).  The
#             dialog is a live project override — no Save-Filament-as needed.
#   close  -> real click on the red close button; slice with the override.
#   oracle -> '; temperature_vitrification' and mac_gcode.purifier_params.
#
# Artifacts: artifacts/mac/pilot/m8x_123/{report.log,result.json,
#            work/*.gcode,*.png}.

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

import ApplicationServices as AS  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos import _ax_perform, _ax_set  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
    wait_for_model,
)
import mac_gcode  # noqa: E402
import m7b_new_project as m7b  # noqa: E402
import m8f_nozzle_flow as c8f  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_123"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def open_material_settings(driver, app, win):
    driver.click(win.rect.x + 196, win.rect.y + 418)
    time.sleep(1.0)
    driver.click(win.rect.x + 198, win.rect.y + 446)
    time.sleep(2.0)
    for w in driver.windows_for_pid(app.pid):
        if w.on_screen and "material settings" in (w.title or "").lower():
            return w
    return None


def vitr_field(driver, dlg):
    for c in driver.controls(dlg):
        if (c.role == "AXTextField" and c.rect is not None
                and c.rect.x < 900 and 300 <= c.rect.y <= 340):
            return c
    return None


def set_softening(driver, dlg, value: str, rep) -> str:
    fld = vitr_field(driver, dlg)
    if fld is None or fld.handle is None:
        return "field not found"
    rep.log(f"[INFO] softening before={fld.value!r} actions={fld.actions}")
    _ax_set(fld.handle, AS.kAXValueAttribute, value)
    time.sleep(0.4)
    if "AXConfirm" in (fld.actions or ()):
        _ax_perform(fld.handle, "AXConfirm")
    time.sleep(1.0)
    fld2 = vitr_field(driver, dlg)
    after = str(fld2.value) if fld2 is not None else None
    rep.log(f"[INFO] softening after={after!r}")
    return after or ""


def close_dialog(driver, app, win, dlg) -> bool:
    driver.click(dlg.rect.x + 10, dlg.rect.y + 8)
    time.sleep(1.5)
    return not any(
        w.on_screen and "material settings" in (w.title or "").lower()
        for w in driver.windows_for_pid(win.pid))


def vitr_line(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^; temperature_vitrification = (.*)$", text, re.M)
    return m.group(1).strip() if m else None


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
    model = work / "m8x_123_mixed.3mf"
    shutil.copy2(DEFAULT_MODEL, model)
    g_a = work / "m8x_123_vitr45.gcode"
    g_b = work / "m8x_123_vitr80.gcode"

    rep = Reporter(OUT)
    rep.log("=== m8x_123 macOS softening temperature -> purifier class ===")
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

        roots = [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"]

        # ---------- A: softening 45 -> strong cooling ----------------------
        dlg = open_material_settings(driver, app, win)
        rep.check("A 打开 Material settings", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({"stage": "dialog-a"})
        val = set_softening(driver, dlg, "45", rep)
        rep.check("A 软化温度设为 45", val == "45", f"readback={val!r}")
        rep.check("A 关闭编辑器", close_dialog(driver, app, win, dlg))
        if not slice_and_export(driver, win, rep, g_a, roots):
            rep.check("A 切片并导出", False, "slice/export failed")
            return rep.save({"stage": "slice-a"})
        vitr_a = vitr_line(g_a)
        pa = mac_gcode.purifier_params(g_a.read_bytes())
        rep.log(f"[INFO] A vitr={vitr_a} purifier={pa}")
        rep.check("A 软化温度进入 gcode（槽 1 = 45）",
                  vitr_a is not None and vitr_a.split(",")[0].strip() == "45",
                  f"vitr={vitr_a}")
        rep.check("A 强冷 MODE=1", bool(pa) and pa.get("MODE") == "1",
                  f"params={pa}")
        rep.check("A 强冷 ALARM_TEMP=48（2.4.2 当前值）",
                  bool(pa) and pa.get("ALARM_TEMP") == "48",
                  f"params={pa}")

        # ---------- B: softening 80 -> keep-warm ---------------------------
        rep.check("回到 Prepare 页", c8f.prepare_tab(driver, win))
        dlg2 = open_material_settings(driver, app, win)
        rep.check("B 重新打开 Material settings", dlg2 is not None)
        if dlg2 is None:
            return rep.save({"stage": "dialog-b"})
        val2 = set_softening(driver, dlg2, "80", rep)
        rep.check("B 软化温度设为 80", val2 == "80", f"readback={val2!r}")
        rep.check("B 关闭编辑器", close_dialog(driver, app, win, dlg2))
        if not slice_and_export(driver, win, rep, g_b, roots):
            rep.check("B 切片并导出", False, "slice/export failed")
            return rep.save({"stage": "slice-b"})
        vitr_b = vitr_line(g_b)
        pb = mac_gcode.purifier_params(g_b.read_bytes())
        rep.log(f"[INFO] B vitr={vitr_b} purifier={pb}")
        rep.check("B 软化温度进入 gcode（槽 1 = 80）",
                  vitr_b is not None and vitr_b.split(",")[0].strip() == "80",
                  f"vitr={vitr_b}")
        rep.check("B 保温 MODE=3", bool(pb) and pb.get("MODE") == "3",
                  f"params={pb}")
        rep.check("B 保温 DESIRE_TEMP=45", bool(pb)
                  and pb.get("DESIRE_TEMP") == "45", f"params={pb}")
        rep.check("B 无 ALARM_TEMP", bool(pb)
                  and pb.get("ALARM_TEMP") is None, f"params={pb}")
        rep.check("A/B 分类确实翻转（强冷 -> 保温）",
                  bool(pa) and bool(pb) and pa.get("MODE") != pb.get("MODE"),
                  f"A={pa} B={pb}")

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
        exit_code = rep.save({"covered": ["#123"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
