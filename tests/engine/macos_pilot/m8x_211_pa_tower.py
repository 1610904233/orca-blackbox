#!/usr/bin/env python3
# m8x_211_pa_tower.py — macOS port: Feishu #211 default PA tower.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_211,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   Calibration > Pressure advance -> defaults 0 / 0.1 / 0.002; Print numbers
#   unchecked; Accelerations/Speeds disabled and empty -> OK generates the PA
#   tower (lands on the plate, selectable) -> slice succeeds without errors.
#
# macOS mapping:
#   dialog  -> "PA Calibration": 3 enabled AXTextFields, 1 AXCheckBox
#              (Print numbers), 2 disabled AXTextFields (Accel/Speed).
#   OK      -> OCR "OK" + real click (AX buttons are Not OK on this dialog).
#   model   -> viewport rises; object info panel shows tower_with_seam.stl.
#   slice   -> Slice button at (1000,45); completion detected by G-code text
#              ("stop printing object ..." / WIPE_START) in the window OCR.
#
# Artifacts: artifacts/mac/pilot/m8x_211/{report.log,result.json,*.png}.

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

import ApplicationServices as AS  # noqa: E402

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import (  # noqa: E402
    joined_text, recognize_text,
)
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import m7b_new_project as m7b  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_211"
SLICE_XY = (1000, 45)
COLORED_GATE = 0.0025
OBJ_TAIL = "tower_with_seam"


def _copy(elem, attr):
    err, value = AS.AXUIElementCopyAttributeValue(elem, attr, None)
    return value if err == 0 else None


def _role(elem):
    value = _copy(elem, AS.kAXRoleAttribute)
    return value if isinstance(value, str) else ""


def walk(root, max_depth=12):
    stack = [(root, 0)]
    seen = set()
    keep = [root]
    while stack:
        elem, depth = stack.pop()
        key = id(elem)
        if key in seen:
            continue
        seen.add(key)
        yield elem, depth
        if depth >= max_depth:
            continue
        children = _copy(elem, AS.kAXChildrenAttribute)
        if children:
            keep.extend(children)
            for child in reversed(list(children)):
                stack.append((child, depth + 1))


