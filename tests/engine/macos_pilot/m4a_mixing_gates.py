#!/usr/bin/env python3
# m4a_mixing_gates.py — macOS port: Feishu #31-#35 mixing entry gates.
# feishu: none  (macOS port; corresponds to the enabled Windows
#         m4a_mixing_gates, registered in cases.MACOS_BASELINE)
#
# Covered:
#   - #31 delete to 1: Color Mixing row hidden; entry pops the one-filament
#         prompt; batch dialog does NOT open; Got it dismisses
#   - #32 add back to 3: entry opens; Manual rows = 3; Cancel closes
#   - #33 add to 6: Manual rows clamp to 4; Cancel closes
#   - #34/#35 Phase B: standard 5-filament + scheme entry opens; Cancel
#
# Fixture note: Phase A uses the standard mixed fixture (scheme present) and
# handles the "Mixed Filament 4" delete Warning; the Windows case uses a
# crafted fixture with mixed definitions stripped to avoid that warning.
# The gated assertions are identical.
#
# Artifacts: artifacts/mac/pilot/m4a/{*.png,report.log,result.json}.

from __future__ import annotations

import argparse
import shutil
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

OUT = ARTIFACTS / "pilot" / "m4a"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
SIDEBAR = Rect(0, 390, 420, 210)
TRASH_XY = (369, 374)  # Filaments title-row middle icon, window-relative


def _count_materials(frame) -> tuple[int, list[str]]:
    words = recognize_text(frame, SIDEBAR)
    mats = [w.text for w in words
            if ("PLA" in w.text or "PETG" in w.text) and w.rect.x < 420]
    return len(mats), mats


def _warning_window(driver, app, main_win):
    for w in driver.windows_for_pid(app.pid):
        if w.id == main_win.id or not w.on_screen:
            continue
        if (w.title or "").lower() == "warning":
            return w
    return None


def _press_warning_ok(driver, warn_win) -> bool:
    frame = driver.capture_screen().crop(warn_win.rect)
    frame.save_png(OUT / f"warning_{warn_win.id}.png")
    words = recognize_text(frame)
    for label in ("OK", "Continue", "Yes"):
        word = next((w for w in words
                     if w.text.strip().lower() == label.lower()), None)
        if word is None:
            continue
        cx, cy = word.rect.center
        print(f"[m4a] click warning {label!r} at "
              f"({warn_win.rect.x + cx:.0f},{warn_win.rect.y + cy:.0f})")
        driver.click(warn_win.rect.x + cx, warn_win.rect.y + cy)
        time.sleep(1.0)
        return True
    print("[m4a] warning buttons OCR:", joined_text(words)[:300])
    return False


def _color_mixing_row_visible(driver, win) -> bool:
    try:
        for c in driver.controls(win):
            if c.role == "AXStaticText" and c.value == "Color Mixing":
                return True
    except Exception:
        pass
    return False


def _add_one(driver, win) -> None:
    driver.click(win.rect.x + 390, win.rect.y + 374)


def _wait_material_count(driver, win, want: int, timeout_s: float = 8.0):
    deadline = time.monotonic() + timeout_s
    last = -1
    while time.monotonic() < deadline:
        last, _mats = _count_materials(driver.capture(win))
        if last == want:
            return last
        time.sleep(0.5)
    return last


def _batch_windows(driver, app, main_win):
    return [w for w in driver.windows_for_pid(app.pid)
            if w.id != main_win.id and w.on_screen
            and "color mixing match" in (w.title or "").lower()
            and w.rect.h > 300]


def _manual_rows(frame) -> int:
    words = recognize_text(frame, Rect(380, 180, 460, 140))
    return sum(1 for w in words
               if any(k in w.text for k in ("PLA", "PETG", "Generic")))


