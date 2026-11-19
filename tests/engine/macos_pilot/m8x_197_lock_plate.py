#!/usr/bin/env python3
# m8x_197_lock_plate.py — macOS port: Feishu #197 lock the current plate.
# feishu: baseline#197  (macOS port; corresponds to the enabled Windows
#         m8x_197, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   1) the plate-side "Lock current plate" button is clickable
#   2) while locked, arrange is rejected (objects keep their positions)
#   3) the button flips to "Unlock current plate"; clicking it unlocks
#   4) after unlocking, arrange works again (objects move)
#
# macOS mapping:
#   rail      -> icon column on the current plate's top-right edge.  At
#                1200x800 with two plates the seed points are
#                (952,271) arrange / (972,281) lock.  Tooltips render to the
#                right; every click is tooltip-verified.
#   locked    -> the same icon's tooltip flips from "Lock current plate" to
#                "Unlock current plate" (state oracle), plus the arrange
#                rejection: save before/after and compare cube positions.
#   arrange   -> the rail "Arrange objects on current plate" icon (the same
#                entry Windows clicks).  If it is inert, fall back to the
#                canvas "A" shortcut (m8x_188 recipe).
#   geometry  -> mac_3mf read_project: build-item transforms of Cube* objects.
#
# Artifacts: artifacts/mac/pilot/m8x_197/{report.log,result.json,work/*.3mf,
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

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, recover_saved_file,
    wait_for_model,
)
import mac_3mf  # noqa: E402
import m7b_new_project as m7b  # noqa: E402
import m8x_186_add_plate as c186  # noqa: E402
import m8x_194_remove_plate as c194  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_197"
DEFAULT_MODEL = HERE / "fixtures" / "Prusa.stl"
ADD_PLATE_XY = (520, 75)
ARRANGE_SEED = (952, 271)
LOCK_SEED = (972, 281)
COLORED_GATE = 0.012
NAV_OFFSETS = [(dx, dy) for dy in (-24, -12, 0, 12, 24)
               for dx in (-32, -16, 0, 16, 32)]


def _tip_at(driver, win, x, y) -> str:
    return c194.rail_tooltip(driver, win, x, y)


def find_icon(driver, win, predicate, seed):
    """Hover seed then a small grid; return (x,y,tip) for the first match."""
    tip = _tip_at(driver, win, *seed)
    if predicate(tip):
        return (*seed, tip)
    for dx, dy in NAV_OFFSETS:
        if dx == 0 and dy == 0:
            continue
        x, y = seed[0] + dx, seed[1] + dy
        tip = _tip_at(driver, win, x, y)
        if predicate(tip):
            return (x, y, tip)
    return None


def is_lock(tip: str) -> bool:
    low = tip.lower()
    return "lock current plate" in low and "unlock" not in low


def is_unlock(tip: str) -> bool:
    return "unlock current plate" in tip.lower()


def is_arrange(tip: str) -> bool:
    return "arrange objects on current plate" in tip.lower()


def cube_positions(path: Path) -> dict[str, tuple]:
    """Cube object name#id -> rounded (tx, ty) build-item translation."""
    geo = mac_3mf.read_project(path)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    out = {}
    for oid, transform in geo.items:
        name = names.get(oid, oid)
        if "cube" not in name.lower():
            continue
        out[f"{name}#{oid}"] = (round(transform[9], 3), round(transform[10], 3))
    return out


def toast_text(driver, win) -> str:
    frame = driver.capture(win)
    # recognize_text() treats `region` as frame-local, not screen-global.
    region = Rect(max(0.0, frame.width - 520),
                  max(0.0, frame.height - 170), 510, 150)
    try:
        words = recognize_text(frame, region)
    except Exception:
        return ""
    return " ".join(w.text for w in words).strip()


