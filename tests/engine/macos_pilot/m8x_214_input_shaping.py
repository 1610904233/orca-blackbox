#!/usr/bin/env python3
# m8x_214_input_shaping.py — macOS port: Feishu #214 input shaping frequency.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_214,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions: Calibration > Input Shaping > Input Shaping Frequency ->
# X/Y defaults 15~110 Hz, Damp 0.150 -> test-model choice (Ringing/Fast Tower)
# -> OK generates the sweep test model -> it lands and is selectable -> slice.
#
# macOS mapping: "Input shaping Frequency test" dialog (5 AXTextFields), the
# two model radios are drawn (OCR labels), OCR OK, optional STEP-import dialog
# accepted via the m8x_213 helper, Slice at (1000,45).
#
# Artifacts: artifacts/mac/pilot/m8x_214/{report.log,result.json,*.png}.

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
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import mac_calib as cal  # noqa: E402
import m8x_213_max_flow as c213  # noqa: E402
import m7b_new_project as m7b  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_214"
OBJ_KEYWORDS = ("input_shaping", "ringing", "shaping")


def _dialog_by_title(driver, app, main_win, needle, timeout_s=6.0):
    """Separate dialog window; the main window title can also match."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for w in driver.windows_for_pid(app.pid):
            if w.id == main_win.id or not w.on_screen:
                continue
            if needle.lower() in (w.title or "").lower():
                return w
        time.sleep(0.3)
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
    rep.log("=== m8x_214 macOS input shaping frequency ===")

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

        rep.check("打开 Calibration > Input Shaping Frequency",
                  cal.open_calib(driver, win, "Input Shaping Frequency"))
        dlg = cal.window_by_title(driver, app, "Input shaping Frequency")
        rep.check("输入整形频率弹窗打开", dlg is not None,
                  f"rect={dlg.rect.to_xywh() if dlg else None}")
        if dlg is None:
            raise RuntimeError("input shaping dialog missing")

        fields = cal.dialog_fields(dlg)
        rep.check("X/Y/Damp 字段可定位", len(fields) >= 5,
                  f"fields={len(fields)}")
        values = cal.field_values(fields, 5)
        rep.check("默认 X/Y 15~110Hz + 阻尼 0.15",
                  values == ["15", "110", "15", "110", "0.150"],
                  f"values={values}")

        words = recognize_text(driver.capture_screen().crop(dlg.rect))
        labels = {w.text.strip() for w in words}
        has_both = (any("ringing" in t.lower() for t in labels)
                    and any("fast" in t.lower() and "tower" in t.lower()
                            for t in labels))
        rep.check("测试模型二选（Ringing/Fast Tower）", has_both,
                  f"labels={sorted(labels)}")

        rep.check("点击确定", cal.click_ok(driver, dlg))
        accepted = c213.accept_import_dialog(driver, app, win, dlg, rep)
        rep.log(f"[INFO] import dialog={accepted!r}")

        arrived, frame, vp1 = cal.wait_model(driver, win, vp0, delta=0.003)
        if frame is not None:
            frame.save_png(OUT / "after_ok.png")
        gone = cal.dialog_closed(driver, app, win,
                                 "Input shaping Frequency")
        info = cal.object_info_text(driver, win)
        rep.check("点击确定后生成扫频测试件", arrived and gone,
                  f"viewport {vp0:.4f}->{vp1:.4f} dialog_closed={gone}")
        rep.check("确定后弹窗关闭", gone)
        rep.check("扫频测试件对象出现（对象信息面板）",
                  any(k in info.lower() for k in OBJ_KEYWORDS),
                  f"tail={info[-160:]!r}")
        rep.check("默认选中 Ringing Tower（生成 ringing_tower）",
                  "ringing_tower" in info.lower(), f"tail={info[-160:]!r}")

        cal.slice_plate(driver, win)
        sliced, text = cal.wait_gcode(driver, win)
        rep.check("切片成功（生成 G-code）", sliced, f"tail={text[-160:]!r}")

        # --- Extra coverage: Fast Tower in a fresh app session ---
        rep.log("[INFO] Fast Tower: terminating and relaunching a fresh session")
        fh = app.extra.get("log_fh")
        if fh:
            try:
                fh.close()
            except Exception:
                pass
        try:
            app.terminate()
        except Exception:
            pass
        deadline = time.monotonic() + 10.0
        while app.alive() and time.monotonic() < deadline:
            time.sleep(0.3)
        time.sleep(1.0)
        fast_profile = OUT / "profile_fast"
        shutil.rmtree(fast_profile, ignore_errors=True)
        app, win = launch_and_focus(
            driver, fast_profile, model=None, timeout_s=args.timeout,
            log_path=OUT / "app_launch_fast.log")
        rep.check("Fast Tower 新会话启动", True, win.title)
        time.sleep(2.0)
        rep.check("打开 Input Shaping Frequency（Fast）",
                  cal.open_calib(driver, win, "Input Shaping Frequency"))
        dlg2 = cal.window_by_title(driver, app, "Input shaping Frequency",
                                   timeout_s=15.0)
        if dlg2 is None:
            cal.open_calib(driver, win, "Input Shaping Frequency")
            dlg2 = cal.window_by_title(driver, app,
                                       "Input shaping Frequency",
                                       timeout_s=10.0)
        rep.check("Fast Tower 对话框打开", dlg2 is not None)
        if dlg2 is not None:
            words = recognize_text(driver.capture(win), timeout_s=20)
            fast = next((w for w in words
                         if "fast" in w.text.lower()), None)
            rep.log(f"[INFO] Fast Tower label="
                    f"{fast.rect.to_xywh() if fast else None}")
            if fast is not None:
                cx = win.rect.x + fast.rect.center[0]
                cy = win.rect.y + fast.rect.center[1]
                driver.click(cx, cy)
                time.sleep(0.6)
                driver.click(cx - 18, cy)
                time.sleep(0.6)
            rep.check("选择 Fast Tower", fast is not None)
            vp_before = m7b._vp_colored(driver.capture(win))
            rep.check("Fast Tower 确定", cal.click_ok(driver, dlg2))
            arrived2, frame2, vp2 = cal.wait_model(
                driver, win, vp_before, delta=0.003)
            if frame2 is not None:
                frame2.save_png(OUT / "after_ok_fast.png")
            info2 = cal.object_info_text(driver, win)
            rep.check("生成 fast_tower 对象",
                      arrived2 and "fast" in info2.lower()
                      and "tower" in info2.lower(),
                      f"tail={info2[-160:]!r}")
            cal.slice_plate(driver, win)
            sliced2, text2 = cal.wait_gcode(driver, win)
            rep.check("Fast Tower 切片成功", sliced2,
                      f"tail={text2[-160:]!r}")
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
        exit_code = rep.save({"covered": ["#214"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
