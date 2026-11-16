#!/usr/bin/env python3
# m3j_mixing_entry.py — macOS pilot: Feishu #100 mixing entry + Auto gate.
# feishu: none  (macOS pilot probe; corresponds to the enabled Windows
#         m3j_mixing_entry, not registered in cases.py yet)
#
# Windows assertions -> macOS equivalents:
#   mixing dialog opens      -> new "Color Mixing Match" window / OCR
#   default mode is Auto     -> OCR "Match Mode" + "Auto" on the same row
#   Auto gates on nozzle     -> OCR warning "Automatic color mixing
#                               matching is not supported ..."
#   warning dismissable      -> click OCR "Got it"
#   dialog survives warning  -> OCR still shows "Start Matching"/"Match Mode"
#
# The macOS mixing dialog is a custom-drawn overlay (AX exposes only a few
# static labels), so this pilot uses Vision OCR for text and real clicks at
# the OCR boxes.
#
# Artifacts: artifacts/mac/pilot/m3j/{*.png,report.log,result.json}.

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]       # repo root
ENGINE = Path(__file__).resolve().parents[1]     # tests/engine
for path in (str(HERE), str(ENGINE)):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import (  # noqa: E402
    find_text, joined_text, recognize_text,
)
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m3j"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"


def _click_word(driver, win, word, label: str) -> None:
    cx, cy = word.rect.center
    rep_text = f"({win.rect.x + cx:.0f},{win.rect.y + cy:.0f})"
    print(f"[m3j] click {label!r} at {rep_text}")
    driver.click(win.rect.x + cx, win.rect.y + cy)


def _mixing_windows(driver, app, main_win, max_height: float | None = None):
    out = []
    for w in driver.windows_for_pid(app.pid):
        if w.id == main_win.id or not w.on_screen:
            continue
        if "color mixing match" not in (w.title or "").lower():
            continue
        if max_height is not None and w.rect.h > max_height:
            continue
        out.append(w)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--model-timeout", default=60.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m3j macOS mixing-entry pilot ===")
    rep.log(f"datadir={args.datadir} model={args.model}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=args.model,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"blockers={app.extra.get('blockers')}")

        loaded, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=args.model_timeout)
        frame.save_png(OUT / "model_loaded.png")
        rep.check("model loaded", loaded,
                  f"colored_fraction={frac:.4f}")

        words = recognize_text(frame)
        entry = next((w for w in words
                      if "color mixing match" in w.text.lower()
                      and w.rect.x < 500), None)
        rep.check("entry found", entry is not None,
                  f"ocr={joined_text(words)[:200]}")
        if entry is None:
            raise RuntimeError("Color Mixing Match entry not found")
        _click_word(driver, win, entry, "Color Mixing Match")
        time.sleep(1.5)

        dialog_frame = driver.capture(win)
        dialog_frame.save_png(OUT / "dialog_open.png")
        dwords = recognize_text(dialog_frame)
        dlg_wins = _mixing_windows(driver, app, win)
        has_mode = find_text(dwords, "match mode") is not None
        has_start = find_text(dwords, "start matching") is not None
        rep.check("mixing dialog opens", bool(dlg_wins) or (has_mode and has_start),
                  f"windows={[(w.id, w.title, w.rect.to_xywh()) for w in dlg_wins]} "
                  f"ocr_mode={has_mode} ocr_start={has_start}")

        match_mode = find_text(dwords, "match mode")
        auto = find_text(dwords, "auto")
        auto_ok = (match_mode is not None and auto is not None
                   and abs(auto.rect.y - match_mode.rect.y) < 20
                   and auto.rect.x > match_mode.rect.x)
        rep.check("default mode is Auto", auto_ok,
                  f"match_mode={match_mode} auto={auto}")
        if auto is None:
            raise RuntimeError("Auto mode text not found")

        start = find_text(dwords, "start matching")
        rep.check("Start Matching found", start is not None)
        if start is None:
            raise RuntimeError("Start Matching not found")
        _click_word(driver, win, start, "Start Matching")
        time.sleep(2.0)

        warn_frame = driver.capture(win)
        warn_frame.save_png(OUT / "warning.png")
        wwords = recognize_text(warn_frame)
        warn_text = find_text(wwords, "automatic color mixing matching")
        warn_not_supported = find_text(wwords, "not supported")
        warn_wins = _mixing_windows(driver, app, win, max_height=300)
        rep.check("nozzle warning appears",
                  (warn_text is not None) or (warn_not_supported is not None)
                  or bool(warn_wins),
                  f"ocr={joined_text(wwords)[:300]} "
                  f"windows={[(w.id, w.rect.to_xywh()) for w in warn_wins]}")

        got_it = find_text(wwords, "got it")
        rep.check("Got it found", got_it is not None)
        if got_it is not None:
            _click_word(driver, win, got_it, "Got it")
            time.sleep(1.5)
            after_frame = driver.capture(win)
            after_frame.save_png(OUT / "after_got_it.png")
            awords = recognize_text(after_frame)
            warn_gone = (find_text(awords, "automatic color mixing matching") is None
                         and find_text(awords, "got it") is None)
            dialog_still = (find_text(awords, "start matching") is not None
                            or find_text(awords, "match mode") is not None)
            rep.check("warning dismissable", warn_gone,
                      f"ocr={joined_text(awords)[:200]}")
            rep.check("dialog survives warning", dialog_still)
        else:
            rep.check("warning dismissable", False, "Got it not found")
            rep.check("dialog survives warning", False, "not tested")

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
        exit_code = rep.save({})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
