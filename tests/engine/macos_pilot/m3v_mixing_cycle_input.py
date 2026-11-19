#!/usr/bin/env python3
# m3v_mixing_cycle_input.py — macOS port: Feishu #80 Cycle pattern input.
# feishu: baseline#80  (macOS port; corresponds to the enabled Windows
#         m3v_mixing_cycle_input, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   default '12'; clicking the 3rd quick badge appends '3'; legal patterns
#   ('23', '23,32') validate with OK enabled; '623' -> unknown filament;
#   '2a3' -> invalid characters; ',123' -> leading comma; '2' -> same-color
#   advisory but OK enabled; empty normalizes back to '12'; 520 typed chars
#   are capped at 512; Cancel leaves the app alive.
#
# macOS mapping:
#   Cycle tab (540,105) in the 'Add Mix' window.  The pattern control is the
#   dialog's only AXTextField; AXSetValue + AXConfirm fires the wx change
#   event and validation (AXSetValue alone would not).
#   The five quick badges are custom-drawn at y~259; the 3rd is (510,259).
#   OK enabled/disabled is sampled from the button fill (teal vs grey).
#   MaxLength is only enforced for real edits: AXSetValue bypasses it, so
#   the cap is exercised with a real clipboard paste (512 accepted, a second
#   20-char paste is rejected -> length stays 512).
#
# Artifacts: artifacts/mac/pilot/m3v/{report.log,result.json,*.png}.

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

import AppKit  # noqa: E402
import ApplicationServices as AS  # noqa: E402

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos import _ax_perform, _ax_set  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m3v"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
ADD_BTN = (388, 521)
CYCLE_TAB = (540, 105)
THIRD_BADGE = (510, 259)
OK_BTN = (672, 707)
CANCEL_BTN = (488, 709)
ERRORS = ("cannot be mixed", "not recognized", "invalid characters",
          "leading or trailing commas")


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


def pattern_field(driver, dlg):
    return next((c for c in driver.controls(dlg)
                 if c.role == "AXTextField" and c.handle is not None), None)


def pattern_value(driver, dlg) -> str:
    fld = pattern_field(driver, dlg)
    return str(fld.value) if fld is not None else ""


def set_pattern(driver, dlg, text: str) -> str:
    fld = pattern_field(driver, dlg)
    if fld is None:
        return ""
    _ax_set(fld.handle, AS.kAXValueAttribute, text)
    time.sleep(0.3)
    if "AXConfirm" in (fld.actions or ()):
        _ax_perform(fld.handle, "AXConfirm")
    time.sleep(1.0)
    return pattern_value(driver, dlg)


def banner_text(driver, win, dlg) -> str:
    return " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()


def ok_enabled(driver, win) -> bool:
    frame = driver.capture(win)
    sx = frame.width / 1200.0
    sy = frame.height / 800.0
    r, g, b, _a = frame.pixel(int(OK_BTN[0] * sx), int(OK_BTN[1] * sy))
    # enabled = teal fill (0,150,136); disabled = flat grey (223,223,223)
    return g > 100 and g > r + 20


def paste(driver, text: str, field, *, select_all: bool = True) -> None:
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
    driver.click(*field.rect.center)
    time.sleep(0.3)
    if select_all:
        driver.send_key("a", modifiers=("cmd",))
        time.sleep(0.2)
    else:
        driver.send_key("end")
        time.sleep(0.2)
    driver.send_key("v", modifiers=("cmd",))
    time.sleep(1.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)

    rep = Reporter(OUT)
    rep.log("=== m3v macOS Cycle pattern input ===")
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

        driver.click(win.rect.x + ADD_BTN[0], win.rect.y + ADD_BTN[1])
        time.sleep(1.5)
        dlg = mix_window(driver, app, win, "add mix")
        rep.check("add mix dialog opens", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({"stage": "dialog"})
        driver.click(win.rect.x + CYCLE_TAB[0], win.rect.y + CYCLE_TAB[1])
        time.sleep(1.2)
        text = banner_text(driver, win, dlg)
        rep.check("cycle tab switches", "preview" in text
                  and "mix effect" in text, text[:100])
        rep.check("pattern input found", pattern_field(driver, dlg) is not None)

        # --- #10: default 12 ------------------------------------------------
        val = pattern_value(driver, dlg)
        rep.check("default pattern is 12", val == "12", f"value={val!r}")

        # --- #12: quick badge appends its id --------------------------------
        driver.click(win.rect.x + THIRD_BADGE[0],
                     win.rect.y + THIRD_BADGE[1])
        time.sleep(1.0)
        val2 = pattern_value(driver, dlg)
        rep.check("badge click appends id", val2 == "123", f"value={val2!r}")
        driver.capture(win).save_png(OUT / "cycle_badge.png")

        # --- #11: legal compatible patterns ---------------------------------
        legal_ok = True
        for pattern in ("23", "23,32"):
            got = set_pattern(driver, dlg, pattern)
            words = banner_text(driver, win, dlg)
            bad = any(e in words for e in ERRORS)
            enabled = ok_enabled(driver, win)
            rep.log(f"[INFO] {pattern!r}: stored={got!r} error={bad} "
                    f"ok={enabled}")
            legal_ok = legal_ok and got == pattern and not bad and enabled
        rep.check("legal patterns validate", legal_ok)

        # --- #14: unrecognized filament id ----------------------------------
        got = set_pattern(driver, dlg, "623")
        words = banner_text(driver, win, dlg)
        unk = "filament 6 not recognized" in words
        rep.check("unknown id blocked",
                  got == "623" and unk and not ok_enabled(driver, win),
                  f"value={got!r} banner={unk}")

        # --- #15: invalid characters / leading comma ------------------------
        set_pattern(driver, dlg, "2a3")
        words = banner_text(driver, win, dlg)
        invalid = "invalid characters" in words
        rep.check("invalid chars blocked",
                  invalid and not ok_enabled(driver, win),
                  f"banner={invalid}")
        set_pattern(driver, dlg, ",123")
        words = banner_text(driver, win, dlg)
        lead = "leading or trailing commas" in words
        rep.check("leading comma blocked",
                  lead and not ok_enabled(driver, win),
                  f"banner={lead}")

        # --- #13b: single filament advisory, not blocked --------------------
        set_pattern(driver, dlg, "2")
        words = banner_text(driver, win, dlg)
        single = "same filament colors" in words
        rep.check("single filament warns, not blocked",
                  single and ok_enabled(driver, win),
                  f"banner={single} ok={ok_enabled(driver, win)}")

        # --- #13a: empty normalizes back to 12 ------------------------------
        got = set_pattern(driver, dlg, "")
        rep.check("empty falls back to 12", got == "12", f"value={got!r}")

        # --- 512 cap: real edits only (AXSetValue bypasses MaxLength) -------
        set_pattern(driver, dlg, "")
        fld = pattern_field(driver, dlg)
        paste(driver, "2" * 512, fld)
        len1 = len(pattern_value(driver, dlg))
        fld = pattern_field(driver, dlg)
        paste(driver, "2" * 20, fld, select_all=False)
        len2 = len(pattern_value(driver, dlg))
        rep.check("input capped at 512", len1 == 512 and len2 == 512,
                  f"after512={len1} after20more={len2}")
        driver.capture(win).save_png(OUT / "cycle_cap.png")

        driver.click(win.rect.x + CANCEL_BTN[0], win.rect.y + CANCEL_BTN[1])
        time.sleep(1.5)
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
        exit_code = rep.save({"covered": ["#80"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
