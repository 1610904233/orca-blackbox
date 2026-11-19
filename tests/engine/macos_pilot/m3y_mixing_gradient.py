#!/usr/bin/env python3
# m3y_mixing_gradient.py — macOS port: Feishu #82/#83/#84 Add Mix Gradient.
# feishu: baseline#82 baseline#83 baseline#84  (macOS port; corresponds to the
#         enabled Windows m3y_mixing_gradient, registered in
#         cases.MACOS_BASELINE)
#
# Windows assertions:
#   - the Gradient tab shows two rows and the Mix Effect card (no Ratio bar)
#   - switching a row repaints the gradient preview
#   - OK registers a scheme; the default label is 'F3->F2'
#   - re-opening the entry stays in Gradient
#   - the swap-direction button flips the label to 'F2->F3'
#   - Cancel registers nothing
#
# macOS mapping:
#   Add Mix from the teal + at (388,521); Gradient tab at (710,105).
#   Compatible pair: row 1 combo (566,255) -> a PLA option (558,321).
#   After the banner clears the rows sit at y 217/259 and the Mix Effect
#   header at (452,331).  The direction-swap AXButton is centred at
#   window-relative (734,186); clicking it flips F3->F2 to F2->F3 on OK.
#   Preview repaint is measured as a pixel-diff over the Mix Effect card.
#
# Artifacts: artifacts/mac/pilot/m3y/{report.log,result.json,*.png}.

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

OUT = ARTIFACTS / "pilot" / "m3y"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
ADD_BTN = (388, 521)
GRADIENT_TAB = (710, 105)
MIX_EFFECT = Rect(445, 340, 210, 125)   # window-relative preview card


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
            if w.rect.x < 330 and 530 < w.rect.y < 660
            and ("->" in w.text or "%" in w.text)]


def crop_diff(a, b, rect) -> float:
    n = changed = 0
    for y in range(int(rect.y), int(rect.bottom), 2):
        for x in range(int(rect.x), int(rect.right), 2):
            if y >= a.height or x >= a.width:
                continue
            i = (y * a.width + x) * 4
            n += 1
            if (abs(a.data[i] - b.data[i]) > 8
                    or abs(a.data[i + 1] - b.data[i + 1]) > 8
                    or abs(a.data[i + 2] - b.data[i + 2]) > 8):
                changed += 1
    return changed / max(1, n)


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
    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m3y macOS Gradient tab ===")

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
        ok, _f, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        rep.check("multicolor project loads", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})
        base = labels(driver, win)
        rep.check("seeded entry present", len(base) >= 1,
                  f"entries={[t for t, _r in base]}")

        base_labels = {t for t, _r in base}

        # --- A: default Gradient registration (F3->F2) ---------------------
        driver.click(win.rect.x + ADD_BTN[0], win.rect.y + ADD_BTN[1])
        time.sleep(1.5)
        dlg = mix_window(driver, app, win, "add mix")
        rep.check("add mix dialog opens", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({"stage": "dialog"})
        driver.click(win.rect.x + GRADIENT_TAB[0], win.rect.y + GRADIENT_TAB[1])
        time.sleep(1.5)
        ws = dlg_words(driver, win, dlg)
        text = " ".join(w.text for w in ws).lower()
        rep.check("gradient tab switches", "mix effect" in text
                  and "mixing ratio" not in text, text[:120])
        rows = [w for w in ws if "pla" in w.text.lower()
                or "petg" in w.text.lower()]
        rep.check("gradient forces 2 rows", len(rows) == 2,
                  f"rows={[(w.text, w.rect.y) for w in rows]}")
        rep.check("mix effect card present", "mix effect" in text,
                  "Mix Effect" if "mix effect" in text else "missing")
        rep.check("compatible rows selectable", make_compatible(driver, win, dlg))
        driver.capture(win).save_png(OUT / "gradient.png")
        driver.click(win.rect.x + 672, win.rect.y + 707)   # OK
        time.sleep(2.0)
        ents = labels(driver, win)
        new = [e for e in ents if e[0] not in base_labels and "->" in e[0]]
        rep.log(f"[INFO] entries after OK={[(t, r.to_xywh()) for t, r in ents]}")
        rep.check("gradient registers", len(ents) == len(base) + 1,
                  f"entries={[t for t, _r in ents]}")
        rep.check("default label F3->F2", bool(new) and new[0][0] == "F3->F2",
                  f"label={new[0][0] if new else None}")
        if not new:
            return rep.save({"stage": "register"})
        label, rect = new[0]

        # --- B: row switch repaints the gradient (Cancel, no registration) --
        driver.click(win.rect.x + ADD_BTN[0], win.rect.y + ADD_BTN[1])
        time.sleep(1.5)
        dlg2 = mix_window(driver, app, win, "add mix")
        rep.check("再次打开 Add Mix", dlg2 is not None)
        if dlg2 is not None:
            driver.click(win.rect.x + GRADIENT_TAB[0],
                         win.rect.y + GRADIENT_TAB[1])
            time.sleep(1.0)
            rep.check("第二次兼容行选择", make_compatible(driver, win, dlg2))
            before = driver.capture(win)
            driver.click(win.rect.x + 570, win.rect.y + 217)
            time.sleep(1.0)
            ws = dlg_words(driver, win, dlg2)
            opts = [w for w in ws if "pla" in w.text.lower()
                    and w.rect.y > 235]
            opt = max(opts, key=lambda w: w.rect.y) if opts else None
            rep.log(f"[INFO] row switch option={opt.text if opt else None}")
            if opt is not None:
                driver.click(win.rect.x + opt.rect.center[0],
                             win.rect.y + opt.rect.center[1])
                time.sleep(1.2)
            after = driver.capture(win)
            diff = crop_diff(before, after, MIX_EFFECT)
            rep.log(f"[INFO] Mix Effect diff after row switch={diff:.4f}")
            rep.check("row switch repaints gradient", diff > 0.01,
                      f"diff={diff:.4f}")
            driver.click(win.rect.x + 488, win.rect.y + 709)   # Cancel
            time.sleep(1.5)
        ents_cancel = labels(driver, win)
        rep.check("cancel registers nothing", len(ents_cancel) == len(ents),
                  f"{len(ents)} -> {len(ents_cancel)}")

        # --- C: Edit Mix -> swap direction -> F2->F3 -----------------------
        driver.click(win.rect.x + rect.center[0], win.rect.y + rect.center[1])
        time.sleep(1.5)
        edit = mix_window(driver, app, win, "edit mix")
        rep.check("edit stays in gradient", edit is not None)
        if edit is None:
            return rep.save({"stage": "edit"})
        ws = dlg_words(driver, win, edit)
        text = " ".join(w.text for w in ws).lower()
        rep.check("Edit Mix 为 Gradient 内容", "mix effect" in text
                  and "mixing ratio" not in text, text[:120])
        driver.click(win.rect.x + 734, win.rect.y + 186)
        time.sleep(1.2)
        driver.click(win.rect.x + 672, win.rect.y + 709)   # OK
        time.sleep(2.0)
        ents2 = labels(driver, win)
        rep.check("swap flips direction",
                  any(t == "F2->F3" for t, _r in ents2),
                  f"entries={[t for t, _r in ents2]}")

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
        exit_code = rep.save({"covered": ["#82", "#83", "#84"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
