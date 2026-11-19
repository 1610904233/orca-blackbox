#!/usr/bin/env python3
# m3t_mixing_add_ratio.py — macOS port: Feishu #78 Add Mix Ratio defaults.
# feishu: baseline#78  (macOS port; corresponds to the enabled Windows
#         m3t_mixing_add_ratio, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   Ratio is the default tab with 2 rows / 50:50 legends and the seeded
#   F1=F PETG + F2=PLA incompatibility banner; the row-1 combo can be
#   switched to a compatible PLA (preview repaints, ratio unchanged); the
#   selector clamps to 10/90 and shows/clears the high-ratio advisory; the
#   row button adds to 3 rows and flips to REMOVE at the cap (icon shifts
#   4px left), removing back to 2; Cancel leaves the sidebar unchanged.
#
# macOS mapping:
#   Add Mix   -> teal + at (388,521); tab row y=105.
#   rows      -> AXStaticText values 'Filament N' (OCR truncates the word).
#   row combo -> (566,255) then the PLA option (558,321); banner clears.
#   selector  -> bar sits ~18px above the '%' legends; x 450 / 600 / 735.
#   row add   -> the AXButton at the 'Filament Selection' line's right edge;
#                AXPress adds, then removes at the cap (rect shifts left).
#
# Artifacts: artifacts/mac/pilot/m3t/{report.log,result.json,*.png}.

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
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m3t"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
ADD_BTN = (388, 521)
OK_BTN = (672, 707)
CANCEL_BTN = (488, 709)
PREVIEW_CARD = Rect(585, 470, 150, 90)   # window-relative Mix Effect card


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


def row_count(driver, dlg) -> int:
    vals = {str(c.value).strip() for c in driver.controls(dlg)
            if c.role == "AXStaticText"
            and re.fullmatch(r"Filament \d+", str(c.value).strip())}
    return len(vals)


def row_button(driver, dlg):
    sel = next((c for c in driver.controls(dlg)
                if c.role == "AXStaticText"
                and "filament selection" in
                (str(c.value) + " " + c.title).lower()), None)
    if sel is None or sel.rect is None:
        return None
    return next((c for c in driver.controls(dlg)
                 if c.role == "AXButton" and c.rect is not None
                 and abs(c.rect.y - sel.rect.y) < 24
                 and c.rect.x > 1000), None)


def legends(driver, win, dlg):
    out = []
    for w in dlg_words(driver, win, dlg):
        m = re.search(r"(\d+)%", w.text)
        if m and w.rect.y > 330:
            out.append((int(m.group(1)), w.rect))
    return out


def bar_y(legs):
    return (min(r.y for _v, r in legs) - 18) if legs else 367


def ok_enabled(driver, win) -> bool:
    frame = driver.capture(win)
    r, g, b, _a = frame.pixel(OK_BTN[0], OK_BTN[1])
    return g > 100 and g > r + 20


def region_mean(frame, rect: Rect):
    x0, y0 = int(rect.x), int(rect.y)
    x1, y1 = int(rect.right), int(rect.bottom)
    n = rsum = gsum = bsum = 0
    for y in range(y0, min(y1, frame.height), 2):
        row = y * frame.width * 4
        for x in range(x0, min(x1, frame.width), 2):
            i = row + x * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            rsum += r
            gsum += g
            bsum += b
            n += 1
    return (rsum / max(1, n), gsum / max(1, n), bsum / max(1, n))


