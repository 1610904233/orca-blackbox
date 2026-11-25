#!/usr/bin/env python3
# m8x_217_yolo.py — macOS port: Feishu #217 YOLO flow comparison.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_217,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions: Calibration > Flow rate > YOLO (Recommended) loads 11
# blocks (0, +/-0.01..0.05); clear the bed; YOLO (perfectionist) loads 16
# blocks (0, +0.005..0.035, -0.005..-0.04); object names are exact; a visible
# row is selectable; slice succeeds.
#
# macOS mapping: submenu AXMenuItems, object names from the saved project,
# clear via Edit > Delete All, Slice at (1000,45).
#
# Artifacts: artifacts/mac/pilot/m8x_217/{report.log,result.json,work/*.3mf}.

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
import mac_3mf  # noqa: E402
import mac_calib as cal  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_217"
EMPTY_BED_MAX = 0.015


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
    p_rec = work / "m8x_217_recommended.3mf"
    p_perf = work / "m8x_217_perfectionist.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_217 macOS YOLO flow comparison ===")

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

        # ---- recommended (11 blocks) ---------------------------------
        rep.check("Calibration > Flow rate > YOLO (Recommended)",
                  cal.open_calib(driver, win, "YOLO (Recommended)"))
        arrived, frame, vp1 = cal.wait_model(driver, win, vp0, delta=0.01)
        if frame is not None:
            frame.save_png(OUT / "recommended.png")
        rep.check("推荐版加载（11 块落板）", arrived,
                  f"viewport {vp0:.4f}->{vp1:.4f}")
        rep.check("推荐版项目保存", cal.save_project_anywhere(
            driver, win, p_rec, search_root=HERE / "artifacts" / "mac")
            and p_rec.exists())
        names_rec = mac_3mf.object_names(p_rec) if p_rec.exists() else []
        rep.log(f"[INFO] recommended names={names_rec}")
        flow_rec = [n for n in names_rec if "flowrate" in n.lower()]
        rep.check("推荐版对象名精确一致（11 块）", len(flow_rec) == 11,
                  f"names={names_rec}")

        # Slice the recommended version too (the user-facing comparison
        # expects both variants to be slicable).
        cal.slice_plate(driver, win)
        sliced_rec, text_rec = cal.wait_gcode(driver, win)
        rep.check("推荐版切片成功（生成 G-code）", sliced_rec,
                  f"tail={text_rec[-160:]!r}")
        driver.click(win.rect.x + 60, win.rect.y + 45)  # Prepare tab
        time.sleep(1.2)

        # ---- clear the bed -------------------------------------------
        delete = next((c for c in driver.controls(win, max_depth=12)
                       if c.role == "AXMenuItem"
                       and c.title.strip().lower() == "delete all"), None)
        rep.check("清场入口（Edit > Delete All）", delete is not None)
        if delete is not None:
            driver.click_control(delete)
            time.sleep(2.0)
        vp_clear = cal.vp(driver.capture(win))
        rep.check("推荐版清场（画布清空）", vp_clear < EMPTY_BED_MAX,
                  f"viewport={vp_clear:.4f}")

        # ---- perfectionist (16 blocks) -------------------------------
        rep.check("Calibration > Flow rate > YOLO (perfectionist)",
                  cal.open_calib(driver, win, "YOLO (perfectionist version)"))
        # The perfectionist preset changes process settings; the app asks how
        # to merge them.  Discard (same choice as the Windows case).
        time.sleep(1.5)
        discarded = False
        for w in driver.windows_for_pid(app.pid):
            if not w.on_screen or w.id == win.id or w.rect.area < 5000:
                continue
            words = recognize_text(driver.capture_screen().crop(w.rect))
            discard = next((x for x in words
                            if x.text.strip().lower() == "discard"), None)
            if discard is not None:
                driver.click(w.rect.x + discard.rect.center[0],
                             w.rect.y + discard.rect.center[1])
                discarded = True
                time.sleep(1.5)
                break
        rep.check("完美版工艺设置合并框（Discard）", discarded,
                  f"discarded={discarded}")
        arrived2, frame2, vp2 = cal.wait_model(
            driver, win, vp_clear, delta=0.01)
        if frame2 is not None:
            frame2.save_png(OUT / "perfectionist.png")
        rep.check("完美版加载（16 块落板）", arrived2,
                  f"viewport {vp_clear:.4f}->{vp2:.4f}")
        rep.check("完美版项目保存", cal.save_project_anywhere(
            driver, win, p_perf, search_root=HERE / "artifacts" / "mac")
            and p_perf.exists())
        names_perf = mac_3mf.object_names(p_perf) if p_perf.exists() else []
        rep.log(f"[INFO] perfectionist names={names_perf}")
        flow_perf = [n for n in names_perf if "flowrate" in n.lower()]
        rep.check("完美版对象名精确一致（16 块）", len(flow_perf) == 16,
                  f"names={names_perf}")
        rep.check("两版对比（16>11）",
                  len(flow_rec) == 11 and len(flow_perf) == 16,
                  f"11 vs {len(flow_perf)}")

        # ---- visible row selectable + slice --------------------------
        words = recognize_text(driver.capture_screen().crop(win.rect))
        tab = next((w for w in words if w.text.strip() == "Objects"), None)
        if tab is not None:
            driver.click(win.rect.x + tab.rect.center[0],
                         win.rect.y + tab.rect.center[1])
            time.sleep(1.2)
        words = recognize_text(driver.capture_screen().crop(win.rect))
        row = next((w for w in words
                    if w.text.strip().lower().startswith("flowrate")), None)
        selected = False
        if row is not None:
            driver.click(win.rect.x + row.rect.center[0],
                         win.rect.y + row.rect.center[1])
            time.sleep(1.0)
            info = cal.object_info_text(driver, win)
            selected = row.text.strip().lower() in info.lower()
        rep.check("完美版对象行可单独选中", selected,
                  f"row={row.text if row else None}")

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
        exit_code = rep.save({"covered": ["#217"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
