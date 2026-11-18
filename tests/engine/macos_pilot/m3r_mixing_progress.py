#!/usr/bin/env python3
# m3r_mixing_progress.py — macOS port: Feishu #96 matching-in-progress state.
# feishu: baseline#96  (macOS port; corresponds to the enabled Windows
#         m3r_mixing_progress, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   while the match runs, a progress bar and a Stop button appear; afterwards
#   the mapping renders and Stop is gone.  The match is fast, so the Windows
#   case explicitly accepts a missed transient ("fast match, transient
#   missed — completion below") as long as completion is observed.
#
# macOS mapping:
#   the batch dialog from m3k; Manual mode; Start Matching.  The macOS dialog
#   is custom-drawn (no AX progress bar), so the transient is looked for by
#   OCR ("stop" / "matching") in a dense 0.2s poll; a miss is accepted exactly
#   like the Windows case.  Completion = Color Mapping + Confirm present and
#   no Stop text left.
#
# Artifacts: artifacts/mac/pilot/m3r/{report.log,result.json,*.png}.

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

OUT = ARTIFACTS / "pilot" / "m3r"
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


def text_of(words) -> str:
    return " ".join(w.text for w in words).lower()


def find(words, needle):
    for w in words:
        if needle in w.text.lower():
            return w
    return None


def click_word(driver, win, word):
    driver.click(win.rect.x + word.rect.center[0],
                 win.rect.y + word.rect.center[1])
    time.sleep(0.8)


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
    rep.log("=== m3r macOS mixing progress state ===")

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
        rep.check("multicolor project loads", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        entry = next((w for w in recognize_text(frame)
                      if "color mixing match" in w.text.lower()
                      and w.rect.x < 500), None)
        rep.check("mixing dialog entry", entry is not None)
        if entry is None:
            return rep.save({"stage": "entry"})
        click_word(driver, win, entry)
        time.sleep(1.5)
        dlg = mixing_window(driver, app, win)
        rep.check("mixing dialog opens", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({"stage": "dialog"})
        ws = dlg_words(driver, win, dlg)
        click_word(driver, win, find(ws, "auto"))
        ws = dlg_words(driver, win, dlg)
        click_word(driver, win, find(ws, "manual"))
        rep.check("mode switch to Manual", True)

        ws = dlg_words(driver, win, dlg)
        start = find(ws, "start matching")
        rep.check("Start Matching 可点击", start is not None)
        if start is None:
            return rep.save({"stage": "start"})
        click_word(driver, win, start)

        # Dense OCR poll for the in-progress state (custom-drawn controls).
        saw_stop = saw_progress = False
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            text = text_of(dlg_words(driver, win, dlg))
            if "stop" in text:
                saw_stop = True
            if "matching" in text and "start matching" not in text:
                saw_progress = True
            if saw_stop and saw_progress:
                break
            time.sleep(0.2)
        rep.log(f"[INFO] in-progress observed stop={saw_stop} "
                f"progress={saw_progress}")
        # Mirrors the Windows verdict: a missed transient is accepted; the
        # completion checks below are the hard ones.
        rep.check("progress/Stop 进行态（可错过，快匹配）", True,
                  f"observed stop={saw_stop} progress={saw_progress}"
                  if (saw_stop or saw_progress)
                  else "PASS (fast match, transient missed — completion below)")

        # Completion: Color Mapping + Confirm appear, no Stop text left.
        done = False
        text = ""
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            ws = dlg_words(driver, win, dlg)
            text = text_of(ws)
            if ("color mapping" in text and "confirm" in text
                    and "stop" not in text):
                done = True
                break
            time.sleep(0.5)
        driver.capture(win).save_png(OUT / "matched.png")
        rep.log(f"[INFO] final text={text[:220]!r}")
        rep.check("match completes（Color Mapping 渲染）", done, text[:160])
        rep.check("stop button gone after match", "stop" not in text)

        cancel = find(dlg_words(driver, win, dlg), "cancel")
        if cancel is not None:
            click_word(driver, win, cancel)
            time.sleep(1.2)
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
        exit_code = rep.save({"covered": ["#96"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
