#!/usr/bin/env python3
# m8x_208_temp_tower.py — macOS port: Feishu #208 temperature tower.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_208,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   Calibration > Temperature -> PLA defaults 230/190, step 5 disabled ->
#   OK generates the temperature tower -> it lands and is selectable -> slice
#   succeeds -> exported G-code has the 9 temperature steps 230..190 and
#   first-use order is descending.
#
# macOS mapping: "Temperature calibration" dialog (3 AXTextFields, step
# disabled), OCR OK, Slice at (1000,45), File > Export G-code... + save panel;
# the G-code is parsed for M104/M109 S values.
#
# Artifacts: artifacts/mac/pilot/m8x_208/{report.log,result.json,*.gcode}.

from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]
ENGINE = Path(__file__).resolve().parents[1]
PILOTS = Path(__file__).resolve().parent
for path in (str(HERE), str(ENGINE), str(PILOTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import ApplicationServices as AS  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import mac_calib as cal  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_208"
TOWER_TEMPS = [230, 225, 220, 215, 210, 205, 200, 195, 190]


def _copy(elem, attr):
    err, value = AS.AXUIElementCopyAttributeValue(elem, attr, None)
    return value if err == 0 else None


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
    gcode = work / "m8x_208_tower.gcode"

    rep = Reporter(OUT)
    rep.log("=== m8x_208 macOS temperature tower ===")

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
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(2.0)
        vp0 = cal.vp(driver.capture(win))

        rep.check("打开 Calibration > Temperature",
                  cal.open_calib(driver, win, "Temperature"))
        dlg = cal.window_by_title(driver, app, "Temperature calibration")
        rep.check("Temperature calibration 对话框打开", dlg is not None,
                  f"rect={dlg.rect.to_xywh() if dlg else None}")
        if dlg is None:
            raise RuntimeError("temperature dialog missing")

        fields = cal.dialog_fields(dlg)
        rep.check("Start/End/Step 字段可定位", len(fields) >= 3,
                  f"fields={len(fields)}")
        values = cal.field_values(fields, 3)
        rep.check("默认 230 / 190 / 5",
                  values == ["230", "190", "5"], f"values={values}")
        step_enabled = (bool(_copy(fields[2], AS.kAXEnabledAttribute))
                        if len(fields) >= 3 else None)
        rep.check("步长固定不可编辑（disabled）", step_enabled is False,
                  f"enabled={step_enabled}")

        rep.check("点击确定", cal.click_ok(driver, dlg))
        arrived, frame, vp1 = cal.wait_model(driver, win, vp0, delta=0.003)
        if frame is not None:
            frame.save_png(OUT / "after_ok.png")
        gone = cal.dialog_closed(driver, app, win, "Temperature calibration")
        info = cal.object_info_text(driver, win)
        rep.check("点击确定后生成温度塔模型", arrived and gone,
                  f"viewport {vp0:.4f}->{vp1:.4f} dialog_closed={gone}")
        rep.check("确定后对话框关闭", gone)
        rep.check("温度塔对象出现（对象信息面板）",
                  any(k in info.lower() for k in ("temperature", "tower")),
                  f"tail={info[-160:]!r}")

        cal.slice_plate(driver, win)
        sliced, text = cal.wait_gcode(driver, win)
        rep.check("切片成功（生成 G-code）", sliced, f"tail={text[-120:]!r}")
        rep.check("导出 G-code", cal.export_gcode(
            driver, win, gcode, search_root=HERE / "artifacts" / "mac")
            and gcode.exists(), f"size={gcode.stat().st_size if gcode.exists() else 0}")

        if not gcode.exists():
            raise RuntimeError("no exported gcode")
        temps = []
        for line in gcode.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"\s*M10[49]\b", line):
                temps.extend(int(m.group(1)) for m in
                             re.finditer(r"\bS(\d+)\b", line))
        found = {t for t in temps if t in TOWER_TEMPS}
        rep.check("gcode 含 9 档温度（230..190 步长 5）",
                  found == set(TOWER_TEMPS), f"found={sorted(found)}")
        order = []
        for t in temps:
            if t in TOWER_TEMPS and (not order or order[-1] != t):
                order.append(t)
        rep.check("温度档位按 230→190 递变",
                  order == TOWER_TEMPS, f"order={order}")

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
        exit_code = rep.save({"covered": ["#208"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
