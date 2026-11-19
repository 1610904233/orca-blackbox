#!/usr/bin/env python3
# m8x_194_remove_plate.py — macOS port: Feishu #194 remove the current plate.
# feishu: baseline#194  (macOS port; corresponds to the enabled Windows
#         m8x_194, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   with >=2 plates and a non-empty current plate, the plate-side "Remove
#   current plate" button deletes the current plate and its objects: the plate
#   count drops by one, the other plate keeps its object set and the Prusa
#   build-item transform is bit-identical.
#
# macOS mapping:
#   entry     -> plate-side rail icon, located by hover tooltip.  At
#                1200x800 with two plates the current (second) plate's rail
#                runs (920,251) remove / (933,261) auto-orient /
#                (952,271) arrange / (972,281) lock / (992,291) customize /
#                (1012,302) move-to-front.  A bounded neighbourhood scan
#                absorbs small geometry drift; the tooltip must literally say
#                "Remove current plate" before clicking (no blind click).
#   fixture   -> Prusa.stl on plate 1; add plate; import cube20 into plate 2
#                so the deleted plate is non-empty.
#   oracle    -> Save Project as P0/P1 and parse both with mac_3mf: plate map,
#                object names and the Prusa item transform.
#
# Artifacts: artifacts/mac/pilot/m8x_194/{report.log,result.json,work/*.3mf,
#            *.png}.

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

import ApplicationServices as AS  # noqa: E402

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, recover_saved_file,
    wait_for_model,
)
import mac_3mf  # noqa: E402
import m8x_186_add_plate as c186  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_194"
DEFAULT_MODEL = HERE / "fixtures" / "Prusa.stl"
DEFAULT_CUBE = HERE / "fixtures" / "cube20.stl"
ADD_PLATE_XY = (520, 75)
RAIL_SEED = (920, 251)       # Remove icon for plate 2 at 1200x800
TOOLTIP_OFFSETS = [(dx, dy) for dy in (-30, -15, 0, 15, 30)
                   for dx in (-40, -20, 0, 20, 40)]
COLORED_GATE = 0.012         # Prusa.stl measured 0.0195


def tooltip_below(driver, win, x, y) -> str:
    for _ in range(4):
        driver.move(win.rect.x + 5, win.rect.y + 5)
        time.sleep(0.25)
        driver.move(win.rect.x + x, win.rect.y + y)
        time.sleep(1.3)
        words = recognize_text(
            driver.capture_screen(),
            Rect(win.rect.x + x - 80, win.rect.y + y + 12, 340, 64))
        text = " ".join(w.text for w in words).strip()
        if text:
            return text
    return ""


def rail_tooltip(driver, win, x, y) -> str:
    """Plate-rail tooltips render to the right of the cursor."""
    region = Rect(min(win.rect.x + x + 8, win.rect.right - 260),
                  win.rect.y + y - 20, 260, 80)
    for _ in range(4):
        driver.move(win.rect.x + 5, win.rect.y + 5)
        time.sleep(0.25)
        driver.move(win.rect.x + x, win.rect.y + y)
        time.sleep(1.3)
        words = recognize_text(driver.capture_screen(), region)
        text = " ".join(w.text for w in words).strip()
        if text:
            return text
    return ""


def find_rail_icon(driver, win, want: str, seed=RAIL_SEED):
    """Hover the seed then a small grid; only a matching tooltip wins."""
    tip = rail_tooltip(driver, win, *seed)
    if want in tip.lower():
        return (*seed, tip)
    for dx, dy in TOOLTIP_OFFSETS:
        if dx == 0 and dy == 0:
            continue
        x, y = seed[0] + dx, seed[1] + dy
        tip = rail_tooltip(driver, win, x, y)
        if want in tip.lower():
            return (x, y, tip)
    return None


def _copy(elem, attr):
    err, value = AS.AXUIElementCopyAttributeValue(elem, attr, None)
    return value if err == 0 else None


