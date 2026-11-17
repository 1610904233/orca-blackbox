#!/usr/bin/env python3
# m8x_213_max_flow.py — macOS port: Feishu #213 max volumetric speed test.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_213,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions: Calibration > Max flowrate -> defaults 5 / 20 / 0.5
# -> (a STEP-import-parameters dialog may appear; accept defaults) -> the test
# model lands and is selectable -> slice succeeds.
#
# macOS mapping: "Max volumetric speed test" dialog (3 AXTextFields), OCR OK,
# optional import-parameters dialog accepted, Slice at (1000,45).
#
# Artifacts: artifacts/mac/pilot/m8x_213/{report.log,result.json,*.png}.

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

OUT = ARTIFACTS / "pilot" / "m8x_213"
OBJ_KEYWORD = "volumetric"


def accept_import_dialog(driver, app, win, dlg, rep):
    """Accept a possible 'Step file import parameters' dialog."""
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        extras = [w for w in driver.windows_for_pid(app.pid)
                  if w.on_screen and w.id not in (win.id, dlg.id)
                  and w.rect.area > 500]
        for w in extras:
            if w.handle is None:
                driver._attach_ax_window(w)
            text = cal.object_info_text(driver, w)
            rep.log(f"[INFO] extra dialog {w.title!r}: {text[:160]!r}")
            words = __import__("harness.platform.macos_ocr", fromlist=["recognize_text"]) \
                .recognize_text(driver.capture_screen().crop(w.rect))
            label = next((x for x in words
                          if x.text.strip().lower() in ("ok", "import",
                                                        "continue")), None)
            if label is not None:
                driver.click(w.rect.x + label.rect.center[0],
                             w.rect.y + label.rect.center[1])
                time.sleep(1.5)
                return w.title or "<untitled>"
        time.sleep(0.5)
    return None


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
    rep.log("=== m8x_213 macOS max volumetric speed ===")

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

        rep.check("打开 Calibration > Max flowrate",
                  cal.open_calib(driver, win, "Max flowrate"))
        dlg = cal.window_by_title(driver, app, "Max volumetric speed")
        rep.check("Max volumetric speed test 对话框打开", dlg is not None,
                  f"rect={dlg.rect.to_xywh() if dlg else None}")
        if dlg is None:
            raise RuntimeError("max-flow dialog missing")

        fields = cal.dialog_fields(dlg)
        rep.check("Start/End/Step 字段可定位", len(fields) >= 3,
                  f"fields={len(fields)}")
        values = cal.field_values(fields, 3)
        rep.check("默认 5 / 20 / 0.5", values == ["5", "20", "0.5"],
                  f"values={values}")

        rep.check("点击确定", cal.click_ok(driver, dlg))
        accepted = accept_import_dialog(driver, app, win, dlg, rep)
        rep.check("STEP 导入参数对话框（接受默认）", True,
                  f"dialog={accepted!r} (none means not needed)")

        arrived, frame, vp1 = cal.wait_model(driver, win, vp0, delta=0.003)
        if frame is not None:
            frame.save_png(OUT / "after_ok.png")
        gone = cal.dialog_closed(driver, app, win, "Max volumetric speed")
        info = cal.object_info_text(driver, win)
        rep.check("点击确定后生成最大体积流量测试件", arrived and gone,
                  f"viewport {vp0:.4f}->{vp1:.4f} dialog_closed={gone}")
        rep.check("确定后对话框关闭", gone)
        rep.check("测试件对象出现（对象信息面板）",
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
        exit_code = rep.save({"covered": ["#213"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