def entry_labels(driver, win):
    return [(w.text.strip(), w.rect) for w in recognize_text(driver.capture(win))
            if w.rect.x < 330 and 530 < w.rect.y < 690
            and re.search(r"\d+%", w.text)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)

    rep = Reporter(OUT)
    rep.log("=== m3t macOS Add Mix Ratio defaults ===")
    rep.log(f"datadir={args.datadir}")

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
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        frame.save_png(OUT / "loaded.png")
        rep.check("multicolor project loads", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})
        base = entry_labels(driver, win)
        rep.check("seeded entry present", len(base) >= 1,
                  f"entries={[t for t, _r in base]}")

        driver.click(win.rect.x + ADD_BTN[0], win.rect.y + ADD_BTN[1])
        time.sleep(1.5)
        dlg = mix_window(driver, app, win, "add mix")
        rep.check("add mix dialog opens", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({"stage": "dialog"})

        # --- #1: default Ratio presentation --------------------------------
        words = " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()
        rep.check("default mode is Ratio",
                  "filament selection" in words and "mixing ratio" in words,
                  words[:120])
        cards = [s for s in ("mixing ratio", "preview", "mix effect",
                             "mixing recommendations") if s in words]
        rep.check("ratio cards present", len(cards) >= 3, f"cards={cards}")
        rows0 = row_count(driver, dlg)
        legs0 = sorted(v for v, _r in legends(driver, win, dlg))
        rep.check("default 2 rows 50/50",
                  rows0 == 2 and legs0[:2] == [50, 50],
                  f"rows={rows0} legends={legs0}")

        words = " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()
        named = ("filament 1" in words and "filament 2" in words
                 and "cannot be mixed" in words)
        rep.check("default pair flagged incompatible",
                  named and not ok_enabled(driver, win),
                  f"banner={named} ok={ok_enabled(driver, win)}")
        driver.capture(win).save_png(OUT / "ratio_default.png")

        # --- #3: switch row 1 to a compatible PLA --------------------------
        before = driver.capture(win)
        driver.click(win.rect.x + 566, win.rect.y + 255)
        time.sleep(1.0)
        driver.click(win.rect.x + 558, win.rect.y + 321)
        time.sleep(1.5)
        after = driver.capture(win)
        after.save_png(OUT / "ratio_compatible.png")
        words = " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()
        legs1 = sorted(v for v, _r in legends(driver, win, dlg))
        rep.check("row combo excludes used, pick valid",
                  "cannot be mixed" not in words and row_count(driver, dlg) == 2,
                  words[:120])
        rep.check("ratio unchanged after switch",
                  legs1[:2] == [50, 50], f"legends={legs1}")
        m0 = region_mean(before, PREVIEW_CARD)
        m1 = region_mean(after, PREVIEW_CARD)
        mdiff = sum(abs(a - b) for a, b in zip(m0, m1))
        rep.check("preview repaints with filament", mdiff > 10.0,
                  f"mean {tuple(round(v,1) for v in m0)} -> "
                  f"{tuple(round(v,1) for v in m1)} d={mdiff:.1f}")

        # --- #4: selector clamps 10..90; advisory shows and clears ---------
        clamped = advised = cleared = False
        legs = legends(driver, win, dlg)
        if legs:
            driver.click(win.rect.x + 450, win.rect.y + bar_y(legs))
            time.sleep(1.0)
            low = sorted(v for v, _r in legends(driver, win, dlg))
            driver.click(win.rect.x + 735, win.rect.y + bar_y(legends(driver, win, dlg)))
            time.sleep(1.0)
            high = sorted(v for v, _r in legends(driver, win, dlg))
            words = " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()
            advised = "ratio is too high" in words
            clamped = bool(low and high
                           and min(low + high) >= 10
                           and max(low + high) <= 90
                           and sum(low) == 100 and sum(high) == 100)
            rep.log(f"[INFO] legends at ends={low} / {high} advisory={advised}")
            driver.click(win.rect.x + 600, win.rect.y + bar_y(legends(driver, win, dlg)))
            time.sleep(1.0)
            words = " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()
            cleared = "ratio is too high" not in words
            driver.capture(win).save_png(OUT / "ratio_clamped.png")
        rep.check("ratio clamped 10-90 sum 100", clamped)
        rep.check("high-ratio advisory shows and clears", advised and cleared,
                  f"shown={advised} cleared={cleared}")

        # --- #2: row button adds, flips to REMOVE at 3, removes ------------
        add_ok = remove_ok = toggled = False
        btn = row_button(driver, dlg)
        if btn is not None:
            x0 = btn.rect.x
            driver.click_control(btn)
            time.sleep(1.2)
            add_ok = row_count(driver, dlg) == 3
            btn2 = row_button(driver, dlg)
            toggled = bool(btn2 is not None and btn2.rect.x != x0)
            if btn2 is not None:
                driver.click_control(btn2)
                time.sleep(1.2)
                remove_ok = row_count(driver, dlg) == 2
            rep.log(f"[INFO] add={add_ok} toggle_x={toggled} "
                    f"remove={remove_ok} rows={row_count(driver, dlg)}")
        rep.check("add row to 3", add_ok)
        rep.check("button flips to remove at cap", toggled)
        rep.check("remove row to 2", remove_ok)
        driver.capture(win).save_png(OUT / "ratio_rows.png")

        driver.click(win.rect.x + CANCEL_BTN[0], win.rect.y + CANCEL_BTN[1])
        time.sleep(1.5)
        gone = mix_window(driver, app, win, "add mix") is None
        ents = entry_labels(driver, win)
        rep.check("cancel closes dialog", gone)
        rep.check("cancel 不注册方案", len(ents) == len(base),
                  f"{len(base)} -> {len(ents)}")
        rep.check("app alive", app.alive())

        alive_before = app.alive()
        closed = close_app(driver, app, win)
        app = None
        rep.check("software closed", alive_before and closed,
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
        exit_code = rep.save({"covered": ["#78"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
