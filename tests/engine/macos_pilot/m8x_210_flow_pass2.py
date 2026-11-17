#!/usr/bin/env python3
# m8x_210_flow_pass2.py — macOS port: Feishu #210 flow-rate Pass 2.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_209,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions: Calibration > Flow rate > Pass 2 loads a 10-block
# pyramid with no parameter dialog; object names are flowrate_0 + m1..m9;
# model lands and a visible object row is selectable; slice succeeds.
#
# macOS mapping: the Flow rate submenu items are AXMenuItems (AXPress works);
# object names come from the saved project's model_settings; Slice at
# (1000,45).
#
# Artifacts: artifacts/mac/pilot/m8x_209/{report.log,result.json,work/*.3mf}.

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

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import mac_3mf  # noqa: E402
import mac_calib as cal  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_210"


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
    proj = work / "m8x_210.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_210 macOS flow-rate Pass 2 ===")

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

        rep.check("Calibration > Flow rate > Pass 2",
                  cal.open_calib(driver, win, "Pass 2"))
        # No parameter dialog: the 9 blocks load directly.
        extras = [w for w in driver.windows_for_pid(app.pid)
                  if w.on_screen and w.id != win.id
                  and (w.title or "").strip()
                  and w.rect.area > 5000]
        rep.check("Pass 2 加载校准件（无参数弹窗）", not extras,
                  f"windows={[(w.title, w.rect.to_xywh()) for w in extras]}")

        arrived, frame, vp1 = cal.wait_model(driver, win, vp0, delta=0.01)
        if frame is not None:
            frame.save_png(OUT / "after_load.png")
        rep.check("10 块模型落板（彩色占比上升）", arrived,
                  f"viewport {vp0:.4f}->{vp1:.4f}")
        if not arrived:
            raise RuntimeError("Pass 2 models did not load")

        rep.check("项目另存（供对象名解析）",
                  cal.save_project_anywhere(
                      driver, win, proj,
                      search_root=HERE / "artifacts" / "mac")
                  and proj.exists())
        names = mac_3mf.object_names(proj) if proj.exists() else []
        rep.log(f"[INFO] objects={names}")
        flow_names = [n for n in names if "flowrate" in n.lower()]
        neg = sorted(n.lower() for n in flow_names if "_m" in n.lower())
        rep.check("3mf 对象名恰为 10 档（flowrate_0 + m1~m9）",
                  len(flow_names) == 10
                  and any(n.lower() == "flowrate_0" for n in flow_names)
                  and len(neg) == 9,
                  f"names={names}")

        # Switch the left panel to the Objects tab, then look for the rows.
        words = __import__("harness.platform.macos_ocr",
                           fromlist=["recognize_text"]).recognize_text(
            driver.capture_screen().crop(win.rect))
        tab = next((w for w in words if w.text.strip() == "Objects"), None)
        if tab is not None:
            driver.click(win.rect.x + tab.rect.center[0],
                         win.rect.y + tab.rect.center[1])
            time.sleep(1.2)
        info = cal.object_info_text(driver, win)
        has_rows = "flowrate" in info.lower()
        rep.check("对象列表可见 flowrate_* 行（UI 证据）", has_rows,
                  f"tail={info[-200:]!r}")
        if has_rows:
            words = __import__("harness.platform.macos_ocr",
                               fromlist=["recognize_text"]).recognize_text(
                driver.capture_screen().crop(win.rect))
            row = next((w for w in words
                        if w.text.strip().lower().startswith("flowrate")), None)
            if row is not None:
                driver.click(win.rect.x + row.rect.center[0],
                             win.rect.y + row.rect.center[1])
                time.sleep(1.0)
                info2 = cal.object_info_text(driver, win)
                rep.check("可见对象行可单独选中",
                          row.text.strip().lower() in info2.lower(),
                          f"row={row.text!r} tail={info2[-160:]!r}")
            else:
                rep.check("可见对象行可单独选中", False, "no flowrate row")

        cal.slice_plate(driver, win)
        sliced, text = cal.wait_gcode(driver, win)
        rep.check("切片成功（生成 G-code）", sliced, f"tail={text[-160:]!r}")
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
        exit_code = rep.save({"covered": ["#210"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
