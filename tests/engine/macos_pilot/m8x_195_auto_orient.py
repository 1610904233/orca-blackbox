#!/usr/bin/env python3
# m8x_195_auto_orient.py — macOS port: Feishu #195 auto orient.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_195,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions: a tilted cube on plate 2 (plate 1 = Prusa spectator) ->
# Auto orient -> the cube is face-down, touches the bed, keeps its size and
# x/y position, and plate 1 is untouched.
#
# macOS mapping:
#   tilt precondition -> the gizmo panel has no AX fields, so the cube's
#                        build-item transform is rewritten to a 45 deg X
#                        rotation in the saved project (crafted fixture).
#   entry             -> toolbar Auto orient at (555,75) ("Auto orient
#                        all/selected objects [Q]"); the plate-rail icon has
#                        no clickable AX node on this build.
#   oracle            -> 3mf item transforms / plate map.
#
# Artifacts: artifacts/mac/pilot/m8x_195/{report.log,result.json,work/*.3mf}.

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

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import mac_3mf  # noqa: E402
import mac_calib as cal  # noqa: E402
import m8x_186_add_plate as c186  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_195"
DEFAULT_MODEL = HERE / "fixtures" / "Prusa.stl"
DEFAULT_STL = HERE / "fixtures" / "cube20.stl"
ORIENT_XY = (555, 75)


def find_toolbar_slot(driver, win, needle, x0=460, x1=621, y=75):
    """Scan the toolbar tooltips for a slot (layout moves with the project)."""
    for x in range(x0, x1, 10):
        driver.move(win.rect.x + x, win.rect.y + y)
        time.sleep(1.0)
        words = recognize_text(
            driver.capture_screen(),
            Rect(win.rect.x + x - 120, win.rect.y + y + 10, 420, 80))
        text = " ".join(w.text for w in words).strip()
        if needle in text.lower():
            return (x, y), text
    return None, ""


def transforms(path: Path) -> dict[str, tuple]:
    geo = mac_3mf.read_project(path)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    return {names.get(oid, oid): t for oid, t in geo.items}


def plate_map(path: Path) -> dict[str, list[str]]:
    return {pid: [n for _i, n in items]
            for pid, items in mac_3mf.read_plates_detailed(path).items()}


def tilt_project(src: Path, dst: Path, name_contains: str,
                 angle_deg: float = 45.0) -> bool:
    """Rewrite the cube's build-item transform to a rotation about X."""
    geo = mac_3mf.read_project(src)
    names = {o.id: (o.name or o.id) for o in geo.objects}
    oid = next((i for i, n in names.items()
                if name_contains in n.lower()), None)
    if oid is None:
        return False
    c = math.cos(math.radians(angle_deg))
    s = math.sin(math.radians(angle_deg))
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for entry in zin.infolist():
            data = zin.read(entry.filename)
            if entry.filename == "3D/3dmodel.model":
                text = data.decode("utf-8")
                for match in re.finditer(r"<item[^>]*/>", text):
                    tag = match.group(0)
                    if f'objectid="{oid}"' not in tag:
                        continue
                    tm = re.search(r'transform="([^"]*)"', tag)
                    if tm is None:
                        continue
                    vals = [float(v) for v in tm.group(1).split()]
                    tx, ty = vals[9], vals[10]
                    new = (f"1 0 0 0 {c:.8f} {-s:.8f} 0 {s:.8f} {c:.8f} "
                           f"{tx} {ty} 20")
                    text = text.replace(tag, tag.replace(tm.group(1), new), 1)
                    break
                data = text.encode("utf-8")
            zout.writestr(entry, data)
    return True


def face_down(rot: tuple) -> bool:
    """Some rotation row is (0,0,+/-1) (a face parallel to the bed)."""
    for i in range(3):
        row = rot[i * 3:(i + 1) * 3]
        if abs(row[0]) < 1e-3 and abs(row[1]) < 1e-3 \
                and abs(abs(row[2]) - 1.0) < 1e-3:
            return True
    return False


