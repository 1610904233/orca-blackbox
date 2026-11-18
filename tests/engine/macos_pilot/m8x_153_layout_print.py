#!/usr/bin/env python3
# m8x_153_layout_print.py — macOS port: Feishu #153 two-model layout + filament
# info change + slice/export (local segment; device print needs real hardware).
# feishu: baseline#153  (macOS port; corresponds to the enabled Windows
#         m8x_153, registered in cases.MACOS_BASELINE)
#
# Windows assertions (local segment):
#   1) launch with Prusa.stl and import cube20.stl
#   2) the two models overlap (collision warning / intersecting projections)
#   3) Arrange separates them (3mf world-centre distance >= 10mm)
#   4) pre-print filament info change: slot 1 colour is changed
#   5) slice completes and exports a gcode
#   6) the gcode's filament_colour reflects the new slot colour
#
# macOS mapping:
#   imports  -> CLI Prusa + File > Import cube20 (retried; the column-view
#               navigation occasionally misses a folder)
#   overlap  -> imports auto-avoid on this build (Prusa at (100,100), cube at
#               the plate centre).  The Windows case uses Move X=Y=0 for the
#               same purpose; the macOS gizmo is unreliable, so the overlap is
#               crafted into the 3mf instead (m8x_195 precedent): the cube's
#               build-item translation is rewritten to Prusa's (100,100) and
#               the project is reloaded.  That gives a real collision warning
#               and a geometry-verified 0mm centre distance.
#   arrange  -> canvas focus + "A" (m8x_188 recipe); S0/S1 via Save Project as
#   colour   -> the slot-1 chip opens the native "Colors" panel; switch it to
#               RGB Sliders and click Red/Green at the left end and Blue at the
#               right end (real clicks; AXSetValue does not apply).  The hex
#               field gives the exact expected colour (measured #0303FC).
#   slice    -> mac_common.slice_and_export (m8x_158 recipe)
#
# Artifacts: artifacts/mac/pilot/m8x_153/{report.log,result.json,work/*.3mf,
#            *.gcode,*.png}.

from __future__ import annotations

import argparse
import math
import re
import shutil
import sys
import time
import traceback
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]       # repo root
ENGINE = Path(__file__).resolve().parents[1]     # tests/engine
PILOTS = Path(__file__).resolve().parent         # tests/engine/macos_pilot
for path in (str(HERE), str(ENGINE), str(PILOTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, recover_saved_file,
    slice_and_export, wait_for_model,
)
import mac_3mf  # noqa: E402
import m8x_158_layout_multi as c158  # noqa: E402
import m8x_186_add_plate as c186  # noqa: E402
import m8d_purifier_gcode as c8d  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_153"
MODEL1 = HERE / "fixtures" / "Prusa.stl"
MODEL2 = HERE / "fixtures" / "cube20.stl"
CHIP_XY = (25, 415)
MIN_CENTER_MM = 10.0
COLOUR_TOL = 5


def chip_rgb(driver, win) -> tuple:
    frame = driver.capture(win)
    i = (CHIP_XY[1] * frame.width + CHIP_XY[0]) * 4
    return (frame.data[i + 2], frame.data[i + 1], frame.data[i])


def import_with_retry(driver, win, path: Path, rep) -> bool:
    """Import via File > Import; the column-view navigation can miss a folder,
    so retry up to 3 times (closing a stuck panel between attempts)."""
    for attempt in range(1, 4):
        ok = c158.import_model(driver, win, path)
        if ok and c158.info_panel_has(driver, win, path.stem,
                                      timeout_s=20.0):
            rep.log(f"[INFO] import {path.name}: ok on attempt {attempt}")
            return True
        rep.log(f"[INFO] import {path.name}: attempt {attempt} failed "
                f"(panel={ok})")
        try:
            panel = driver.find_file_dialog(
                win.pid, titles=driver._OPEN_PANEL_TITLES,
                exclude_id=win.id, timeout_s=1.0)
            if panel is not None:
                driver.close_window(panel)
        except Exception:
            pass
        time.sleep(1.0)
    return False


def save_project(driver, win, rep, path: Path) -> bool:
    started = time.time()
    if c186.save_project(driver, win, rep, path):
        return True
    recovered = recover_saved_file(path, started, [ARTIFACTS / "pilot"])
    rep.log(f"[INFO] save recovery {path.name}: {recovered}")
    return recovered is not None


def centers(path: Path) -> dict[str, tuple]:
    boxes = mac_3mf.object_world_aabbs(path)
    return {name: ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0)
            for name, (lo, hi) in boxes.items()}


def max_center_dist(points: list[tuple]) -> float:
    best = 0.0
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            best = max(best, math.hypot(points[i][0] - points[j][0],
                                        points[i][1] - points[j][1]))
    return best


