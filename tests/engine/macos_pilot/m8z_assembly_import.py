#!/usr/bin/env python3
# m8z_assembly_import.py — macOS port: Feishu #20 import a project that already
# contains assembly relations.
# feishu: baseline#20  (macOS port; corresponds to the enabled Windows
#         m8z_assembly_import, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   1) the project loads (plate 1 content is rendered)
#   2) the Objects tab can select a part of plate 1 (the object really exists)
#   3) the Assembly View toolbar slot is clickable and switches the view
#      (viewport changes significantly)
#   4) no error dialog; the app closes normally
#
# macOS mapping:
#   load      -> wait_for_model (viewport chromatic fraction, 5.9% measured)
#   select    -> Objects tab click, then the first child row under
#                "Plate 1 (160X100X80)".  The fixture's plate-1 object is
#                literally named "1", which Vision OCR does not detect as a
#                tree row (too small), so the click point is derived from the
#                OCR'd Plate 1 row: first child at x=25, one 23px row below.
#                The right-hand info panel then shows "Object name: 1" and
#                "Size: 166.998 x 112 x 37.004 mm" — the real selection proof.
#   assembly  -> with the default 1200pt window the Assembly View slot is
#                clipped off the toolbar, so this case pins a 1512pt-wide
#                window through ORCA_BB_WINDOW_FRAME and clicks the slot at
#                window-relative (1470,70).  Success = viewport diff > 0.05
#                plus OCR of Section View / Explosion Ratio / Selection Mode.
#   dialogs   -> no attached AXSheets and no extra on-screen dialog windows.
#
# Artifacts: artifacts/mac/pilot/m8z/{report.log,result.json,*.png}.

from __future__ import annotations

import argparse
import os
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
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)
import mac_3mf  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8z"
DEFAULT_MODEL = HERE / "fixtures" / "assembly_pokemon_box.3mf"

# The Assembly View slot sits at x≈1470 on the Prepare toolbar; the default
# 1200pt frame clips it, so the case requests a 1512pt window explicitly.
WINDOW_FRAME = "180; 40; 1512; 982; 0"
OBJECTS_TAB = (152, 520)        # fallback when OCR misses the tab label
ASSEMBLY_VIEW_XY = (1470, 70)   # calibrated at 1512pt width
COLORED_GATE = 0.03             # measured 0.0586 after load
VIEW_DIFF_GATE = 0.05           # measured 0.348 after switching


def ocr_window(driver, win):
    """OCR the window, returning window-relative word boxes (not global)."""
    return recognize_text(driver.capture_screen().crop(win.rect))


def find_word(words, needle, *, region: Rect | None = None):
    for word in words:
        if needle not in word.text.lower():
            continue
        if region is not None and not _inside(word.rect, region):
            continue
        return word
    return None


def _inside(rect: Rect, region: Rect) -> bool:
    return (region.x <= rect.x <= region.right
            and region.y <= rect.y <= region.bottom)


def tooltip_text(driver, win, x, y) -> str:
    """Hover a toolbar slot and OCR the tooltip that appears below it."""
    driver.move(win.rect.x + x, win.rect.y + y)
    time.sleep(1.2)
    words = recognize_text(
        driver.capture_screen(),
        Rect(win.rect.x + x - 120, win.rect.y + y + 10, 400, 60))
    return " ".join(w.text for w in words).strip()


def select_plate1_object(driver, win, rep) -> tuple[bool, str]:
    """Activate Objects, select the first part row under Plate 1.

    Returns (selected, detail).  The info panel's "Object name:" line is the
    proof; one disclosure-triangle retry covers a collapsed tree.
    """
    info_region = Rect(1030, 700, 482, 253)

    def click_objects_tab():
        words = ocr_window(driver, win)
        tab = find_word(words, "objects", region=Rect(0, 480, 430, 70))
        point = (tab.rect.center[0], tab.rect.center[1]) if tab else OBJECTS_TAB
        rep.log(f"[INFO] Objects tab click at window-rel "
                f"({point[0]:.0f},{point[1]:.0f})")
        driver.click(win.rect.x + point[0], win.rect.y + point[1])
        time.sleep(1.5)
        return ocr_window(driver, win)

    def read_info_panel():
        # OCR the panel region directly: a full-window pass downscales this
        # small line and Vision misreads "Object" as "Obiect" (seen
        # 2026-11-25), which made the selection check a false negative.
        frame = driver.capture_screen().crop(win.rect)
        words = recognize_text(frame, region=info_region)
        name = (find_word(words, "object name", region=info_region)
                or find_word(words, "obiect name", region=info_region))
        return (name, find_word(words, "size:", region=info_region))

    def click_child_row(plate1, tag):
        row_y = plate1.rect.y + 23.0
        rep.log(f"[INFO] {tag}: Plate 1 @ {plate1.rect.to_xywh()} "
                f"-> child row (25,{row_y:.0f})")
        driver.click(win.rect.x + 25.0, win.rect.y + row_y)
        # The info panel for a 45k-triangle part populates asynchronously
        # (measured ~4s on 2026-11-25), so poll instead of a single OCR after
        # a fixed 2s wait; a too-early read was a false negative.
        deadline = time.monotonic() + 12.0
        name = size = None
        attempt = 0
        while time.monotonic() < deadline:
            time.sleep(1.5)
            attempt += 1
            name, size = read_info_panel()
            name_text = name.text if name else None
            size_text = size.text if size else None
            rep.log(f"[INFO] {tag}: info OCR #{attempt} "
                    f"name={name_text!r} size={size_text!r}")
            if name is not None:
                break
        return name, size

    words = click_objects_tab()
    plate1 = find_word(words, "plate 1", region=Rect(0, 520, 430, 160))
    if plate1 is None:
        # The tab click can be swallowed; retry once before giving up.
        words = click_objects_tab()
        plate1 = find_word(words, "plate 1", region=Rect(0, 520, 430, 160))
    if plate1 is None:
        return False, "Plate 1 row not found in Objects tree"

    name, size = click_child_row(plate1, "attempt 1")
    if name is None:
        # The row click can land on the plate header after a re-layout; select
        # the plate once, then click the child row again (same coordinates).
        rep.log("[INFO] no Object name panel; re-select Plate 1 and retry")
        driver.click(win.rect.x + plate1.rect.center[0],
                     win.rect.y + plate1.rect.center[1])
        time.sleep(1.2)
        name, size = click_child_row(plate1, "attempt 2")
    if name is None:
        return False, "Object name panel did not appear after row click"
    detail = name.text
    if size is not None:
        detail += f" | {size.text}"
    return True, f"{detail} (@{name.rect.to_xywh()})"


