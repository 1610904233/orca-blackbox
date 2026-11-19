#!/usr/bin/env python3
# m3x_mixing_match.py — macOS port: Feishu #82/#83/#84 Add Mix Match mode.
# feishu: baseline#82 baseline#83 baseline#84  (macOS port; corresponds to the
#         enabled Windows m3x_mixing_match, registered in
#         cases.MACOS_BASELINE)
#
# Windows assertions:
#   Match tab presentation (Target Color / Hex / Min Mix Ratio), default hex,
#   invalid hex blocked, a valid hex clears the error and recomputes recipes
#   within 6s, the min-ratio slider changes the value text, the stock color
#   picker updates the target, OK registers the scheme, and the entry
#   re-opens in Match mode with a valid hex.
#
# macOS mapping:
#   Match tab    -> (624,105); the only AXTextField is the 6-digit hex.
#   validation   -> AXSetValue + AXConfirm; error banner OCR + OK button fill
#                   (teal enabled / grey disabled).
#   min ratio    -> the track sits on the OCR 'Min Mix Ratio' row; clicks at
#                   x 645/556 change 15% -> 45% -> 1%.
#   color picker -> the target swatch (label x+61, label.y+40) opens the
#                   native 'Colors' panel.  Its AXTextField identifier='hex'
#                   accepts a new value; closing the panel applies it.
#   register     -> OK; sidebar labels with '%' grow by one.
#   re-open      -> click the new label, 'Edit Mix' stays in Match and its hex
#                   is a valid 6-digit value (the target itself is recomputed,
#                   same caveat as Windows #29).
#
# Artifacts: artifacts/mac/pilot/m3x/{report.log,result.json,*.png}.

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

import ApplicationServices as AS  # noqa: E402

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos import _ax_perform, _ax_set  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m3x"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
ADD_BTN = (388, 521)
MATCH_TAB = (624, 105)
OK_BTN = (672, 709)
CANCEL_BTN = (488, 709)
HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")


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


def find_word(driver, win, dlg, needle):
    for w in dlg_words(driver, win, dlg):
        if needle.lower() in w.text.lower():
            return w
    return None


def entry_labels(driver, win):
    return [(w.text.strip(), w.rect) for w in recognize_text(driver.capture(win))
            if w.rect.x < 330 and 530 < w.rect.y < 690
            and re.search(r"\d+%", w.text)]


def hex_field(driver, dlg):
    return next((c for c in driver.controls(dlg)
                 if c.role == "AXTextField" and c.handle is not None), None)


def field_value(driver, dlg) -> str:
    fld = hex_field(driver, dlg)
    return str(fld.value) if fld is not None else ""


def set_hex(driver, dlg, text: str) -> str:
    fld = hex_field(driver, dlg)
    if fld is None:
        return ""
    _ax_set(fld.handle, AS.kAXValueAttribute, text)
    time.sleep(0.3)
    if "AXConfirm" in (fld.actions or ()):
        _ax_perform(fld.handle, "AXConfirm")
    time.sleep(1.0)
    return field_value(driver, dlg)


def ok_enabled(driver, win) -> bool:
    frame = driver.capture(win)
    sx = frame.width / 1200.0
    sy = frame.height / 800.0
    r, g, b, _a = frame.pixel(int(OK_BTN[0] * sx), int(OK_BTN[1] * sy))
    return g > 100 and g > r + 20


def percent_texts(driver, win, dlg):
    return [w.text.strip() for w in dlg_words(driver, win, dlg)
            if re.search(r"\d+%", w.text)]


