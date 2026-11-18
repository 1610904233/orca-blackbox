#!/usr/bin/env python3
# m3l_mixing_delta.py — macOS port: Feishu #22/#24 Delta-E grade tooltip on
# the mixing mapping rows.
# feishu: baseline#91  (macOS port; corresponds to the enabled Windows
#         m3l_mixing_delta, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   after a Manual match, hovering a Color Mapping swatch row raises a
#   tooltip "Color Difference: <grade> (AE=<value>)" (#24); the grade obeys
#   the source bands Good <= 4.0, Fair <= 8.0, Poor > 8.0 (#22).
#
# macOS mapping:
#   the same batch dialog as m3k (separate window 'Color Mixing Match');
#   Manual -> Start Matching -> the mapping rows render.  wx tooltips need a
#   longer dwell here (~2.5 s); hovering window-relative (400,725) raises
#   'Color Difference: Good (AE=0.0)'.
#
# Artifacts: artifacts/mac/pilot/m3l/{report.log,result.json,*.png}.

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

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m3l"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
HOVER_XY = (400, 725)            # first mapping row, window-relative


def mixing_window(driver, app, win):
    for w in driver.windows_for_pid(app.pid):
        if (w.on_screen and w.id != win.id and w.layer != 0
                and "color mixing match" in (w.title or "").lower()):
            return w
    return None


def dlg_words(driver, win, dlg):
    return recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(dlg.rect.x - win.rect.x, dlg.rect.y - win.rect.y,
             dlg.rect.w, dlg.rect.h))


def find(words, needle):
    for w in words:
        if needle in w.text.lower():
            return w
    return None


def click_word(driver, win, word):
    driver.click(win.rect.x + word.rect.center[0],
                 win.rect.y + word.rect.center[1])
    time.sleep(1.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m3l macOS mixing Delta-E tooltip ===")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=DEFAULT_MODEL,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"rect={win.rect.to_xywh()}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        rep.check("模型载入（mixed 夹具）", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        entry = next((w for w in recognize_text(frame)
                      if "color mixing match" in w.text.lower()
                      and w.rect.x < 500), None)
        rep.check("混色入口（Color Mixing Match）", entry is not None)
        if entry is None:
            return rep.save({"stage": "entry"})
        click_word(driver, win, entry)
        time.sleep(1.5)
        dlg = mixing_window(driver, app, win)
        rep.check("混色对话框窗口", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({"stage": "dialog"})

        ws = dlg_words(driver, win, dlg)
        auto = find(ws, "auto")
        if auto is None:
            return rep.save({"stage": "auto"})
        click_word(driver, win, auto)
        ws = dlg_words(driver, win, dlg)
        manual = find(ws, "manual")
        rep.check("Manual 可选", manual is not None)
        if manual is None:
            return rep.save({"stage": "manual"})
        click_word(driver, win, manual)
        ws = dlg_words(driver, win, dlg)
        start = find(ws, "start matching")
        rep.check("Start Matching 可点击", start is not None)
        if start is None:
            return rep.save({"stage": "start"})
        click_word(driver, win, start)
        time.sleep(6.0)
        driver.capture(win).save_png(OUT / "matched.png")
        ws = dlg_words(driver, win, dlg)
        rep.check("匹配完成（Color Mapping 出现）",
                  find(ws, "color mapping") is not None
                  and find(ws, "confirm") is not None,
                  f"ocr={[w.text for w in ws][-10:]}")

        # Hover the first mapping row; wx tooltips need a real dwell.
        driver.move(win.rect.x + HOVER_XY[0], win.rect.y + HOVER_XY[1])
        time.sleep(2.5)
        words = recognize_text(
            driver.capture_screen(),
            Rect(win.rect.x + 380, win.rect.y + 710, 460, 80))
        text = " ".join(w.text for w in words).strip()
        rep.log(f"[INFO] tooltip OCR={text!r}")
        driver.capture_screen().save_png(OUT / "tooltip.png")
        m = re.search(r"color difference:\s*(good|fair|poor)\s*"
                      r"\(ae\s*=\s*([0-9.]+)\)", text, re.I)
        rep.check("#24 映射行悬停出现 Delta-E tooltip", m is not None, text)
        if m is None:
            return rep.save({"stage": "tooltip"})
        grade = m.group(1).lower()
        ae = float(m.group(2))
        expect = "good" if ae <= 4.0 else ("fair" if ae <= 8.0 else "poor")
        rep.check("#22 等级与 AE 带一致（Good<=4 / Fair<=8 / Poor>8）",
                  grade == expect, f"grade={grade} AE={ae} expected={expect}")
        rep.check("tooltip 含 Color Difference + AE=",
                  "color difference" in text.lower() and "ae=" in text.lower(),
                  text)

        # Cancel the dialog (tooltip assertions are complete).
        ws = dlg_words(driver, win, dlg)
        cancel = find(ws, "cancel")
        if cancel is not None:
            click_word(driver, win, cancel)
            time.sleep(1.5)
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
        if app is not None and not args.keep:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        exit_code = rep.save({"covered": ["#91"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