def window_by_title(driver, app, needle, timeout_s=6.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for w in driver.windows_for_pid(app.pid):
            if w.on_screen and needle.lower() in (w.title or "").lower():
                if w.handle is None:
                    driver._attach_ax_window(w)
                return w
        time.sleep(0.3)
    return None


def open_pa(driver, win) -> bool:
    calib = next((c for c in driver.controls(win, max_depth=12)
                  if c.role == "AXMenuBarItem"
                  and c.title.strip().lower() == "calibration"), None)
    if calib is None or not driver.click_control(calib):
        return False
    time.sleep(0.8)
    row = next((c for c in driver.controls(win, max_depth=14)
                if c.role == "AXMenuItem"
                and "pressure advance" in c.title.lower()), None)
    return bool(row is not None and driver.click_control(row))


def click_ok(driver, dlg) -> bool:
    words = recognize_text(driver.capture_screen().crop(dlg.rect))
    ok = next((w for w in words if w.text.strip().lower() == "ok"), None)
    if ok is None:
        return False
    driver.click(dlg.rect.x + ok.rect.center[0],
                 dlg.rect.y + ok.rect.center[1])
    return True


def wait_gcode(driver, win, timeout_s=90.0):
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        last = joined_text(recognize_text(
            driver.capture_screen().crop(win.rect)))
        low = last.lower()
        if ("stop printing object" in low or "wipe_start" in low
                or "wipe start" in low):
            return True, last
        time.sleep(2.0)
    return False, last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    rep = Reporter(OUT)
    rep.log("=== m8x_211 macOS default PA tower ===")
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
                  f"blockers={app.extra.get('blockers')}")
        time.sleep(2.0)
        vp0 = m7b._vp_colored(driver.capture(win))
        rep.log(f"[INFO] empty bed={vp0:.4f}")

        rep.check("打开 Calibration > Pressure advance", open_pa(driver, win))
        dlg = window_by_title(driver, app, "PA Calibration")
        rep.check("PA Calibration 对话框打开", dlg is not None,
                  f"rect={dlg.rect.to_xywh() if dlg else None}")
        if dlg is None:
            raise RuntimeError("PA dialog missing")

        fields = [e for e, _d in walk(dlg.handle)
                  if _role(e) == "AXTextField"]
        checkboxes = [e for e, _d in walk(dlg.handle)
                      if _role(e) == "AXCheckBox"]
        rep.check("Start/End/Step/Accel/Speed 字段可定位",
                  len(fields) >= 5, f"fields={len(fields)}")
        values = [str(_copy(f, AS.kAXValueAttribute)) for f in fields[:3]]
        rep.check("默认 0 / 0.1 / 0.002", values == ["0", "0.1", "0.002"],
                  f"values={values}")

        pn = checkboxes[0] if checkboxes else None
        pn_value = _copy(pn, AS.kAXValueAttribute) if pn is not None else None
        rep.check("Print numbers 未勾选",
                  pn is not None and not bool(pn_value),
                  f"checkbox value={pn_value!r}")

        accel_speed = fields[3:5] if len(fields) >= 5 else []
        disabled_empty = all(
            not bool(_copy(f, AS.kAXEnabledAttribute))
            and str(_copy(f, AS.kAXValueAttribute) or "") == ""
            for f in accel_speed)
        rep.check("加速度/速度灰置且为空（DDE+PA Tower 默认态）",
                  len(accel_speed) == 2 and disabled_empty,
                  f"states={[(bool(_copy(f, AS.kAXEnabledAttribute)), _copy(f, AS.kAXValueAttribute)) for f in accel_speed]}")

        rep.check("点击确定", click_ok(driver, dlg))
        time.sleep(4.0)
        gone = window_by_title(driver, app, "PA Calibration", timeout_s=2.0) is None
        vp1 = m7b._vp_colored(driver.capture(win))
        frame1 = driver.capture(win)
        frame1.save_png(OUT / "after_ok.png")
        text1 = joined_text(recognize_text(
            driver.capture_screen().crop(win.rect)))
        rep.check("点击确定后生成 PA 塔模型",
                  gone and vp1 > vp0 + 0.005,
                  f"dialog_closed={gone} viewport {vp0:.4f}->{vp1:.4f}")
        rep.check("确定后对话框关闭", gone)

        info_ok = OBJ_TAIL in text1.lower()
        rep.check("PA 塔对象出现（对象信息面板）", info_ok,
                  f"object={OBJ_TAIL!r} tail={text1[-160:]!r}")

        # Selectability: clear via the Outside row, then click the tower row.
        outside = next((w for w in recognize_text(
            driver.capture_screen().crop(win.rect))
            if w.text.strip().lower() == "outside"), None)
        selected_again = False
        if outside is not None:
            driver.click(win.rect.x + outside.rect.center[0],
                         win.rect.y + outside.rect.center[1])
            time.sleep(1.0)
            row = next((w for w in recognize_text(
                driver.capture_screen().crop(win.rect))
                if OBJ_TAIL in w.text.lower()), None)
            if row is not None:
                driver.click(win.rect.x + row.rect.center[0],
                             win.rect.y + row.rect.center[1])
                time.sleep(1.0)
                text2 = joined_text(recognize_text(
                    driver.capture_screen().crop(win.rect)))
                selected_again = OBJ_TAIL in text2.lower()
        rep.check("PA 塔对象行可单独选中",
                  info_ok and (selected_again or outside is None),
                  f"outside={outside is not None} reselect={selected_again}")

        driver.click(win.rect.x + SLICE_XY[0], win.rect.y + SLICE_XY[1])
        sliced, text3 = wait_gcode(driver, win)
        rep.check("切片成功（生成 G-code）", sliced,
                  f"tail={text3[-160:]!r}")

        rep.check("app alive", app.alive())
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None and not args.keep:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        elif app is not None:
            rep.log(f"[INFO] --keep: app pid={app.pid} left running")
        exit_code = rep.save({"covered": ["#211"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