def craft_overlap(src: Path, dst: Path, mover: str, target_item: str) -> bool:
    """Rewrite `mover`'s build-item x/y to `target_item`'s translation."""
    geo = mac_3mf.read_project(src)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    items = {names.get(oid, oid): t for oid, t in geo.items}
    mover_t = items.get(mover)
    target_t = items.get(target_item)
    if mover_t is None or target_t is None or len(mover_t) != 12 \
            or len(target_t) != 12:
        return False
    mover_oid = next(oid for oid, t in geo.items
                     if names.get(oid, oid) == mover)
    new_t = list(mover_t)
    new_t[9], new_t[10] = target_t[9], target_t[10]
    new_txt = " ".join(f"{v:.17g}" for v in new_t)
    pattern = re.compile(
        rf'(<item\b[^>]*objectid="{re.escape(mover_oid)}"[^>]*transform=")'
        rf'([^"]*)(")')
    with zipfile.ZipFile(src) as zin:
        entries = [(info, zin.read(info.filename)) for info in zin.infolist()]
    replaced = False
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, data in entries:
            if info.filename == "3D/3dmodel.model":
                text = data.decode("utf-8")
                text, n = pattern.subn(lambda m: m.group(1) + new_txt +
                                       m.group(3), text, count=1)
                replaced = n == 1
                data = text.encode("utf-8")
            zout.writestr(info, data)
    return replaced


def set_slot_colour_rgb(driver, app, win, rep):
    """Chip -> Colors panel -> RGB Sliders -> Red/Green 0, Blue 255."""
    before = chip_rgb(driver, win)
    rep.log(f"[INFO] slot-1 chip before={before}")
    driver.click(win.rect.x + CHIP_XY[0], win.rect.y + CHIP_XY[1])
    time.sleep(2.0)
    panel = None
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        for w in driver.windows_for_pid(app.pid):
            if w.on_screen and "colors" in (w.title or "").lower():
                panel = w
                break
        if panel is not None:
            break
        time.sleep(0.4)
    if panel is None:
        return before, None, None

    def ctrls():
        return driver.controls(panel)

    toolbar = sorted([c for c in ctrls() if c.role == "AXButton"
                      and c.rect is not None
                      and 38 <= c.rect.w <= 52 and 28 <= c.rect.h <= 38
                      and c.rect.y < panel.rect.y + 60],
                     key=lambda c: c.rect.x)
    if len(toolbar) < 2:
        return before, panel, None
    rep.log(f"[INFO] sliders toolbar -> {toolbar[1].rect.to_xywh()}")
    driver.click(*toolbar[1].rect.center)
    time.sleep(1.0)
    popup = next((c for c in ctrls() if c.role == "AXPopUpButton"), None)
    if popup is None:
        return before, panel, None
    if str(popup.value or "").strip() != "RGB Sliders":
        rep.log(f"[INFO] mode={popup.value!r}; switching to RGB Sliders")
        driver.click(*popup.rect.center)
        time.sleep(1.0)
        target = None
        for w in driver.windows_for_pid(app.pid):
            if not w.on_screen or w.id in (panel.id, win.id):
                continue
            try:
                for c in driver.controls(w):
                    if (c.role == "AXMenuItem"
                            and (c.title or "").strip() == "RGB Sliders"
                            and c.rect is not None):
                        target = c
                        break
            except Exception:
                pass
            if target is not None:
                break
        if target is None:
            return before, panel, None
        driver.click(*target.rect.center)
        time.sleep(1.2)
    sliders = [c for c in ctrls() if c.role == "AXSlider"]
    if len(sliders) < 3:
        rep.log(f"[INFO] sliders={[(c.title, c.value) for c in sliders]}")
        return before, panel, None
    points = [(sliders[0].rect.x + 3, sliders[0].rect.center[1]),
              (sliders[1].rect.x + 3, sliders[1].rect.center[1]),
              (sliders[2].rect.right - 3, sliders[2].rect.center[1])]
    rep.log(f"[INFO] RGB click points={points}")
    for x, y in points:
        driver.click(x, y)
        time.sleep(0.6)
    hexf = next((c for c in ctrls() if c.role == "AXTextField"
                 and c.value and re.fullmatch(r"[0-9A-Fa-f]{6}", str(c.value))),
                None)
    expected = f"#{str(hexf.value).upper()}" if hexf is not None else None
    rep.log(f"[INFO] RGB hex field={expected}")
    try:
        driver.close_window(panel)
    except Exception as exc:  # noqa: BLE001
        rep.log(f"[INFO] close Colors panel: {exc}")
    time.sleep(1.0)
    return before, panel, expected