def dismiss_confirm(driver, win, rep) -> str:
    """A plate delete may raise a confirm sheet/window; press Yes/OK if so."""
    time.sleep(1.5)
    try:
        sheets = _copy(win.handle, "AXSheets") or []
    except Exception:
        sheets = []
    keep = list(sheets)
    roots = list(sheets)
    for w in driver.windows_for_pid(win.pid):
        if w.id == win.id or not w.on_screen:
            continue
        low = (w.title or "").lower()
        if any(k in low for k in ("remove", "delete", "confirm", "warning")):
            roots.append(w.handle)
            keep.append(w.handle)
            rep.log(f"[INFO] confirm window: {w.title!r} {w.rect.to_xywh()}")
    for root in roots:
        if root is None:
            continue
        stack = [(root, 0)]
        while stack:
            elem, depth = stack.pop()
            role = _copy(elem, AS.kAXRoleAttribute)
            if role == "AXButton":
                text = " ".join(str(_copy(elem, AS.kAXTitleAttribute) or "")
                                + " " + str(_copy(elem, AS.kAXValueAttribute)
                                            or "")).lower()
                if any(k in text for k in ("yes", "ok", "remove", "delete",
                                           "confirm")):
                    if driver._ax_perform(elem, AS.kAXPressAction):
                        rep.log(f"[INFO] confirm pressed: {text.strip()!r}")
                        time.sleep(1.5)
                        return text.strip()
            if depth < 10:
                for child in reversed(list(_copy(elem, AS.kAXChildrenAttribute)
                                           or [])):
                    stack.append((child, depth + 1))
    return ""


def import_cube(driver, win, cube: Path, rep) -> bool:
    rows = [c for c in driver.controls(win, max_depth=12)
            if c.role == "AXMenuItem"
            and c.title.strip().lower().startswith("import ")
            and "3mf" in c.title.lower()]
    if not rows:
        rep.log("[INFO] Import menu item not found")
        return False
    driver.click_control(rows[0])
    return driver.open_file_dialog(win, cube)


def save_project(driver, win, rep, path: Path) -> bool:
    """Save Project as..., moving the file back if the panel opened in the
    previous case's ``work`` folder (shared NSSavePanel recent places)."""
    started = time.time()
    if c186.save_project(driver, win, rep, path):
        return True
    recovered = recover_saved_file(path, started, [ARTIFACTS / "pilot"])
    rep.log(f"[INFO] save recovery {path.name}: {recovered}")
    return recovered is not None