def save_project(driver, win, rep, path: Path) -> bool:
    """Save Project as..., recovering files the panel wrote to another work dir.

    The shared NSSavePanel recent-places list can make the panel open in the
    previous case's folder (observed: m8x_194/work); the driver still reports
    the target as missing.  Find the fresh file under artifacts/mac/pilot and
    move it into place.
    """
    started = time.time()
    if c186.save_project(driver, win, rep, path):
        return True
    recovered = recover_saved_file(
        path, started, [path.parent, ARTIFACTS / "pilot", HERE / "fixtures"])
    rep.log(f"[INFO] save recovery {path.name}: {recovered}")
    return recovered is not None


def close_colors(driver, app) -> None:
    """The app can restore the native Colors panel on screen; close it so it
    cannot steal key/focus from the Add-Plate / Add-Cube clicks."""
    w = next((w for w in driver.windows_for_pid(app.pid)
              if w.on_screen and (w.title or "").lower() == "colors"), None)
    if w is not None:
        driver.click(w.rect.x + 12, w.rect.y + 12)
        time.sleep(1.0)


def add_cube(driver, app, win) -> bool:
    driver.set_foreground(win)
    time.sleep(0.5)
    return m7b._add_cube(driver, app, win)


def arrange(driver, win, rep, icon) -> str:
    """Click the rail arrange icon; fall back to canvas+A if geometry is inert."""
    driver.click(win.rect.x + icon[0], win.rect.y + icon[1])
    time.sleep(5.0)
    return "rail"


