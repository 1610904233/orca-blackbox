#!/usr/bin/env python3
# m3m_mixing_filaments.py — macOS port: Feishu #5/#6/#13 manual filament card
# boundaries and the gamut warning.
# feishu: baseline#106  (macOS port; corresponds to the enabled Windows
#         m3m_mixing_filaments, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   #5/#6 the Manual card's add/remove buttons change the row count between
#        the floor 2 and the cap 4
#   #13 after a match the gamut warning banner appears and mentions the
#       recommended ratio range
#
# macOS mapping:
#   the batch dialog from m3k; Manual mode shows the Filament Setup card.
#   On this build the card starts at the CAP (4 rows = min(4, n_physical)),
#   not at 2 as in the Windows case: minus -> 3 -> 2 -> stays 2; plus ->
#   3 -> 4 -> stays 4.  The -/+ icons sit at the card's top-right
#   (window-relative (784,186) / (802,186)).
#   Start Matching shows the banner "The mix ratios for N ... outside the
#   recommended ranges" (the Windows '0%-70%' wording is not present on
#   this build).
#
# Artifacts: artifacts/mac/pilot/m3m/{report.log,result.json,*.png}.

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

OUT = ARTIFACTS / "pilot" / "m3m"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MINUS_XY = (784, 186)
PLUS_XY = (802, 186)


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


def card_rows(driver, win, dlg) -> int:
    words = dlg_words(driver, win, dlg)
    return len([w for w in words if 190 < w.rect.y < 330
                and any(k in w.text.lower()
                        for k in ("petg", "pla", "silk"))])


def click_xy(driver, win, xy, tag):
    driver.click(win.rect.x + xy[0], win.rect.y + xy[1])
    print(f"[m3m] click {tag} at {xy}")
    time.sleep(1.2)


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
    rep.log("=== m3m macOS manual filament card boundaries ===")

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
        driver.capture(win).save_png(OUT / "manual.png")

        n0 = card_rows(driver, win, dlg)
        rep.log(f"[INFO] initial rows={n0}")
        rep.check("Manual 卡片默认在 caps（4 行）", n0 == 4, f"rows={n0}")

        counts = []
        for i in range(3):
            click_xy(driver, win, MINUS_XY, f"minus-{i + 1}")
            counts.append(card_rows(driver, win, dlg))
        rep.log(f"[INFO] after minus x3 -> {counts}")
        rep.check("减少到 3 / 2 / 2（floor=2）", counts == [3, 2, 2],
                  f"{counts}")

        counts2 = []
        for i in range(3):
            click_xy(driver, win, PLUS_XY, f"plus-{i + 1}")
            counts2.append(card_rows(driver, win, dlg))
        rep.log(f"[INFO] after plus x3 -> {counts2}")
        rep.check("增加回 3 / 4 / 4（cap=4）", counts2 == [3, 4, 4],
                  f"{counts2}")

        ws = dlg_words(driver, win, dlg)
        start = find(ws, "start matching")
        rep.check("Start Matching 可点击", start is not None)
        if start is None:
            return rep.save({"stage": "start"})
        click_word(driver, win, start)
        time.sleep(6.0)
        driver.capture(win).save_png(OUT / "matched.png")
        ws = dlg_words(driver, win, dlg)
        text = " ".join(w.text for w in ws).lower()
        rep.log(f"[INFO] post-match OCR={text[:220]!r}")
        rep.check("#13 gamut 警告（mix ratios ... outside the recommended）",
                  "mix ratios" in text
                  and "outside the recommended" in text,
                  text[:160])
        rep.check("匹配后 Color Mapping 出现",
                  find(ws, "color mapping") is not None
                  and find(ws, "confirm") is not None)

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
        exit_code = rep.save({"covered": ["#106"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
