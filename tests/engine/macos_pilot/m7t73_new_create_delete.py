#!/usr/bin/env python3
# m7t73_new_create_delete.py — macOS port: Feishu #73 main-flow template.
# feishu: none  (macOS port; corresponds to the enabled Windows m7t73,
#         registered in cases.MACOS_BASELINE)
#
# O-01 open -> O-05 new project -> M-20 add primitive -> M-19 Delete All
# -> O-02 close.
#
# macOS equivalents:
#   empty boot             -> launch without model; viewport chromatic ~0
#   New Project            -> AXPress "New Project" (no prompt when clean)
#   Add Primitive > Cube   -> bed right-click + AXPress context "Cube"
#   Delete All             -> AXPress the Edit-menu "Delete All"
#
# Artifacts: artifacts/mac/pilot/m7t73/{*.png,report.log,result.json}.

from __future__ import annotations

import argparse
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]       # repo root
ENGINE = Path(__file__).resolve().parents[1]     # tests/engine
PILOTS = Path(__file__).resolve().parent        # tests/engine/macos_pilot
for path in (str(HERE), str(ENGINE), str(PILOTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import m7b_new_project as m7b  # noqa: E402  (reuse Add Cube / save prompt)

OUT = ARTIFACTS / "pilot" / "m7t73"
EMPTY_BED_MAX = 0.015


def _new_project(driver, app, win) -> tuple[bool, bool]:
    """Dispatch New Project; return (dispatched, save_prompt_handled)."""
    item = driver.find_control(win, role="AXMenuItem",
                               title="New Project", timeout_s=3)
    if item is None or not item.enabled:
        return False, True
    dispatched = driver.click_control(item)
    time.sleep(2.0)
    dlg = m7b._save_dialog(driver, app, win)
    handled = True
    if dlg is not None:
        crop = driver.capture_screen().crop(dlg.rect)
        words = recognize_text(crop)
        handled = m7b._click_dialog_word(driver, dlg, words, "No")
        time.sleep(2.0)
    return dispatched, handled


def _delete_all(driver, win) -> bool:
    item = driver.find_control(win, role="AXMenuItem",
                               title="Delete All", timeout_s=3)
    if item is None:
        return False
    pressed = driver.click_control(item)
    time.sleep(2.0)
    return pressed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    rep = Reporter(OUT)
    rep.log("=== m7t73 macOS new/create/delete (#73) ===")
    rep.log(f"datadir={args.datadir}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=None,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"blockers={app.extra.get('blockers')}")
        time.sleep(2.0)

        boot = driver.capture(win)
        boot.save_png(OUT / "boot.png")
        vp_boot = m7b._vp_colored(boot)
        rep.check("empty bed at boot", vp_boot < EMPTY_BED_MAX,
                  f"viewport={vp_boot:.4f}")

        dispatched, handled = _new_project(driver, app, win)
        rep.check("new project dispatches", dispatched and handled,
                  f"dispatched={dispatched} save_prompt_handled={handled}")
        plate = driver.capture(win)
        plate.save_png(OUT / "after_new.png")
        vp_new = m7b._vp_colored(plate)
        rep.check("plate still empty", vp_new < EMPTY_BED_MAX,
                  f"viewport={vp_new:.4f}")

        added = m7b._add_cube(driver, app, win)
        created = driver.capture(win)
        created.save_png(OUT / "after_add_cube.png")
        vp_add = m7b._vp_colored(created)
        title_add = driver._refresh(win).title
        diff_add = plate.difference(created)
        rep.check("model created (M-20)",
                  added and (title_add.startswith("*")
                             or vp_add > vp_new + 0.002
                             or diff_add > 0.002),
                  f"added={added} title={title_add!r} "
                  f"viewport={vp_add:.4f} diff={diff_add:.4f}")

        deleted = _delete_all(driver, win)
        emptied = driver.capture(win)
        emptied.save_png(OUT / "after_delete_all.png")
        vp_del = m7b._vp_colored(emptied)
        rep.check("Delete All empties again", deleted and vp_del < EMPTY_BED_MAX,
                  f"pressed={deleted} viewport={vp_del:.4f}")

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