def _open_manual(driver, win):
    """Entry -> batch dialog -> Match Mode Manual.  Returns (frame, words)."""
    frame = driver.capture(win)
    words = recognize_text(frame)
    entry = next((w for w in words
                  if "color mixing match" in w.text.lower()
                  and w.rect.x < 500), None)
    if entry is None:
        print("[m4a] entry not found for Manual step")
        return None
    driver.click(win.rect.x + entry.rect.center[0],
                 win.rect.y + entry.rect.center[1])
    time.sleep(1.5)
    frame2 = driver.capture(win)
    words2 = recognize_text(frame2)
    auto = find_text(words2, "auto")
    if auto is None:
        print("[m4a] Auto combo not found")
        return None
    driver.click(win.rect.x + auto.rect.center[0],
                 win.rect.y + auto.rect.center[1])
    time.sleep(0.8)
    screen = driver.capture_screen().crop(win.rect)
    manual = find_text(recognize_text(screen), "manual")
    if manual is None:
        print("[m4a] Manual popup item not found")
        return None
    driver.click(win.rect.x + manual.rect.center[0],
                 win.rect.y + manual.rect.center[1])
    time.sleep(1.2)
    frame3 = driver.capture(win)
    words3 = recognize_text(frame3)
    return frame3, words3


def _cancel_dialog(driver, app, win) -> bool:
    frame = driver.capture(win)
    words = recognize_text(frame)
    cancel = next((w for w in words
                   if w.text.strip() == "Cancel"
                   and w.rect.x > 400 and w.rect.y > 700), None)
    if cancel is None:
        print("[m4a] Cancel button not found")
        return False
    driver.click(win.rect.x + cancel.rect.center[0],
                 win.rect.y + cancel.rect.center[1])
    time.sleep(1.2)
    return not _batch_windows(driver, app, win)


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
    # Fresh profile: this pilot depends on the fixture's physical count (5).
    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    rep = Reporter(OUT)
    rep.log("=== m4a macOS mixing-gates (#31-#35) ===")
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
        frame.save_png(OUT / "before.png")
        rep.check("model loaded", loaded, f"colored_fraction={frac:.4f}")
        initial_n, initial_mats = _count_materials(frame)
        rep.check("initial filaments >= 2", initial_n >= 2,
                  f"count={initial_n} mats={initial_mats}")
        rep.check("Color Mixing row visible", _color_mixing_row_visible(driver, win))

        # --- Phase B (#34/#35): standard 5-filament + scheme entry ------
        phase_b = _open_manual(driver, win)
        if phase_b is None:
            rep.check("#34/#35 entry opens normally", False,
                      "Manual step not reached")
            rep.check("#34/#35 Cancel closes", False, "not reached")
        else:
            _fb, _wb = phase_b
            bwins = _batch_windows(driver, app, win)
            rep.check("#34/#35 entry opens normally", bool(bwins),
                      f"windows={[(w.id, w.rect.to_xywh()) for w in bwins]}")
            rep.check("#34/#35 Cancel closes",
                      _cancel_dialog(driver, app, win))

        # Delete physical filaments down to 1.  The standard mixed fixture
        # has a scheme, so deleting a referenced filament raises a Warning;
        # press OK and continue.
        for step in range(8):
            n, mats = _count_materials(driver.capture(win))
            if n <= 1:
                break
            print(f"[m4a] delete step {step + 1}: count={n} mats={mats}")
            driver.click(win.rect.x + TRASH_XY[0], win.rect.y + TRASH_XY[1])
            time.sleep(1.2)
            warn = _warning_window(driver, app, win)
            if warn is not None:
                print(f"[m4a] delete warning id={warn.id} "
                      f"rect={warn.rect.to_xywh()}")
                _press_warning_ok(driver, warn)
                time.sleep(1.0)
        final_n, final_mats = _count_materials(driver.capture(win))
        rep.check("deleted to one filament", final_n == 1,
                  f"count={final_n} mats={final_mats}")
        after_delete = driver.capture(win)
        after_delete.save_png(OUT / "after_delete.png")
        rep.check("Color Mixing row hidden at 1 filament",
                  not _color_mixing_row_visible(driver, win))

        # Entry -> one-filament prompt, batch dialog must NOT open.
        words = recognize_text(after_delete)
        entry = next((w for w in words
                      if "color mixing match" in w.text.lower()
                      and w.rect.x < 500), None)
        rep.check("entry found at 1 filament", entry is not None,
                  f"ocr={joined_text(words)[:200]}")
        if entry is None:
            raise RuntimeError("Color Mixing Match entry not found")
        cx, cy = entry.rect.center
        print(f"[m4a] click entry at ({win.rect.x + cx:.0f},{win.rect.y + cy:.0f})")
        driver.click(win.rect.x + cx, win.rect.y + cy)
        time.sleep(1.5)

        prompt_frame = driver.capture(win)
        prompt_frame.save_png(OUT / "prompt.png")
        pwords = recognize_text(prompt_frame)
        ptext = joined_text(pwords)
        has_gate = (find_text(pwords, "only one filament") is not None
                    or find_text(pwords, "unavailable") is not None)
        batch_wins = [w for w in driver.windows_for_pid(app.pid)
                      if w.id != win.id and w.on_screen
                      and "color mixing match" in (w.title or "").lower()
                      and w.rect.h > 300]
        rep.check("one-filament prompt appears", has_gate,
                  f"ocr={ptext[:400]}")
        rep.check("batch dialog NOT opened", not batch_wins,
                  f"windows={[(w.id, w.rect.to_xywh()) for w in batch_wins]}")

        got_it = find_text(pwords, "got it")
        rep.check("Got it found", got_it is not None)
        if got_it is not None:
            gx, gy = got_it.rect.center
            driver.click(win.rect.x + gx, win.rect.y + gy)
            time.sleep(1.2)
            after = driver.capture(win)
            after.save_png(OUT / "after_got_it.png")
            awords = recognize_text(after)
            prompt_gone = (find_text(awords, "only one filament") is None
                           and find_text(awords, "got it") is None)
            rep.check("prompt dismissable", prompt_gone,
                      f"ocr={joined_text(awords)[:250]}")
        else:
            rep.check("prompt dismissable", False, "Got it not found")

        # --- #32: add back to 3 -> Manual rows = 3 -> Cancel -------------
        n3, _ = _count_materials(driver.capture(win))
        for _ in range(8):
            if n3 >= 3:
                break
            _add_one(driver, win)
            n3 = _wait_material_count(driver, win, min(n3 + 1, 3))
        rep.check("#32 add back to 3", n3 == 3, f"count={n3}")
        manual3 = _open_manual(driver, win)
        if manual3 is None:
            rep.check("#32 Manual rows == 3", False, "Manual mode not reached")
            rep.check("#32 Cancel closes", False, "not reached")
        else:
            frame3, words3 = manual3
            rows3 = _manual_rows(frame3)
            is_manual = find_text(words3, "manual") is not None
            rep.check("#32 Manual rows == 3",
                      is_manual and rows3 == 3,
                      f"manual={is_manual} rows={rows3}")
            rep.check("#32 Cancel closes", _cancel_dialog(driver, app, win))

        # --- #33: add to 6 -> Manual rows clamp to 4 -> Cancel -----------
        n6, _ = _count_materials(driver.capture(win))
        for _ in range(8):
            if n6 >= 6:
                break
            _add_one(driver, win)
            n6 = _wait_material_count(driver, win, min(n6 + 1, 6))
        rep.check("#33 add to 6", n6 == 6, f"count={n6}")
        manual6 = _open_manual(driver, win)
        if manual6 is None:
            rep.check("#33 Manual rows clamp to 4", False,
                      "Manual mode not reached")
            rep.check("#33 Cancel closes", False, "not reached")
        else:
            frame6, words6 = manual6
            rows6 = _manual_rows(frame6)
            is_manual6 = find_text(words6, "manual") is not None
            rep.check("#33 Manual rows clamp to 4",
                      is_manual6 and rows6 == 4,
                      f"manual={is_manual6} rows={rows6}")
            rep.check("#33 Cancel closes", _cancel_dialog(driver, app, win))

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
        exit_code = rep.save({"partial": False,
                              "covered": ["#31 one-filament gate",
                                          "#32 add-3/manual rows",
                                          "#33 add-6/clamp",
                                          "#34/#35 Phase B"],
                              "fixture_note": "Phase A uses the standard mixed "
                                              "fixture with scheme (delete Warning "
                                              "handled); Windows uses a stripped "
                                              "fixture to avoid that warning"})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
