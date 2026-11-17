#!/usr/bin/env python3
# m8x_212_retraction.py — macOS port: Feishu #212 default retraction test.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_212,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions: Calibration > Retraction test -> defaults 0 / 2 / 0.1
# -> OK loads the retraction tower -> it lands on the plate and is selectable
# -> slice succeeds.
#
# macOS mapping: "Retraction test" dialog (3 AXTextFields), OCR OK, Slice at
# (1000,45); the object info panel names the generated model and G-code text
# proves the slice.
#
# Artifacts: artifacts/mac/pilot/m8x_212/{report.log,result.json,*.png}.

from __future__ import annotations

import argparse
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
import mac_calib as cal  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_212"
OBJ_KEYWORD = "retraction_tower"


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
    rep.log("=== m8x_212 macOS retraction test ===")

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
        rep.log(f"[INFO] empty bed={vp0:.4f}")

        rep.check("打开 Calibration > Retraction test",
                  cal.open_calib(driver, win, "Retraction test"))
        dlg = cal.window_by_title(driver, app, "Retraction test")
        rep.check("Retraction test 对话框打开", dlg is not None,
                  f"rect={dlg.rect.to_xywh() if dlg else None}")
        if dlg is None:
            raise RuntimeError("retraction dialog missing")

        fields = cal.dialog_fields(dlg)
        rep.check("Start/End/Step 字段可定位", len(fields) >= 3,
                  f"fields={len(fields)}")
        values = cal.field_values(fields, 3)
        rep.check("默认 0 / 2 / 0.1", values == ["0", "2", "0.1"],
                  f"values={values}")

        rep.check("点击确定", cal.click_ok(driver, dlg))
        arrived, frame, vp1 = cal.wait_model(driver, win, vp0, delta=0.003)
        if frame is not None:
            frame.save_png(OUT / "after_ok.png")
        gone = cal.dialog_closed(driver, app, win, "Retraction test")
        info = cal.object_info_text(driver, win)
        if "non-manifold" in info.lower():
            rep.log("[INFO] app reported non-manifold edges on the template "
                    "(model still loads and slices)")
        rep.check("点击确定后生成回抽测试塔", arrived and gone,
                  f"viewport {vp0:.4f}->{vp1:.4f} dialog_closed={gone}")
        rep.check("确定后对话框关闭", gone)
        rep.check("回抽测试塔对象出现（对象信息面板）",
                  OBJ_KEYWORD in info.lower(), f"tail={info[-160:]!r}")

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
        exit_code = rep.save({"covered": ["#212"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