def row_norms(rot: tuple) -> list[float]:
    return [math.sqrt(sum(rot[i * 3 + j] ** 2 for j in range(3)))
            for i in range(3)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=None, type=Path)
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
    base = work / "m8x_195_base.3mf"
    tilted = work / "m8x_195_tilted.3mf"
    after = work / "m8x_195_after.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_195 macOS auto orient ===")
    rep.log("[INFO] tilt precondition: 45deg X via 3mf build-item rewrite")

    driver = None
    exit_code = 2
    try:
        driver = get_driver()
        # ---- session 1: two plates, Prusa + cube ---------------------
        app = win = None
        try:
            app, win = launch_and_focus(
                driver, OUT / "profile_base", model=prusa,
                timeout_s=args.timeout,
                log_path=OUT / "app_launch_base.log")
            rep.check("s1 启动", True, f"pid={app.pid} title={win.title!r}")
            time.sleep(3.0)
            added = False
            add_slot, add_tip = find_toolbar_slot(driver, win, "add plate")
            rep.log(f"[INFO] Add plate slot={add_slot} tip={add_tip!r}")
            if add_slot is None:
                add_slot = c186.ADD_PLATE_XY
            for attempt in range(1, 4):
                driver.click(win.rect.x + add_slot[0],
                             win.rect.y + add_slot[1])
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
        plates0 = plate_map(base)
        t0 = transforms(base)
        rep.log(f"[INFO] base plates={plates0} transforms={t0}")
        rep.check("s1 基线（2 盘，cube 在 2 号盘）",
                  len(plates0) == 2
                  and any("cube20" in n.lower()
                          for objs in plates0.values() for n in objs),
                  f"plates={plates0}")

        rep.check("构造倾斜模型（45° X）",
                  tilt_project(base, tilted, "cube20", 45.0)
                  and tilted.exists())
        rep.check("倾斜后 cube 绕 X 旋转 45°",
                  abs(transforms(tilted).get("cube20.stl", (0,) * 12)[4]
                      - math.cos(math.radians(45))) < 1e-4,
                  f"t={transforms(tilted).get('cube20.stl')}")

        # ---- session 2: auto orient ---------------------------------
        app = win = None
        try:
            app, win = launch_and_focus(
                driver, OUT / "profile_verify", model=tilted,
                timeout_s=args.timeout,
                log_path=OUT / "app_launch_verify.log")
            rep.check("s2 启动（倾斜项目）", True,
                      f"pid={app.pid} title={win.title!r}")
            time.sleep(3.0)
            plates1 = plate_map(tilted)
            rep.check("s2 盘映射（2 盘）", len(plates1) == 2,
                      f"plates={plates1}")

            sel = next((c for c in driver.controls(win, max_depth=12)
                        if c.role == "AXMenuItem"
                        and c.title.strip().lower().startswith("select all")),
                       None)
            rep.check("Select All 可用", sel is not None)
            if sel is not None:
                driver.click_control(sel)
                time.sleep(1.0)
            orient_slot, tip = find_toolbar_slot(
                driver, win, "orient", x0=500, x1=621)
            rep.log(f"[INFO] orient slot={orient_slot} tip={tip!r}")
            if orient_slot is None:
                orient_slot = ORIENT_XY
            driver.click(win.rect.x + orient_slot[0],
                         win.rect.y + orient_slot[1])
            time.sleep(4.0)
            rep.check("s2 项目保存", cal.save_project_anywhere(
                driver, win, after, search_root=HERE / "artifacts" / "mac")
                and after.exists())
            rep.check("app alive (s2)", app.alive())
        except Exception as exc:  # noqa: BLE001
            rep.check("s2 unexpected", False, f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
        finally:
            if app is not None:
                rep.check("s2 close", close_app(driver, app, win))

        if not after.exists():
            raise RuntimeError("after project missing")
        t1 = transforms(after)
        plates2 = plate_map(after)
        rep.log(f"[INFO] after plates={plates2} transforms={t1}")
        cube_t = t1.get("cube20.stl", ())
        rep.check("cube 面着地（旋转行 ≈ (0,0,±1)）",
                  len(cube_t) == 12 and face_down(cube_t[:9]),
                  f"rot={cube_t[:9]}")
        rep.check("底面贴合（tz ≈ 10）",
                  len(cube_t) == 12 and abs(cube_t[11] - 10.0) < 0.5,
                  f"tz={cube_t[11] if len(cube_t) == 12 else None}")
        rep.check("尺寸不变（旋转行范数 ≈1）",
                  len(cube_t) == 12
                  and all(abs(n - 1.0) < 1e-3 for n in row_norms(cube_t[:9])),
                  f"norms={row_norms(cube_t[:9]) if len(cube_t) == 12 else None}")
        rep.check("原地旋转（|Δtx|,|Δty| ≤0.5）",
                  len(cube_t) == 12
                  and abs(cube_t[9] - t0["cube20.stl"][9]) <= 0.5
                  and abs(cube_t[10] - t0["cube20.stl"][10]) <= 0.5,
                  f"{t0['cube20.stl'][9:11]} -> {cube_t[9:11]}")
        rep.check("1 号盘 Prusa 逐位不变（3 位小数）",
                  tuple(round(v, 3) for v in t1["prusa.stl"])
                  == tuple(round(v, 3) for v in t0["prusa.stl"]),
                  f"{t0['prusa.stl']} -> {t1['prusa.stl']}")
        rep.check("盘映射不变", plates2 == plates1,
                  f"{plates1} -> {plates2}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        exit_code = rep.save({"covered": ["#195"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
