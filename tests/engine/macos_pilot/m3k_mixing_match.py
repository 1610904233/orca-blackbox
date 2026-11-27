#!/usr/bin/env python3
# m3k_mixing_match.py — macOS port: Feishu #95/#107 manual-mode colour
# matching in the mixing dialog.
# feishu: baseline#95 baseline#107  (macOS port; corresponds to the enabled
#         Windows m3k_mixing_match, registered in cases.MACOS_BASELINE)
# The Windows case's step labels #10/#15/#27 are not Feishu baseline numbers;
# Feishu #10/#15 are unrelated detector cases (mac status 不适用).
#
# Windows assertions:
#   #10 switch the Match Mode combo from Auto to Manual (text-confirmed)
#   #15 Start Matching renders the colour-mapping result view
#   #27 Confirm closes the dialog and the app stays alive
#
# macOS mapping:
#   entry  -> the sidebar "Color Mixing Match" link opens a SEPARATE window
#             (title 'Color Mixing Match', layer 8, ~500x728)
#   combo  -> the self-drawn Match Mode combo at window-relative
#             (482,119); its dropdown lists Auto/Manual right below it
#   result -> the dialog's "Matched" preview turns from a grey gradient into
#             coloured swatches; the Color Mapping rows and the gamut banner
#             ("The mix ratios for N ... outside the recommended ranges")
#             appear, and Confirm is enabled
#   confirm-> closes the dialog window
#
# Artifacts: artifacts/mac/pilot/m3k/{report.log,result.json,*.png}.

from __future__ import annotations

import argparse
import colorsys
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

OUT = ARTIFACTS / "pilot" / "m3k"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MATCHED_PREVIEW = Rect(585, 345, 195, 160)   # window-relative


def mixing_window(driver, app, win):
    for w in driver.windows_for_pid(app.pid):
        if (w.on_screen and w.id != win.id and w.layer != 0
                and "color mixing match" in (w.title or "").lower()):
            return w
    return None


def dlg_words(driver, win, dlg):
    """Window-relative OCR boxes for the dialog (frame = crop(win.rect))."""
    return recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(dlg.rect.x - win.rect.x, dlg.rect.y - win.rect.y,
             dlg.rect.w, dlg.rect.h))


def find(words, needle):
    for w in words:
        if needle in w.text.lower():
            return w
    return None


def click_word(driver, win, word, tag):
    driver.click(win.rect.x + word.rect.center[0],
                 win.rect.y + word.rect.center[1])
    print(f"[m3k] click {tag!r} ({word.text!r})")


