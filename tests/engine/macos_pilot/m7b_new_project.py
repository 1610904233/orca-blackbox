#!/usr/bin/env python3
# m7b_new_project.py — macOS port: Feishu #9 new project clears the model.
# feishu: none  (macOS port; corresponds to the enabled Windows
#         m7b_new_project, registered in cases.MACOS_BASELINE)
#
# Windows flow -> macOS equivalents:
#   load mixed fixture            -> launch --model
#   dirty via Add Primitive>Cube  -> bed right-click, AXPress the context-menu
#                                    "Cube" AXMenuItem (real menu clicks are
#                                    unreliable, AX works)
#   File > New Project            -> AXPress the "New Project" menu item
#   save prompt (Yes/No/Cancel)   -> "Snapmaker Orca - Save" dialog, OCR "No"
#   viewport empty                -> viewport chromatic fraction drops
#
# Artifacts: artifacts/mac/pilot/m7b/{*.png,report.log,result.json}.

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

import numpy as np  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import (  # noqa: E402
    find_text, joined_text, recognize_text,
)
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m7b"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
VIEWPORT = (430, 100, 1080, 700)  # x0,y0,x1,y1 clean 3D viewport crop
EMPTY_BED_MAX = 0.015


def _vp_colored(frame) -> float:
    arr = np.frombuffer(frame.data, dtype=np.uint8).reshape(
        frame.height, frame.width, 4)
    b = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    r = arr[:, :, 2].astype(int)
    spread = np.maximum(np.maximum(b, g), r) - np.minimum(np.minimum(b, g), r)
    x0, y0, x1, y1 = VIEWPORT
    return float((spread[y0:y1, x0:x1] > 24).mean())


def _add_cube(driver, app, win) -> bool:
    """Bed right-click -> AXPress the context-menu Cube item."""
    driver.click(win.rect.x + 1000, win.rect.y + 300, button="right")
    time.sleep(1.0)
    for attempt in range(2):
        for w in driver.windows_for_pid(app.pid):
            if w.id == win.id or not w.on_screen or w.rect.area < 1000:
                continue
            try:
                for c in driver.controls(w):
                    if (c.role == "AXMenuItem"
                            and "cube" in (c.title + " " + c.description).lower()):
                        print(f"[m7b] AXPress Cube (id={w.id})")
                        driver.click_control(c)
                        time.sleep(1.2)
                        return True
            except Exception:
                continue
        # The submenu may not be materialised until Add Primitive is clicked.
        words = recognize_text(driver.capture(win))
        add = find_text(words, "add primitive")
        if add is None:
            break
        driver.click(win.rect.x + add.rect.center[0],
                     win.rect.y + add.rect.center[1])
        time.sleep(0.8)
    return False


def _save_dialog(driver, app, win):
    for w in driver.windows_for_pid(app.pid):
        if w.id == win.id or not w.on_screen or w.rect.area < 1000:
            continue
        if "save" in (w.title or "").lower():
            return w
    return None


def _click_dialog_word(driver, dlg, words, label: str) -> bool:
    word = next((w for w in words
                 if w.text.strip().lower() == label.lower()), None)
    if word is None:
        return False
    driver.click(dlg.rect.x + word.rect.center[0],
                 dlg.rect.y + word.rect.center[1])
    return True


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
    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    rep = Reporter(OUT)
    rep.log("=== m7b macOS new-project (#9) ===")
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
        before_vp = _vp_colored(frame)
        rep.check("model arrives", loaded,
                  f"colored_fraction={frac:.4f} viewport={before_vp:.4f}")

        added = _add_cube(driver, app, win)
        dirty_title = driver._refresh(win).title
        rep.check("project dirtied (add cube)",
                  added and dirty_title.startswith("*"),
                  f"added={added} title={dirty_title!r}")

        proj = driver.find_control(win, role="AXMenuItem",
                                   title="New Project", timeout_s=3)
        rep.check("New Project menu found",
                  proj is not None and proj.enabled,
                  f"found={proj is not None}")
        if proj is None:
            raise RuntimeError("New Project menu item unavailable")
        driver.click_control(proj)
        time.sleep(1.5)

        dlg = _save_dialog(driver, app, win)
        rep.check("new project dispatches", dlg is not None,
                  f"dialog={dlg.title if dlg else None}")
        if dlg is None:
            raise RuntimeError("save prompt did not appear")

        crop = driver.capture_screen().crop(dlg.rect)
        crop.save_png(OUT / "save_dialog.png")
        words = recognize_text(crop)
        rep.log(f"[INFO] save prompt OCR: {joined_text(words)[:300]}")
        prompt_ok = (find_text(words, "unsaved changes") is not None
                     or find_text(words, "would you like to save") is not None)
        rep.check("save prompt appears", prompt_ok)
        clicked = _click_dialog_word(driver, dlg, words, "No")
        rep.check("save prompt handled (don't save)", clicked)
        time.sleep(2.5)

        after = driver.capture(win)
        after.save_png(OUT / "after_new_project.png")
        after_vp = _vp_colored(after)
        rep.log(f"[INFO] after No: title={driver._refresh(win).title!r} "
                f"viewport {before_vp:.4f}->{after_vp:.4f}")
        empty_ok = (after_vp < EMPTY_BED_MAX
                    and after_vp < before_vp * 0.3)
        rep.check("viewport empty (model cleared)", empty_ok,
                  f"viewport={after_vp:.4f} (before={before_vp:.4f})")

        # A parameter-edit dirty route would raise a settings-transfer dialog;
        # the Add-Cube route should not.  Record any unexpected modal.
        extra = [w for w in driver.windows_for_pid(app.pid)
                 if w.id != win.id and w.on_screen and w.rect.area > 10000]
        rep.log(f"[INFO] extra on-screen windows: "
                f"{[(w.id, w.title, w.rect.to_xywh()) for w in extra]}")
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