def dialog_windows(driver, app, win):
    """On-screen top-level windows other than the main one (boot blockers,
    modal alerts).  Tooltips/shadows live on a non-zero window layer."""
    others = []
    for other in driver.windows_for_pid(app.pid):
        if other.id == win.id or not other.on_screen:
            continue
        if other.layer != 0 or other.rect.area < 10000:
            continue
        others.append((other.id, other.title, other.rect.to_xywh()))
    return others


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    # The harness seeds window_mainframe from this variable at launch time.
    os.environ["ORCA_BB_WINDOW_FRAME"] = WINDOW_FRAME

    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)

    rep = Reporter(OUT)
    rep.log("=== m8z macOS assembly import ===")
    rep.log(f"datadir={args.datadir} model={args.model}")
    rep.log(f"window frame override: {WINDOW_FRAME}")

    plates = mac_3mf.read_plates(args.model)
    plate1_names = plates.get("1", [])
    rep.log(f"[INFO] fixture plates: {plates}")

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
                  f"rect={win.rect.to_xywh()} "
                  f"blockers={app.extra.get('blockers')}")
        rep.log(f"[INFO] window rect={win.rect.to_xywh()}")

        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=COLORED_GATE)
        if not ok:
            # One retry: the first capture can land before the plates render.
            ok, frame, frac, _seen = wait_for_model(
                driver, app, win, timeout_s=60.0, threshold=COLORED_GATE)
        frame.save_png(OUT / "loaded.png")
        rep.check("工程载入（装配 3mf 渲染到视口）", ok,
                  f"colored_fraction={frac:.4f} plates={len(plates)}")
        if not ok:
            return rep.save({"stage": "load"})

        # 2) Objects tab -> plate 1 part row -> object info panel.
        selected, detail = select_plate1_object(driver, win, rep)
        driver.capture(win).save_png(OUT / "object_selected.png")
        if selected:
            rep.check("对象标签页选中盘1零件", True, detail)
            name = detail.split("|", 1)[0].split(":", 1)[-1].strip()
            expected = plate1_names[0] if plate1_names else None
            normalized = name.strip("|lI[] ").strip()
            rep.check("选中对象名与夹具一致", normalized == expected,
                      f"ui={normalized!r} fixture={expected!r}")
        else:
            rep.check("对象标签页选中盘1零件", False, detail)

        # 3) Assembly View slot: hover tooltip (evidence) then click.
        tip = tooltip_text(driver, win, *ASSEMBLY_VIEW_XY)
        rep.log(f"[INFO] Assembly slot tooltip={tip!r}")
        before = driver.capture(win)
        driver.click(win.rect.x + ASSEMBLY_VIEW_XY[0],
                     win.rect.y + ASSEMBLY_VIEW_XY[1])
        time.sleep(3.0)
        after = driver.capture(win)
        before.save_png(OUT / "before_assembly.png")
        after.save_png(OUT / "after_assembly.png")
        driver.move(win.rect.x + 700, win.rect.y + 500)  # drop tooltip state
        diff = before.difference(after)
        words = ocr_window(driver, win)
        markers = [w.text for w in words
                   if any(k in w.text.lower() for k in
                          ("section view", "explosion", "selection mode"))]
        rep.log(f"[INFO] viewport diff={diff:.4f} markers={markers[:6]}")
        rep.check("装配视图入口可点击且视图切换", diff > VIEW_DIFF_GATE
                  and ("assembly" in tip.lower() or bool(markers)),
                  f"diff={diff:.4f} tooltip={tip!r} markers={markers[:4]}")

        # 4) No error dialog; normal close.
        time.sleep(0.5)
        sheets = []
        if win.handle is not None:
            err, value = AS.AXUIElementCopyAttributeValue(
                win.handle, "AXSheets", None)
            if err == 0 and value:
                sheets = [str(s) for s in value]
        others = dialog_windows(driver, app, win)
        rep.log(f"[INFO] attached sheets={len(sheets)} other windows={others}")
        rep.check("无错误弹窗", not sheets and not others,
                  f"sheets={len(sheets)} others={others[:2]}")
        alive_before = app.alive()
        closed = close_app(driver, app, win)
        app = None
        rep.check("软件正常关闭", alive_before and closed,
                  f"alive_before_close={alive_before} closed={closed}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        exit_code = rep.save({"fixture": str(args.model)})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