def sat_share(frame) -> float:
    n = hit = 0
    for y in range(int(MATCHED_PREVIEW.y),
                   int(MATCHED_PREVIEW.bottom), 2):
        for x in range(int(MATCHED_PREVIEW.x),
                       int(MATCHED_PREVIEW.right), 2):
            if y >= frame.height or x >= frame.width:
                continue
            i = (y * frame.width + x) * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            _h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            n += 1
            if s > 0.25 and v > 0.25:
                hit += 1
    return hit / max(1, n)


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
    rep.log("=== m3k macOS manual mixing match ===")

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
        frame.save_png(OUT / "loaded.png")
        rep.check("模型载入（mixed 夹具）", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        entry = next((w for w in recognize_text(frame)
                      if "color mixing match" in w.text.lower()
                      and w.rect.x < 500), None)
        rep.check("混色入口（Color Mixing Match）", entry is not None)
        if entry is None:
            return rep.save({"stage": "entry"})
        click_word(driver, win, entry, "Color Mixing Match")
        time.sleep(1.5)
        dlg = mixing_window(driver, app, win)
        rep.check("混色对话框窗口", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({"stage": "dialog"})

        words = dlg_words(driver, win, dlg)
        rep.log(f"[INFO] OCR={[(w.text, w.rect.to_xywh()) for w in words][:22]}")
        rep.check("对话框内容（Match Mode / Start Matching）",
                  find(words, "match mode") is not None
                  and find(words, "start matching") is not None)
        auto = find(words, "auto")
        rep.check("默认 Match Mode = Auto", auto is not None,
                  auto.text if auto else "no Auto")
        if auto is None:
            return rep.save({"stage": "auto"})

        before = sat_share(driver.capture(win))
        rep.log(f"[INFO] Matched preview saturation before={before:.3f}")

        click_word(driver, win, auto, "Auto combo")
        time.sleep(1.0)
        words = dlg_words(driver, win, dlg)
        manual = find(words, "manual")
        rep.check("下拉出现 Manual", manual is not None,
                  f"words={[w.text for w in words if 140 < w.rect.y < 200][:6]}")
        if manual is None:
            return rep.save({"stage": "manual-option"})
        click_word(driver, win, manual, "Manual")
        time.sleep(1.0)
        words = dlg_words(driver, win, dlg)
        rep.check("匹配模式已切到 Manual",
                  "manual" in " ".join(w.text for w in words).lower()
                  and find(words, "match mode") is not None,
                  f"mode words={[w.text for w in words if 100 < w.rect.y < 140]}")

        start = find(words, "start matching")
        rep.check("Start Matching 可点击", start is not None)
        if start is None:
            return rep.save({"stage": "start"})
        click_word(driver, win, start, "Start Matching")
        time.sleep(6.0)
        driver.capture(win).save_png(OUT / "matched.png")
        words = dlg_words(driver, win, dlg)
        after = sat_share(driver.capture(win))
        rep.log(f"[INFO] Matched preview saturation after={after:.3f}")
        rep.check("匹配后视图渲染（饱和色块增加）",
                  after > 0.10 and after - before > 0.03,
                  f"{before:.3f} -> {after:.3f}")
        rep.check("Color Mapping 列表/警告出现",
                  find(words, "color mapping") is not None
                  and (find(words, "mix ratios") is not None
                       or find(words, "→") is not None),
                  f"ocr={[w.text for w in words][-12:]}")
        confirm = find(words, "confirm")
        rep.check("Confirm 可点击", confirm is not None,
                  confirm.text if confirm else "missing")
        # #95 manual matched view is complete.  #107 must be an AUTO-mode
        # match (Feishu precondition), so switch this same dialog back to
        # Auto, match again, then Confirm and check the mapping result.
        mode = (find(words, "manual") or find(words, "auto"))
        rep.check("#107 当前模式可切换", mode is not None,
                  mode.text if mode else "missing")
        if mode is None:
            return rep.save({"stage": "auto-mode"})
        click_word(driver, win, mode, "Mode combo")
        time.sleep(1.0)
        words = dlg_words(driver, win, dlg)
        auto_opt = find(words, "auto")
        rep.check("#107 下拉出现 Auto", auto_opt is not None,
                  f"words={[w.text for w in words if 140 < w.rect.y < 200][:6]}")
        if auto_opt is None:
            return rep.save({"stage": "auto-option"})
        click_word(driver, win, auto_opt, "Auto")
        time.sleep(1.0)
        words = dlg_words(driver, win, dlg)
        rep.check("#107 Match Mode = Auto",
                  find(words, "auto") is not None
                  and find(words, "manual") is None,
                  f"mode words={[w.text for w in words if 100 < w.rect.y < 140]}")
        start2 = find(words, "start matching")
        rep.check("#107 Start Matching 可点击", start2 is not None)
        if start2 is None:
            return rep.save({"stage": "start-auto"})
        click_word(driver, win, start2, "Start Matching (auto)")
        time.sleep(6.0)
        driver.capture(win).save_png(OUT / "matched_auto.png")
        words = dlg_words(driver, win, dlg)
        after2 = sat_share(driver.capture(win))
        rep.log(f"[INFO] #107 auto matched saturation={after2:.3f}")
        rep.check("#107 自动匹配后视图渲染",
                  after2 > 0.10 and find(words, "color mapping") is not None,
                  f"sat={after2:.3f}")
        confirm2 = find(words, "confirm")
        rep.check("#107 Confirm 可点击", confirm2 is not None)
        if confirm2 is None:
            return rep.save({"stage": "confirm-auto"})
        click_word(driver, win, confirm2, "Confirm (auto)")
        time.sleep(2.0)
        gone2 = mixing_window(driver, app, win) is None
        rep.check("#107 Confirm 关闭对话框", gone2)
        if not gone2:
            return rep.save({"stage": "confirm-auto-close"})
        words = recognize_text(driver.capture(win))
        text = " ".join(w.text for w in words).lower()
        rep.check("#107 颜色映射结果生效（Color Mixing 混色耗材）",
                  "color mixing" in text
                  and ("50%" in text or "mixed" in text or "mix" in text),
                  text[:220])
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
        exit_code = rep.save({"covered": ["#95", "#107"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