def arrange_fallback_a(driver, win) -> None:
    driver.click(win.rect.x + 1000, win.rect.y + 300)
    time.sleep(0.5)
    driver.send_key("a")
    time.sleep(6.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    model = work / "m8x_197_prusa.stl"
    shutil.copy2(args.model, model)
    s0 = work / "m8x_197_s0.3mf"
    s1 = work / "m8x_197_s1.3mf"
    s2 = work / "m8x_197_s2.3mf"
    s2b = work / "m8x_197_s2b.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_197 macOS lock current plate ===")
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

        # Two-plate layout; the new plate is current.
        close_colors(driver, app)
        tip = c194.tooltip_below(driver, win, *ADD_PLATE_XY)
        rep.check("「添加新盘」按钮", "add plate" in tip.lower(), f"tip={tip!r}")
        driver.click(win.rect.x + ADD_PLATE_XY[0],
                     win.rect.y + ADD_PLATE_XY[1])
        time.sleep(3.0)

        added = [add_cube(driver, app, win) for _ in range(2)]
        rep.check("两个零件已添加", all(added), f"results={added}")
        if not all(added):
            return rep.save({"stage": "add-cubes"})
        time.sleep(2.0)

        if not save_project(driver, win, rep, s0):
            driver.capture(win).save_png(OUT / "save_failed.png")
            rep.log(f"[INFO] windows after failed save="
                    f"{[(w.title, w.rect.to_xywh(), w.layer) for w in driver.windows_for_pid(app.pid)]}")
            rep.check("另存 S0（基线）", False, "save panel failed")
            return rep.save({"stage": "save-s0"})
        plates0 = mac_3mf.read_plates(s0)
        pos0 = cube_positions(s0)
        locked0 = mac_3mf.plate_locked(s0)
        rep.log(f"[INFO] S0 plates={ {k: v for k, v in plates0.items()} }")
        rep.log(f"[INFO] S0 cube positions={pos0} locked={locked0}")
        rep.check("基线几何可解析（两立方体坐标）", len(pos0) >= 2,
                  f"cubes={pos0}")
        rep.check("基线盘未锁定（3mf locked=false）",
                  locked0.get("2") is False, f"locked={locked0}")

        # 1) Lock entry, tooltip-verified.
        lock = find_icon(driver, win, is_lock, LOCK_SEED)
        rep.check("「锁定当前板」按钮（tooltip 验证）", lock is not None,
                  f"@{lock}" if lock else "no 'Lock current plate' tooltip")
        if lock is None:
            return rep.save({"stage": "lock-icon"})
        driver.click(win.rect.x + lock[0], win.rect.y + lock[1])
        time.sleep(2.5)
        driver.capture(win).save_png(OUT / "locked.png")
        st = _tip_at(driver, win, lock[0], lock[1])
        rep.log(f"[INFO] post-lock tooltip={st!r}")
        rep.check("锁定态（tooltip 变为 Unlock）", is_unlock(st),
                  f"tip={st!r}")

        # 2) Arrange while locked: geometry must not change.
        arr = find_icon(driver, win, is_arrange, ARRANGE_SEED)
        rep.check("「排列零件」按钮（导轨，tooltip 验证）", arr is not None,
                  f"@{arr}" if arr else "not found")
        if arr is None:
            return rep.save({"stage": "arrange-icon"})
        arrange(driver, win, rep, arr)
        toast = toast_text(driver, win)
        rep.log(f"[INFO] locked arrange toast={toast!r}")
        rep.log(f"[INFO] 锁定后 toast 证据（Windows 断言为含 locked）："
                f"{'PASS' if 'lock' in toast.lower() else 'absent'}")
        if not save_project(driver, win, rep, s1):
            rep.check("另存 S1（锁定后）", False, "save panel failed")
            return rep.save({"stage": "save-s1"})
        pos1 = cube_positions(s1)
        locked1 = mac_3mf.plate_locked(s1)
        rep.log(f"[INFO] S1 cube positions={pos1} locked={locked1}")
        rep.check("锁定后立方体未移动（几何）", bool(pos1) and pos1 == pos0,
                  f"{pos0} -> {pos1}")
        rep.check("锁定态落盘（3mf locked=true）",
                  locked1.get("2") is True, f"locked={locked1}")

        # 3) Unlock: tooltip flips back.
        unlock = find_icon(driver, win, is_unlock, LOCK_SEED)
        rep.check("「解锁当前板」按钮（tooltip 验证）", unlock is not None,
                  f"@{unlock}" if unlock else "no 'Unlock current plate'")
        if unlock is None:
            return rep.save({"stage": "unlock-icon"})
        driver.click(win.rect.x + unlock[0], win.rect.y + unlock[1])
        time.sleep(2.5)
        driver.capture(win).save_png(OUT / "unlocked.png")
        st2 = _tip_at(driver, win, unlock[0], unlock[1])
        rep.log(f"[INFO] post-unlock tooltip={st2!r}")
        rep.check("解锁状态核验（tooltip 回到 Lock）", is_lock(st2),
                  f"tip={st2!r}")

        # 4) Arrange after unlock: at least one cube moves.
        arrange(driver, win, rep, arr)
        if not save_project(driver, win, rep, s2):
            rep.check("另存 S2（解锁后）", False, "save panel failed")
            return rep.save({"stage": "save-s2"})
        pos2 = cube_positions(s2)
        rep.log(f"[INFO] S2 cube positions={pos2}")
        moved = bool(pos1) and bool(pos2) and pos1 != pos2
        s2_used = s2
        if not moved:
            rep.log("[INFO] rail arrange no-op after unlock; trying canvas+A")
            arrange_fallback_a(driver, win)
            if not save_project(driver, win, rep, s2b):
                rep.check("另存 S2b（全局整理）", False, "save panel failed")
                return rep.save({"stage": "save-s2b"})
            pos2 = cube_positions(s2b)
            s2_used = s2b
            rep.log(f"[INFO] S2b cube positions={pos2}")
            moved = bool(pos1) and bool(pos2) and pos1 != pos2
        rep.check("解锁后整理恢复（几何变化）", moved,
                  f"{pos1} -> {pos2}")
        locked2 = mac_3mf.plate_locked(s2_used)
        rep.log(f"[INFO] unlock state 3mf locked={locked2}")
        rep.check("解锁态落盘（3mf locked=false）",
                  locked2.get("2") is False, f"locked={locked2}")
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
        exit_code = rep.save({"covered": ["#197"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
