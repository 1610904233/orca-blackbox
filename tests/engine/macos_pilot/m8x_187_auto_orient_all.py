#!/usr/bin/env python3
# m8x_187_auto_orient_all.py — macOS port: Feishu #187 auto orient (Q / Shift+Q).
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_187,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions: two plates with tilted models -> Shift+Q orients only the
# current plate (1 of 2 items changes) -> Q orients every plate (all items
# face-down, bed contact, size preserved, position kept, plate map unchanged).
#
# macOS mapping: the tilt precondition is written into the saved project's
# build-item transforms (gizmo has no AX fields); Shift+Q / Q are real key
# events after focusing the canvas; the oracle is the 3mf item transforms.
#
# Artifacts: artifacts/mac/pilot/m8x_187/{report.log,result.json,work/*.3mf}.

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

HERE = Path(__file__).resolve().parents[3]
ENGINE = Path(__file__).resolve().parents[1]
PILOTS = Path(__file__).resolve().parent
for path in (str(HERE), str(ENGINE), str(PILOTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import mac_3mf  # noqa: E402
import mac_calib as cal  # noqa: E402
import m8x_186_add_plate as c186  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_187"
DEFAULT_MODEL = HERE / "fixtures" / "Prusa.stl"
DEFAULT_STL = HERE / "fixtures" / "cube20.stl"


def transforms(path: Path) -> dict[str, tuple]:
    geo = mac_3mf.read_project(path)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    return {names.get(oid, oid): t for oid, t in geo.items}


def plate_map(path: Path) -> dict[str, list[str]]:
    return {pid: [n for _i, n in items]
            for pid, items in mac_3mf.read_plates_detailed(path).items()}


def face_down(rot: tuple) -> bool:
    for i in range(3):
        row = rot[i * 3:(i + 1) * 3]
        if abs(row[0]) < 1e-3 and abs(row[1]) < 1e-3 \
                and abs(abs(row[2]) - 1.0) < 1e-3:
            return True
    return False


def row_norms(rot: tuple) -> list[float]:
    return [math.sqrt(sum(rot[i * 3 + j] ** 2 for j in range(3)))
            for i in range(3)]


def tilt_items(src: Path, dst: Path, specs: dict[str, tuple[float, float]]) -> bool:
    """specs: object-name substring -> (angle_deg about X, tz)."""
    geo = mac_3mf.read_project(src)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    targets: dict[str, tuple[str, float, float]] = {}
    for needle, (angle, tz) in specs.items():
        oid = next((i for i, n in names.items() if needle in n.lower()), None)
        if oid is None:
            return False
        targets[oid] = (needle, angle, tz)
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for entry in zin.infolist():
            data = zin.read(entry.filename)
            if entry.filename == "3D/3dmodel.model":
                text = data.decode("utf-8")
                for match in re.finditer(r"<item[^>]*/>", text):
                    tag = match.group(0)
                    oid = re.search(r'objectid="(\d+)"', tag)
                    if oid is None or oid.group(1) not in targets:
                        continue
                    tm = re.search(r'transform="([^"]*)"', tag)
                    if tm is None:
                        continue
                    vals = [float(v) for v in tm.group(1).split()]
                    tx, ty = vals[9], vals[10]
                    _needle, angle, tz = targets[oid.group(1)]
                    c = math.cos(math.radians(angle))
                    s = math.sin(math.radians(angle))
                    new = (f"1 0 0 0 {c:.8f} {-s:.8f} 0 {s:.8f} {c:.8f} "
                           f"{tx} {ty} {tz}")
                    text = text.replace(tag, tag.replace(tm.group(1), new), 1)
                data = text.encode("utf-8")
            zout.writestr(entry, data)
    return True


def sig(t: tuple) -> tuple:
    return tuple(round(v, 3) for v in t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--stl", default=DEFAULT_STL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (work, OUT / "profile_base", OUT / "profile_verify"):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    prusa = work / "prusa.stl"
    shutil.copy2(args.model, prusa)
    cube = work / "cube20.stl"
    shutil.copy2(args.stl, cube)
    base = work / "m8x_187_base.3mf"
    tilted = work / "m8x_187_tilted.3mf"
    p_shift = work / "m8x_187_shiftq.3mf"
    p_all = work / "m8x_187_q.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_187 macOS auto orient Q / Shift+Q ===")

    driver = None
    exit_code = 2
    try:
        driver = get_driver()
        # ---- build the two-plate project -----------------------------
        app = win = None
        try:
            app, win = launch_and_focus(
                driver, OUT / "profile_base", model=prusa,
                timeout_s=args.timeout,
                log_path=OUT / "app_launch_base.log")
            rep.check("s1 启动", True, f"pid={app.pid} title={win.title!r}")
            time.sleep(3.0)
            added = False
            for attempt in range(1, 4):
                driver.click(win.rect.x + c186.ADD_PLATE_XY[0],
                             win.rect.y + c186.ADD_PLATE_XY[1])
                time.sleep(2.0)
                cand = work / f"add{attempt}.3mf"
                if cal.save_project_anywhere(
                        driver, win, cand,
                        search_root=HERE / "artifacts" / "mac") \
                        and len(plate_map(cand)) == 2:
                    added = True
                    break
            rep.check("s1 加盘成功（保存验证）", added)
            rows = [c for c in driver.controls(win, max_depth=12)
                    if c.role == "AXMenuItem"
                    and c.title.strip().lower().startswith("import ")
                    and "3mf" in c.title.lower()]
            driver.click_control(rows[0])
            imported = driver.open_file_dialog(win, cube)
            time.sleep(3.0)
            rep.check("s1 加盘并导入 cube20", imported)
            rep.check("s1 项目保存", cal.save_project_anywhere(
                driver, win, base, search_root=HERE / "artifacts" / "mac")
                and base.exists())
        except Exception as exc:  # noqa: BLE001
            rep.check("s1 unexpected", False, f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
        finally:
            if app is not None:
                rep.check("s1 close", close_app(driver, app, win))

        if not base.exists():
            raise RuntimeError("base project missing")
        rep.check("构造双盘倾斜模型（Prusa + cube，X=45）",
                  tilt_items(base, tilted,
                             {"prusa": (45.0, 20.0),
                              "cube20": (45.0, 20.0)})
                  and tilted.exists())
        t_crafted = transforms(tilted)
        rep.log(f"[INFO] tilted transforms={t_crafted}")
        rep.check("两个 item 均已倾斜",
                  len(t_crafted) == 2
                  and all(abs(t[4] - math.cos(math.radians(45))) < 1e-4
                          for t in t_crafted.values()),
                  f"transforms={t_crafted}")

        # ---- Shift+Q: current plate only ----------------------------
        app = win = None
        try:
            app, win = launch_and_focus(
                driver, OUT / "profile_verify", model=tilted,
                timeout_s=args.timeout,
                log_path=OUT / "app_launch_verify.log")
            rep.check("s2 启动（倾斜项目）", True,
                      f"pid={app.pid} title={win.title!r}")
            time.sleep(3.0)
            # Baseline AFTER load: the app drops the tilted objects onto the
            # bed (tz normalisation), so the crafted file is not the baseline.
            p0 = work / "m8x_187_p0.3mf"
            rep.check("P0 基线保存（加载后）", cal.save_project_anywhere(
                driver, win, p0, search_root=HERE / "artifacts" / "mac")
                and p0.exists())
            t0 = transforms(p0)
            plates0 = plate_map(p0)
            rep.log(f"[INFO] P0 transforms={t0} plates={plates0}")
            driver.click(win.rect.x + 1000, win.rect.y + 320)
            time.sleep(0.5)
            driver.send_key("q", modifiers=("shift",))
            time.sleep(4.0)
            rep.check("Shift+Q 后项目保存", cal.save_project_anywhere(
                driver, win, p_shift,
                search_root=HERE / "artifacts" / "mac") and p_shift.exists())
            t_shift = transforms(p_shift)
            changed = [n for n in t0
                       if n in t_shift and sig(t_shift[n]) != sig(t0[n])]
            unchanged = [n for n in t0
                         if n in t_shift and sig(t_shift[n]) == sig(t0[n])]
            rep.log(f"[INFO] Shift+Q changed={changed} unchanged={unchanged}")
            rep.check("Shift+Q 只动当前盘（恰 1 个 item 变化）",
                      len(changed) == 1 and len(unchanged) == 1,
                      f"changed={changed} unchanged={unchanged}")
            if len(changed) == 1:
                rep.check("当前盘 item 面着地",
                          face_down(t_shift[changed[0]][:9]),
                          f"rot={t_shift[changed[0]][:9]}")

            # ---- Q: all plates (Select All + toolbar Auto orient) ---
            sel = next((c for c in driver.controls(win, max_depth=12)
                        if c.role == "AXMenuItem"
                        and c.title.strip().lower().startswith("select all")),
                       None)
            rep.check("Select All（Q 阶段）", sel is not None)
            if sel is not None:
                driver.click_control(sel)
                time.sleep(1.0)
            driver.move(win.rect.x + 555, win.rect.y + 75)
            time.sleep(1.0)
            driver.click(win.rect.x + 555, win.rect.y + 75)
            time.sleep(5.0)
            rep.check("Q 后项目保存", cal.save_project_anywhere(
                driver, win, p_all,
                search_root=HERE / "artifacts" / "mac") and p_all.exists())
            t_all = transforms(p_all)
            rep.log(f"[INFO] Q transforms={t_all}")
            all_face = all(face_down(t[:9]) for t in t_all.values())
            rep.check("Q 后所有 item 面着地", all_face, f"transforms={t_all}")
            norms_ok = all(abs(n - 1.0) < 1e-3
                           for t in t_all.values() for n in row_norms(t[:9]))
            rep.check("尺寸不变（各旋转行范数 ≈1）", norms_ok,
                      f"norms={ {n: row_norms(t[:9]) for n, t in t_all.items()} }")
            z_ok = all(t_all[n][11] <= t0[n][11] + 0.5 for n in t0 if n in t_all)
            rep.check("底面不高于倾斜前（tz 不增）", z_ok,
                      f"tz={ {n: (t0[n][11], t_all[n][11]) for n in t0 if n in t_all} }")
            rep.check("盘映射不变", plate_map(p_all) == plates0,
                      f"{plates0} -> {plate_map(p_all)}")
            rep.check("app alive (s2)", app.alive())
        except Exception as exc:  # noqa: BLE001
            rep.check("s2 unexpected", False, f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
        finally:
            if app is not None:
                rep.check("s2 close", close_app(driver, app, win))
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        exit_code = rep.save({"covered": ["#187"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