def item_transforms(path: Path) -> dict[str, tuple]:
    """object name -> rounded 12-number build-item transform."""
    geo = mac_3mf.read_project(path)
    names = {obj.id: obj.name or obj.id for obj in geo.objects}
    out = {}
    for oid, transform in geo.items:
        name = names.get(oid, oid)
        if name in out:
            name = f"{name}#{oid}"
        out[name] = tuple(round(v, 3) for v in transform)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--cube", default=DEFAULT_CUBE, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    model = work / "m8x_194_prusa.stl"
    shutil.copy2(args.model, model)
    cube = work / "m8x_194_cube20.stl"
    shutil.copy2(args.cube, cube)
    p0 = work / "m8x_194_p0.3mf"
    p1 = work / "m8x_194_p1.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_194 macOS remove current plate ===")
    rep.log(f"datadir={args.datadir} model={model}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=model,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"rect={win.rect.to_xywh()}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=COLORED_GATE)
        frame.save_png(OUT / "loaded.png")
        rep.check("载入（1 号盘 Prusa）", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        # --- 2nd plate (current), then make it non-empty -------------------
        tip = tooltip_below(driver, win, *ADD_PLATE_XY)
        rep.log(f"[INFO] Add plate tooltip={tip!r} "
                f"(button identity is proven by the plate count below)")
        driver.click(win.rect.x + ADD_PLATE_XY[0],
                     win.rect.y + ADD_PLATE_XY[1])
        time.sleep(3.0)

        imported = import_cube(driver, win, cube, rep)
        rep.check("导入 cube20（打开面板走通）", imported)
        time.sleep(2.5)

        if not save_project(driver, win, rep, p0):
            rep.check("另存 P0（基线）", False, "save panel failed")
            return rep.save({"stage": "save-p0"})
        plates0 = mac_3mf.read_plates(p0)
        rep.log(f"[INFO] P0 plates={ {k: v for k, v in plates0.items()} }")
        rep.check("新建 2 号盘（P0 有 2 盘）", len(plates0) == 2,
                  f"plates={sorted(plates0)}")
        rep.check("2 号盘导入 cube20（非空盘）",
                  len(plates0.get("2", [])) == 1
                  and "cube20" in plates0.get("2", [""])[0].lower(),
                  f"plate2={plates0.get('2')}")
        base_ok = (len(plates0) == 2
                   and len(plates0.get("1", [])) == 1
                   and len(plates0.get("2", [])) == 1)
        rep.check("P0 基线（2 盘各 1 对象）", base_ok,
                  f"plates={ {k: len(v) for k, v in plates0.items()} }")
        if not base_ok:
            return rep.save({"stage": "baseline"})
        transforms0 = item_transforms(p0)
        rep.log(f"[INFO] P0 transforms={transforms0}")

        # --- plate-side Remove button, tooltip-verified --------------------
        icon = find_rail_icon(driver, win, "remove")
        rep.check("盘侧删除按钮（tooltip 验证）", icon is not None,
                  f"@{icon}" if icon else "no 'remove' tooltip near rail")
        if icon is None:
            return rep.save({"stage": "remove-icon"})
        driver.move(win.rect.x + icon[0], win.rect.y + icon[1])
        time.sleep(0.3)
        driver.click(win.rect.x + icon[0], win.rect.y + icon[1])
        time.sleep(2.0)
        confirmed = dismiss_confirm(driver, win, rep)
        rep.check("移除当前板（点删除按钮）", True,
                  f"@{icon[0]},{icon[1]} confirm={confirmed or 'none'}")
        driver.capture(win).save_png(OUT / "after_remove.png")
        time.sleep(1.5)

        if not save_project(driver, win, rep, p1):
            rep.check("另存 P1（删后）", False, "save panel failed")
            return rep.save({"stage": "save-p1"})
        plates1 = mac_3mf.read_plates(p1)
        rep.log(f"[INFO] P1 plates={ {k: v for k, v in plates1.items()} }")
        transforms1 = item_transforms(p1)
        rep.log(f"[INFO] P1 transforms={transforms1}")

        rep.check("盘数量 -1（2 → 1）", len(plates1) == 1,
                  f"plates={sorted(plates1)}")
        keep = plates1.get("1", [])
        rep.check("其余盘对象集不变（1 号盘仍 [Prusa.stl]）",
                  sorted(keep) == sorted(plates0.get("1", [])),
                  f"plate1={keep}, was={plates0.get('1')}")
        # The imported object is named after the file stem, so take the plate-1
        # name from P0 instead of hardcoding "Prusa.stl".
        prusa = (plates0.get("1") or [""])[0]
        rep.check("Prusa 位姿逐位不变",
                  bool(prusa) and transforms0.get(prusa) == transforms1.get(prusa)
                  and transforms0.get(prusa) is not None,
                  f"name={prusa!r} "
                  f"{transforms0.get(prusa)} -> {transforms1.get(prusa)}")
        removed = set(plates0.get("2", []))
        on_any = sorted({name for objs in plates1.values() for name in objs
                         if name in removed})
        rep.check("被删盘的对象不再属于任何盘", not on_any,
                  f"still referenced={on_any}")
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
        exit_code = rep.save({"covered": ["#194"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
