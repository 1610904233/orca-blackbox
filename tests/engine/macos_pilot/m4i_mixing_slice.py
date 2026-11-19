#!/usr/bin/env python3
# m4i_mixing_slice.py — macOS port: Feishu #89/#157 mixed-slice + export.
# feishu: baseline#89 baseline#157  (macOS port; corresponds to the enabled
#         Windows m4i_mixing_slice, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   two schemes of DIFFERENT modes are registered (Ratio 50/50 + Gradient),
#   the mixed project slices to completion, and the exported gcode carries
#   at least two DISTINCT ^T<n> tool-change commands.
#
# macOS mapping:
#   Ratio   -> Add Mix (teal + at (388,521)); row 1 -> a PLA (558,321);
#              click a recommendation swatch (first saturated square below
#              'Mixing Recommendations', measured (458,639)); OK.
#   Gradient-> Add Mix -> Gradient tab (710,105); compatible rows; OK
#              (default label F3->F2).
#   slice   -> mac_common.slice_and_export.
#   gcode   -> mac_gcode.tool_changes (distinct ^T<n>).
#
# Artifacts: artifacts/mac/pilot/m4i/{report.log,result.json,work/*.gcode,
#            *.png}.

from __future__ import annotations

import argparse
import colorsys
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

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
    wait_for_model,
)
import mac_gcode  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m4i"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
ADD_BTN = (388, 521)


def mix_window(driver, app, win, needle):
    for w in driver.windows_for_pid(app.pid):
        if (w.on_screen and w.id != win.id and w.layer != 0
                and needle in (w.title or "").lower()):
            return w
    return None


def dlg_words(driver, win, dlg):
    return recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(dlg.rect.x - win.rect.x, dlg.rect.y - win.rect.y,
             dlg.rect.w, dlg.rect.h))


def labels(driver, win):
    return [(w.text.strip(), w.rect) for w in recognize_text(driver.capture(win))
            if w.rect.x < 330 and 530 < w.rect.y < 680
            and ("->" in w.text or "%" in w.text)]


def find_swatch(driver, win, dlg):
    frame = driver.capture(win)
    width = frame.width
    for y in range(600, min(frame.height, 720), 3):
        run = 0
        start = None
        for x in range(440, min(width, 700)):
            i = (y * width + x) * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            _h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            hot = s > 0.45 and v > 0.45
            if hot and run == 0:
                start = x
            if hot:
                run += 1
            else:
                if run >= 12 and start is not None:
                    return (start + run // 2, y)
                run = 0
                start = None
    return None


def make_compatible(driver, win, dlg):
    driver.click(win.rect.x + 566, win.rect.y + 255)
    time.sleep(1.0)
    driver.click(win.rect.x + 558, win.rect.y + 321)
    time.sleep(1.5)
    text = " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()
    return "cannot be mixed" not in text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    work = OUT / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    model = work / "m4i_mixed.3mf"
    shutil.copy2(DEFAULT_MODEL, model)
    gcode = work / "m4i_mixed.gcode"

    rep = Reporter(OUT)
    rep.log("=== m4i macOS mixed slice + export ===")
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
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        ok, _f, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        rep.check("multicolor project loads", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})
        base = labels(driver, win)
        rep.check("seeded entry present", len(base) >= 1,
                  f"entries={[t for t, _r in base]}")

        # --- Ratio scheme -------------------------------------------------
        driver.click(win.rect.x + ADD_BTN[0], win.rect.y + ADD_BTN[1])
        time.sleep(1.5)
        dlg = mix_window(driver, app, win, "add mix")
        rep.check("add mix dialog opens (Ratio)", dlg is not None)
        if dlg is None:
            return rep.save({"stage": "dialog-ratio"})
        rep.check("ratio pair compatible", make_compatible(driver, win, dlg))
        sw = find_swatch(driver, win, dlg)
        rep.log(f"[INFO] recommendation swatch={sw}")
        if sw is not None:
            driver.click(win.rect.x + sw[0], win.rect.y + sw[1])
            time.sleep(1.0)
        driver.click(win.rect.x + 672, win.rect.y + 707)   # OK
        time.sleep(2.0)
        ents1 = labels(driver, win)
        ratio_new = [e for e in ents1 if e[0] not in {t for t, _r in base}]
        rep.check("Ratio 方案已注册", len(ratio_new) == 1,
                  f"entries={[t for t, _r in ents1]}")

        # --- Gradient scheme ---------------------------------------------
        driver.click(win.rect.x + ADD_BTN[0], win.rect.y + ADD_BTN[1])
        time.sleep(1.5)
        dlg2 = mix_window(driver, app, win, "add mix")
        rep.check("add mix dialog opens (Gradient)", dlg2 is not None)
        if dlg2 is None:
            return rep.save({"stage": "dialog-gradient"})
        driver.click(win.rect.x + 710, win.rect.y + 105)   # Gradient tab
        time.sleep(1.5)
        rep.check("gradient pair compatible", make_compatible(driver, win, dlg2))
        driver.click(win.rect.x + 672, win.rect.y + 707)   # OK
        time.sleep(2.0)
        ents2 = labels(driver, win)
        grad_new = [e for e in ents2
                    if "->" in e[0]
                    and e[0] not in {t for t, _r in ents1}]
        rep.check("Gradient 方案已注册", len(grad_new) == 1,
                  f"entries={[t for t, _r in ents2]}")
        driver.capture(win).save_png(OUT / "entries.png")

        # --- Slice + export ----------------------------------------------
        if not slice_and_export(driver, win, rep, gcode,
                                [work, OUT, ARTIFACTS / "pilot",
                                 HERE / "fixtures"]):
            rep.check("混色切片并导出", False, "slice/export failed")
            return rep.save({"stage": "slice"})
        rep.check("混色切片并导出", True,
                  f"size={gcode.stat().st_size}")
        data = gcode.read_bytes()
        tools = mac_gcode.tool_changes(data)
        used = mac_gcode.used_filaments(data)
        rep.log(f"[INFO] tool changes={tools} used={used}")
        rep.check("#50 gcode 含 >=2 种换刀指令", len(tools) >= 2,
                  f"tools={tools}")
        rep.check("app alive", app.alive())

        alive_before = app.alive()
        closed = close_app(driver, app, win)
        app = None
        rep.check("软件正常关闭", alive_before and closed,
                  f"alive_before={alive_before} closed={closed}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        exit_code = rep.save({"covered": ["#89", "#157"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
