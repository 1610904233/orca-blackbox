#!/usr/bin/env python3
# m4b_batch_manual.py — macOS port: Feishu #92/#103/#104/#105 batch dialog
# Auto/Manual filament cards and the post-Confirm kept-filament cleanup.
# feishu: baseline#92 baseline#103 baseline#104 baseline#105  (macOS port;
#         corresponds to the enabled Windows m4b_batch_manual, registered in
#         cases.MACOS_BASELINE)
#
# Windows assertions (表2 #2/#3/#4):
#   - the Auto (recommended) card shows four slots with numbered swatches and
#     the full-spectrum labels
#   - the Manual card shows the 2-column combo rows
#   - after Confirm only the SELECTED physical filaments are kept; unselected
#     physical slots are removed from the sidebar
#
# macOS mapping:
#   the batch dialog from m3k.  The Auto card and the Manual card both show
#   four Filament Setup rows on this build (the fixture has 5 physicals).
#   After a Manual match + Confirm the sidebar should drop the unselected
#   slot (the default selections are physicals 1..4), so the filament-row
#   count changes 5 -> 4.  Counts are OCR-based (labels at x<330, y 400..500
#   in the sidebar, and x 380..820, y 190..330 in the dialog card).
#
# Artifacts: artifacts/mac/pilot/m4b/{report.log,result.json,*.png}.

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

OUT = ARTIFACTS / "pilot" / "m4b"
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


def sidebar_rows(driver, win) -> int:
    words = recognize_text(driver.capture(win))
    return len([w for w in words if w.rect.x < 330 and 400 < w.rect.y < 500
                and any(k in w.text.lower()
                        for k in ("petg", "pla", "silk", "snapspeed"))])


def card_rows(driver, win, dlg) -> int:
    words = dlg_words(driver, win, dlg)
    return len([w for w in words if 190 < w.rect.y < 330
                and any(k in w.text.lower()
                        for k in ("petg", "pla", "silk", "full s", "spectrum"))])


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
    rep.log("=== m4b macOS batch Auto/Manual cards + kept filaments ===")

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
        rows0 = sidebar_rows(driver, win)
        rep.log(f"[INFO] sidebar filament rows before={rows0}")

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
        driver.capture(win).save_png(OUT / "auto_card.png")

        auto_rows = card_rows(driver, win, dlg)
        rep.log(f"[INFO] Auto card rows={auto_rows}")
        rep.check("#92 Auto 推荐卡 4 个槽位", auto_rows == 4,
                  f"rows={auto_rows}")

        ws = dlg_words(driver, win, dlg)
        click_word(driver, win, find(ws, "auto"))
        ws = dlg_words(driver, win, dlg)
        click_word(driver, win, find(ws, "manual"))
        time.sleep(1.0)
        driver.capture(win).save_png(OUT / "manual_card.png")
        manual_rows = card_rows(driver, win, dlg)
        rep.log(f"[INFO] Manual card rows={manual_rows}")
        rep.check("#103 Manual 卡 4 行组合框", manual_rows == 4,
                  f"rows={manual_rows}")

        ws = dlg_words(driver, win, dlg)
        start = find(ws, "start matching")
        rep.check("Start Matching 可点击", start is not None)
        if start is None:
            return rep.save({"stage": "start"})
        click_word(driver, win, start)
        time.sleep(6.0)
        ws = dlg_words(driver, win, dlg)
        confirm = find(ws, "confirm")
        rep.check("Confirm 可点击", confirm is not None)
        if confirm is None:
            return rep.save({"stage": "confirm"})
        click_word(driver, win, confirm)
        time.sleep(2.5)
        rep.check("Confirm 关闭对话框",
                  mixing_window(driver, app, win) is None)
        rows1 = sidebar_rows(driver, win)
        rep.log(f"[INFO] sidebar filament rows after={rows1}")
        rep.check("#104/#105 Confirm 后只保留选中的物理耗材（5 -> 4）",
                  rows1 == 4, f"{rows0} -> {rows1}")
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
        exit_code = rep.save({"covered": ["#92", "#103", "#104", "#105"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