def gcode_slot_colour(path: Path, index: int = 0):
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^; filament_colour = ([^\r\n]+)", text, re.M)
    if not match:
        return None
    values = [v.strip() for v in match.group(1).split(";") if v.strip()]
    return values[index] if index < len(values) else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    model1 = work / "prusa153.stl"
    shutil.copy2(MODEL1, model1)
    model2 = work / "cube153.stl"
    shutil.copy2(MODEL2, model2)
    s0 = work / "m8x_153_s0.3mf"
    overlap = work / "m8x_153_overlap.3mf"
    s1 = work / "m8x_153_s1.3mf"
    gcode = work / "m8x_153.gcode"

    rep = Reporter(OUT)
    rep.log("=== m8x_153 macOS two-model layout + colour + slice ===")
    rep.log(f"datadir={args.datadir} model1={model1} model2={model2}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=model1,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"rect={win.rect.to_xywh()}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.012)
        frame.save_png(OUT / "loaded.png")
        rep.check("启动并载入 Prusa.stl", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        imported = import_with_retry(driver, win, model2, rep)
        rep.check("导入 cube20.stl", imported)
        if not imported:
            return rep.save({"stage": "import"})
        time.sleep(2.0)
        if not save_project(driver, win, rep, s0):
            rep.check("另存 S0（导入后）", False, "save panel failed")
            return rep.save({"stage": "save-s0"})
        c0 = centers(s0)
        rep.log(f"[INFO] S0 centres={c0}")

        # Craft the overlap (imports auto-avoid; Move gizmo is unreliable).
        crafted = craft_overlap(s0, overlap, "cube153.stl", "prusa153.stl")
        rep.check("构造重合工程（cube -> Prusa 位置）", crafted,
                  str(overlap))
        if not crafted:
            return rep.save({"stage": "craft"})
        closed_first = close_app(driver, app, win)
        app = None
        time.sleep(2.0)
        rep.check("关闭首个会话", closed_first, "")

        app, win = launch_and_focus(
            driver, args.datadir, model=overlap,
            timeout_s=args.timeout, log_path=OUT / "app_launch2.log")
        rep.check("重载重合工程", True,
                  f"pid={app.pid} title={win.title!r}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.012)
        frame.save_png(OUT / "overlap_loaded.png")
        rep.check("重合工程载入渲染", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "reload"})
        text = " ".join(w.text for w in c8d.ocr_window(driver, win)).lower()
        rep.log(f"[INFO] collision warning visible={'too close' in text}")
        rep.check("两模型重合（碰撞提示）", "too close" in text,
                  "OCR 'too close to others'")
        c_over = centers(overlap)
        d_over = (max_center_dist(list(c_over.values()))
                  if len(c_over) >= 2 else 99)
        rep.log(f"[INFO] crafted centres={c_over} maxdist={d_over:.2f}mm")
        rep.check("两对象同盘且重合（中心距 <1mm）",
                  len(c_over) == 2 and d_over < 1.0, f"centers={c_over}")

        # Arrange all: canvas focus + A.
        driver.click(win.rect.x + 1000, win.rect.y + 300)
        time.sleep(0.5)
        driver.send_key("a")
        time.sleep(6.0)
        driver.capture(win).save_png(OUT / "after_arrange.png")
        if not save_project(driver, win, rep, s1):
            rep.check("另存 S1（整理后）", False, "save panel failed")
            return rep.save({"stage": "save-s1"})
        c1 = centers(s1)
        d1 = max_center_dist(list(c1.values())) if len(c1) >= 2 else 0.0
        rep.log(f"[INFO] S1 centres={c1} maxdist={d1:.2f}mm")
        rep.check("模型整理（两对象分离，中心距 >=10mm）",
                  len(c1) >= 2 and d1 >= MIN_CENTER_MM,
                  f"center-dist={d1:.2f}mm")

        before_rgb, panel, expected = set_slot_colour_rgb(driver, app, win, rep)
        rep.check("槽 1 换色（RGB Sliders -> 蓝）",
                  panel is not None and expected is not None,
                  f"panel={panel is not None} expected={expected}")
        if panel is None or expected is None:
            return rep.save({"stage": "colour"})
        after_rgb = chip_rgb(driver, win)
        rep.log(f"[INFO] slot-1 chip after={after_rgb}")
        rep.check("侧栏色块变化（换色生效）", after_rgb != before_rgb,
                  f"{before_rgb} -> {after_rgb}")

        if not slice_and_export(driver, win, rep, gcode,
                                [work, OUT, ARTIFACTS / "pilot",
                                 HERE / "fixtures"]):
            rep.check("切片并导出 G-code", False, "slice/export failed")
            return rep.save({"stage": "slice"})
        rep.check("切片并导出 G-code", True,
                  f"size={gcode.stat().st_size}")
        hex_colour = gcode_slot_colour(gcode, 0)
        diff = None
        if hex_colour and expected:
            try:
                diff = max(abs(int(hex_colour[i:i + 2], 16)
                               - int(expected[i:i + 2], 16))
                           for i in (1, 3, 5))
            except ValueError:
                diff = None
        rep.log(f"[INFO] gcode slot1={hex_colour} panel={expected} "
                f"maxchan={diff}")
        rep.check("gcode 反映耗材颜色修改（filament_colour）",
                  diff is not None and diff <= COLOUR_TOL,
                  f"gcode={hex_colour} expected={expected} maxchan={diff}")

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
        exit_code = rep.save({"covered": ["#153"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
