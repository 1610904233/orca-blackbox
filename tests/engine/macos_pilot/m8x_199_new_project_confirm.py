#!/usr/bin/env python3
# m8x_199_new_project_confirm.py — macOS port: Feishu #199 new-project confirm.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_199,
#         registered in cases.MACOS_BASELINE)
#
# Windows flow: load model -> dirty via Move X=40 -> File > New Project ->
# unsaved confirmation -> discard -> empty canvas + default title.
#
# macOS equivalent: load the mixed fixture -> dirty via Add Primitive > Cube
# (platform-equivalent dirty action; no gizmo dependency) -> New Project ->
# "Snapmaker Orca - Save" prompt -> OCR No -> empty viewport + "Untitled".
#
# Artifacts: artifacts/mac/pilot/m8x_199/{*.png,report.log,result.json}.

from __future__ import annotations

import argparse
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]       # repo root
ENGINE = Path(__file__).resolve().parents[1]     # tests/engine
PILOTS = Path(__file__).resolve().parent
for path in (str(HERE), str(ENGINE), str(PILOTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import (  # noqa: E402
    find_text, joined_text, recognize_text,
)
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)
import m7b_new_project as m7b  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_199"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
EMPTY_BED_MAX = 0.015


def _title(driver, win) -> str:
    return driver._refresh(win).title


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
    rep.log("=== m8x_199 macOS new-project confirmation ===")
    rep.log(f"datadir={args.datadir} model={args.model}")
    rep.log("[INFO] dirty action: Add Cube (platform-equivalent to Move X=40)")

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
        rep.check("载入模型", loaded, f"colored_fraction={frac:.4f}")

        added = m7b._add_cube(driver, app, win)
        dirty_title = _title(driver, win)
        rep.check("未保存改动（Add Cube）",
                  added and dirty_title.startswith("*"),
                  f"added={added} title={dirty_title!r}")

        proj = driver.find_control(win, role="AXMenuItem",
                                   title="New Project", timeout_s=3)
        if proj is None:
            rep.check("New Project menu found", False)
            raise RuntimeError("New Project menu unavailable")
        driver.click_control(proj)
        time.sleep(1.5)

        dlg = m7b._save_dialog(driver, app, win)
        rep.check("未保存改动时弹出确认提示", dlg is not None,
                  f"dialog={dlg.title if dlg else None}")
        if dlg is None:
            raise RuntimeError("save prompt did not appear")

        crop = driver.capture_screen().crop(dlg.rect)
        crop.save_png(OUT / "save_prompt.png")
        words = recognize_text(crop)
        rep.log(f"[INFO] prompt OCR: {joined_text(words)[:300]}")
        rep.check("提示文案为未保存确认",
                  find_text(words, "unsaved changes") is not None
                  or find_text(words, "would you like to save") is not None)
        clicked = m7b._click_dialog_word(driver, dlg, words, "No")
        rep.check("选择不保存", clicked)
        time.sleep(2.5)

        after = driver.capture(win)
        after.save_png(OUT / "after_new_project.png")
        after_vp = m7b._vp_colored(after)
        rep.check("新建后画布为空", after_vp < EMPTY_BED_MAX,
                  f"viewport={after_vp:.4f}")

        title_after = _title(driver, win)
        default_name = ("untitled" in title_after.lower()
                        or "未命名" in title_after)
        rep.check("标题为默认名", default_name, f"title={title_after!r}")
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
        exit_code = rep.save({"dirty_method": "add cube (platform-equivalent)"})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