def min_ratio_text(driver, win, dlg, label):
    out = []
    for w in dlg_words(driver, win, dlg):
        if (re.fullmatch(r"\d{1,3}%", w.text.strip())
                and abs(w.rect.y - label.rect.y) <= 6
                and w.rect.x > label.rect.x + label.rect.w + 20):
            out.append(w.text.strip())
    return out[0] if out else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)

    rep = Reporter(OUT)
    rep.log("=== m3x macOS Match mode ===")
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
        rep.log(f"[INFO] base entries={[(t, r.to_xywh()) for t, r in base]}")
        rep.check("seeded entry present", len(base) >= 1,
                  f"entries={[t for t, _r in base]}")

        driver.click(win.rect.x + ADD_BTN[0], win.rect.y + ADD_BTN[1])
        time.sleep(1.5)
        dlg = mix_window(driver, app, win, "add mix")
        rep.check("add mix dialog opens", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({"stage": "dialog"})
        driver.click(win.rect.x + MATCH_TAB[0], win.rect.y + MATCH_TAB[1])
        time.sleep(1.2)

        # --- #21: Match presentation ---------------------------------------
        words = " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()
        labels = [s for s in ("target color", "hex", "min mix ratio")
                  if s in words]
        rep.check("match labels present", len(labels) >= 2, f"labels={labels}")
        hex0 = field_value(driver, dlg)
        rep.check("hex input 6 hex chars", bool(HEX_RE.match(hex0)),
                  f"hex={hex0!r}")
        driver.capture(win).save_png(OUT / "match_default.png")

        # --- #26: invalid hex blocks ---------------------------------------
        got = set_hex(driver, dlg, "GGGGGG")
        words = " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()
        err = "valid 6-digit hex" in words
        rep.check("letters rejected",
                  got == "GGGGGG" and err and not ok_enabled(driver, win),
                  f"stored={got!r} err={err} ok={ok_enabled(driver, win)}")
        set_hex(driver, dlg, "FF573")
        words = " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()
        err5 = "valid 6-digit hex" in words
        rep.check("5 digits rejected",
                  err5 and not ok_enabled(driver, win),
                  f"err={err5} ok={ok_enabled(driver, win)}")

        # --- #22: valid hex recomputes within 6s ---------------------------
        before_vals = percent_texts(driver, win, dlg)
        got = set_hex(driver, dlg, "FF5733")
        deadline = time.monotonic() + 6.0
        ready = False
        while time.monotonic() < deadline:
            words = " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()
            if "valid 6-digit hex" not in words and ok_enabled(driver, win):
                ready = True
                break
            time.sleep(0.4)
        after_vals = percent_texts(driver, win, dlg)
        rep.check("valid hex computes within 6s",
                  ready and got == "FF5733", f"stored={got!r} ready={ready}")
        rep.check("recipe values update", after_vals != before_vals,
                  f"{before_vals} -> {after_vals}")
        driver.capture(win).save_png(OUT / "match_valid.png")

        # --- #23: min-ratio slider is live ---------------------------------
        label = find_word(driver, win, dlg, "min mix ratio")
        moved = False
        if label is not None:
            y = int(label.rect.y + label.rect.h / 2)
            v0 = min_ratio_text(driver, win, dlg, label)
            driver.click(win.rect.x + 645, win.rect.y + y)
            time.sleep(0.8)
            v1 = min_ratio_text(driver, win, dlg, label)
            driver.click(win.rect.x + 556, win.rect.y + y)
            time.sleep(0.8)
            v2 = min_ratio_text(driver, win, dlg, label)
            moved = bool(v1 and v2 and v1 != v0 and v2 != v1)
            rep.log(f"[INFO] min ratio {v0!r} -> {v1!r} -> {v2!r}")
        rep.check("min-ratio slider live", moved)

        # --- #25: native Colors panel updates the target -------------------
        target = find_word(driver, win, dlg, "target color")
        picker_ok = False
        if target is not None:
            driver.click(win.rect.x + int(target.rect.x + 61),
                         win.rect.y + int(target.rect.y + 40))
            time.sleep(1.5)
            panel = next((w for w in driver.windows_for_pid(app.pid)
                          if w.on_screen and (w.title or "").lower() == "colors"),
                         None)
            rep.check("color picker opens", panel is not None,
                      panel.rect.to_xywh() if panel else "")
            if panel is not None:
                hexf = next((c for c in driver.controls(panel)
                             if c.role == "AXTextField"
                             and c.identifier == "hex"), None)
                if hexf is not None and hexf.handle is not None:
                    _ax_set(hexf.handle, AS.kAXValueAttribute, "33AAFF")
                    time.sleep(0.3)
                    _ax_perform(hexf.handle, "AXConfirm")
                    time.sleep(0.4)
                    driver.send_key("return")
                    time.sleep(0.8)
                driver.click(panel.rect.x + 12, panel.rect.y + 12)
                time.sleep(1.5)
                got = field_value(driver, dlg)
                picker_ok = got.upper() == "33AAFF"
                rep.log(f"[INFO] hex after picker={got!r}")
        rep.check("picker updates target", picker_ok)
        rep.check("OK enabled after picker", ok_enabled(driver, win))
        driver.capture(win).save_png(OUT / "match_picked.png")
        if not picker_ok:
            return rep.save({"stage": "picker"})

        # --- #28: OK registers the scheme ----------------------------------
        driver.click(win.rect.x + OK_BTN[0], win.rect.y + OK_BTN[1])
        gone = False
        for _ in range(6):
            time.sleep(1.0)
            if mix_window(driver, app, win, "add mix") is None:
                gone = True
                break
        after = entry_labels(driver, win)
        rep.log(f"[INFO] entries after OK={[t for t, _r in after]}")
        registered = gone and len(after) == len(base) + 1
        rep.check("match scheme registered", registered,
                  f"gone={gone} {len(base)} -> {len(after)}")
        if not registered:
            return rep.save({"stage": "register"})
        new = [e for e in after if e[0] not in {t for t, _r in base}]
        if not new:
            return rep.save({"stage": "label"})

        # --- #29: the entry re-opens in Match with a valid hex -------------
        _label, rect = new[0]
        driver.click(win.rect.x + rect.center[0],
                     win.rect.y + rect.center[1])
        time.sleep(2.0)
        edlg = mix_window(driver, app, win, "edit mix")
        rep.check("entry reopens (Edit Mix)", edlg is not None,
                  edlg.rect.to_xywh() if edlg else "")
        if edlg is not None:
            words = " ".join(w.text for w in dlg_words(driver, win, edlg)).lower()
            rep.check("entry reopens in match",
                      "target color" in words and "min mix ratio" in words,
                      words[:120])
            hex3 = field_value(driver, edlg)
            rep.check("target hex valid", bool(HEX_RE.match(hex3)),
                      f"hex={hex3!r}")
            driver.capture(win).save_png(OUT / "edit_reopen.png")
            driver.click(win.rect.x + CANCEL_BTN[0],
                         win.rect.y + CANCEL_BTN[1])
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
        exit_code = rep.save({"covered": ["#82", "#83", "#84"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
