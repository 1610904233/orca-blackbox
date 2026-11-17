#!/usr/bin/env python3
# m8x_218_temp_defaults.py — macOS port: Feishu #218 temperature-tower defaults.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_218,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   Calibration > Temperature -> switch filament type through ABS/ASA, PETG,
#   PCTG, TPU, PA-CF, PET-CF -> read Start/End defaults (exact, no residue);
#   PLA/Custom = 230/190; Temp step is fixed 5 and disabled; every range is
#   sane (start<=350, end>=170, end<=start-5).  No model is generated.
#
# macOS mapping:
#   dialog      -> "Temperature calibration" (246x376); the three AXTextFields
#                  are Start temp / End temp / Temp step.
#   type switch -> self-drawn radio grid; click by calibrated dialog-relative
#                  positions (AX exposes no radio titles/rects).
#
# Artifacts: artifacts/mac/pilot/m8x_218/{report.log,result.json,*.png}.

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

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)

OUT = ARTIFACTS / "pilot" / "m8x_218"
# dialog-relative centres of the self-drawn radio grid
TYPES = (
    ("PLA", (60, 78)),
    ("ABS/ASA", (145, 78)),
    ("PETG", (58, 106)),
    ("PCTG", (135, 106)),
    ("TPU", (46, 134)),
    ("PA-CF", (136, 135)),
    ("PET-CF", (55, 162)),
    ("Custom", (149, 162)),
)
EXPECTED = {
    "PLA": ("230", "190"),
    "ABS/ASA": ("270", "230"),
    "PETG": ("250", "230"),
    "PCTG": ("280", "240"),
    "TPU": ("240", "210"),
    "PA-CF": ("320", "280"),
    "PET-CF": ("320", "280"),
    "Custom": ("230", "190"),
}


def _copy(elem, attr):
    err, value = AS.AXUIElementCopyAttributeValue(elem, attr, None)
    return value if err == 0 else None


def _role(elem):
    value = _copy(elem, AS.kAXRoleAttribute)
    return value if isinstance(value, str) else ""


def walk(root, max_depth=14):
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


def dialog_by_title(driver, app, needle, timeout_s=8.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for w in driver.windows_for_pid(app.pid):
            if w.on_screen and needle.lower() in (w.title or "").lower():
                if w.handle is None:
                    driver._attach_ax_window(w)
                return w
        time.sleep(0.3)
    return None


def fields(dlg):
    return [e for e, _d in walk(dlg.handle) if _role(e) == "AXTextField"]


def read_fields(dlg):
    out = []
    for f in fields(dlg)[:3]:
        value = _copy(f, AS.kAXValueAttribute)
        out.append(str(value) if value is not None else "")
    return out


def open_temperature(driver, win) -> bool:
    calib = next((c for c in driver.controls(win, max_depth=12)
                  if c.role == "AXMenuBarItem"
                  and c.title.strip().lower() == "calibration"), None)
    if calib is None or not driver.click_control(calib):
        return False
    time.sleep(0.8)
    row = next((c for c in driver.controls(win, max_depth=14)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("temperature")), None)
    return bool(row is not None and driver.click_control(row))


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
    rep.log("=== m8x_218 macOS temperature-tower defaults ===")
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

        rep.check("打开 Calibration > Temperature", open_temperature(driver, win))
        dlg = dialog_by_title(driver, app, "Temperature calibration")
        rep.check("Temperature calibration 对话框打开", dlg is not None,
                  f"rect={dlg.rect.to_xywh() if dlg else None}")
        if dlg is None:
            raise RuntimeError("temperature dialog missing")
        driver.capture_screen().crop(dlg.rect).save_png(OUT / "dialog.png")

        initial = read_fields(dlg)
        rep.check("PLA 默认 230/190", tuple(initial[:2]) == ("230", "190"),
                  f"fields={initial}")

        seen: dict[str, tuple[str, str]] = {}
        for name, (cx, cy) in TYPES:
            driver.click(dlg.rect.x + cx, dlg.rect.y + cy)
            time.sleep(0.8)
            vals = read_fields(dlg)
            seen[name] = (vals[0], vals[1]) if len(vals) >= 2 else ("", "")
            rep.log(f"[INFO] {name}: fields={vals}")

        six = ("ABS/ASA", "PETG", "PCTG", "TPU", "PA-CF", "PET-CF")
        bad = {k: seen.get(k) for k in six if seen.get(k) != EXPECTED[k]}
        rep.check("六组默认值逐组精确（无残留）", not bad, f"bad={bad}")
        rep.check("PLA/Custom 默认 230/190",
                  seen.get("PLA") == EXPECTED["PLA"]
                  and seen.get("Custom") == EXPECTED["Custom"],
                  f"PLA={seen.get('PLA')} Custom={seen.get('Custom')}")

        step_fields = fields(dlg)
        step_val = (str(_copy(step_fields[2], AS.kAXValueAttribute))
                    if len(step_fields) >= 3 else "")
        step_enabled = (_copy(step_fields[2], AS.kAXEnabledAttribute)
                        if len(step_fields) >= 3 else None)
        rep.check("步长固定 5 且不可编辑",
                  step_val == "5" and not step_enabled,
                  f"value={step_val!r} enabled={step_enabled}")

        range_bad = []
        for name, (start, end) in seen.items():
            try:
                s, e = int(start), int(end)
            except ValueError:
                range_bad.append(name)
                continue
            if not (s <= 350 and e >= 170 and e <= s - 5):
                range_bad.append(name)
        rep.check("区间校验（start<=350, end>=170, end<=start-5）",
                  not range_bad, f"bad={range_bad}")

        # Close the dialog without generating a model.
        driver.send_key("escape")
        time.sleep(1.0)
        gone = dialog_by_title(driver, app, "Temperature calibration",
                               timeout_s=2.0) is None
        rep.check("对话框可关闭", gone)
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
        exit_code = rep.save({"covered": ["#218"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
