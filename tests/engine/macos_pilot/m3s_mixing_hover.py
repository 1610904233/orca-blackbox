#!/usr/bin/env python3
# m3s_mixing_hover.py — macOS port: Feishu #8/#91 dialog-control hover
# tooltips (downgraded smoke on Windows).
# feishu: baseline#91  (macOS port; corresponds to the enabled Windows
#         m3s_mixing_hover, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   hovering known controls (the add-filament button and a swatch row) raises
#   a tooltip window whose text is OCR-readable (non-empty text).
#
# macOS mapping:
#   the batch dialog from m3k; Manual mode.  Hovering the + icon at
#   window-relative (802,186) for ~2.5 s shows "Add filament"; the mode combo
#   shows "Manually select filaments from the current list for color mixing.";
#   after a match the first mapping row shows "Color Difference: ... (AE=...)".
#   wx tooltips need the longer dwell; 1.2 s is not enough here.
#
# Artifacts: artifacts/mac/pilot/m3s/{report.log,result.json,*.png}.

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

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m3s"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


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


def hover_text(driver, win, x, y, w=340, h=70):
    driver.move(win.rect.x + x, win.rect.y + y)
    time.sleep(2.5)
    words = recognize_text(
        driver.capture_screen(),
        Rect(win.rect.x + x - 20, win.rect.y + y + 8, w, h))
    return " ".join(w.text for w in words).strip()


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
    rep.log("=== m3s macOS mixing dialog hover tooltips ===")

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
                  f"pid={app.pid} title={win.title!r}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        rep.check("模型载入（mixed 夹具）", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        entry = next((w for w in recognize_text(frame)
                      if "color mixing match" in w.text.lower()
                      and w.rect.x < 500), None)
        rep.check("混色入口", entry is not None)
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
        click_word(driver, win, find(ws, "auto"))
        ws = dlg_words(driver, win, dlg)
        click_word(driver, win, find(ws, "manual"))
        time.sleep(1.0)

        # #8 known-control tooltips: add-filament icon and the mode combo.
        add_tip = hover_text(driver, win, 802, 186)
        rep.log(f"[INFO] add button tooltip={add_tip!r}")
        rep.check("#8 Add filament 按钮 tooltip（非空且含 Add filament）",
                  "add filament" in add_tip.lower(), add_tip)
        mode_tip = hover_text(driver, win, 482, 119)
        rep.log(f"[INFO] mode combo tooltip={mode_tip!r}")
        rep.check("#8 Match Mode tooltip（非空）", bool(mode_tip), mode_tip)

        # #91 swatch-row tooltip after a match.
        ws = dlg_words(driver, win, dlg)
        start = find(ws, "start matching")
        rep.check("Start Matching 可点击", start is not None)
        if start is None:
            return rep.save({"stage": "start"})
        click_word(driver, win, start)
        time.sleep(6.0)
        driver.capture(win).save_png(OUT / "matched.png")
        row_tip = hover_text(driver, win, 400, 725, w=460, h=80)
        rep.log(f"[INFO] swatch tooltip={row_tip!r}")
        rep.check("#91 映射行悬停 tooltip（非空）", bool(row_tip), row_tip)
        rep.check("#91 tooltip 为 Delta-E 文本",
                  "color difference" in row_tip.lower()
                  or "ae=" in row_tip.lower(), row_tip)
        driver.capture_screen().save_png(OUT / "tooltip.png")

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
