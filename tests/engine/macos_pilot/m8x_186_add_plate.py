#!/usr/bin/env python3
# m8x_186_add_plate.py — macOS port: Feishu #186 add a new plate.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_186,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   click "Add plate" -> the plate list grows by one and the new empty plate is
#   current -> import cube20 into it -> the original plate keeps its objects.
#
# macOS mapping:
#   Add plate -> custom-drawn toolbar icon at (520,75) (hover tooltip
#                "Add plate"); toolbar clicks are occasionally swallowed, so
#                the case saves and re-reads the plate map to verify +1.
#   plate map -> mac_3mf.read_plates(): model_settings.config <plate> blocks
#                (plater_id -> object names), which also proves the new plate
#                is empty and that the old plates are untouched.
#   import    -> File > Import + driver.open_file_dialog.
#
# Artifacts: artifacts/mac/pilot/m8x_186/{report.log,result.json,work/*.3mf}.

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
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import mac_3mf  # noqa: E402
import m7b_new_project as m7b  # noqa: E402
import m8x_202_save_as as c202  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_186"
DEFAULT_MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"
DEFAULT_STL = HERE / "fixtures" / "cube20.stl"
ADD_PLATE_XY = (520, 75)
COLORED_GATE = 0.0025


def tooltip(driver, win, x, y) -> str:
    driver.move(win.rect.x + x, win.rect.y + y)
    time.sleep(1.2)
    words = recognize_text(
        driver.capture_screen(),
        Rect(win.rect.x + x - 120, win.rect.y + y + 10, 400, 60))
    return " ".join(w.text for w in words).strip()


def save_project(driver, win, rep, path: Path) -> bool:
    if not c202.open_save_as(driver, win, rep):
        return False
    return driver.save_file_dialog(win, path, default_dir=path.parent)


def wait_arrival(driver, win, timeout_s: float = 90.0):
    deadline = time.monotonic() + timeout_s
    last = None
    last_vp = 0.0
    while time.monotonic() < deadline:
        last = driver.capture(win)
        last_vp = m7b._vp_colored(last)
        if last_vp >= COLORED_GATE:
            time.sleep(1.5)
            frame2 = driver.capture(win)
            vp2 = m7b._vp_colored(frame2)
            if vp2 >= COLORED_GATE:
                return True, frame2, max(last_vp, vp2)
        time.sleep(1.0)
    return False, last, last_vp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--stl", default=DEFAULT_STL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    model = work / "m8x_186_model.3mf"
    shutil.copy2(args.model, model)
    cube = work / "cube20.stl"
    shutil.copy2(args.stl, cube)
    p0 = work / "m8x_186_p0.3mf"
    p1 = work / "m8x_186_p1.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_186 macOS add plate ===")
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
                  f"blockers={app.extra.get('blockers')}")
        time.sleep(3.0)
        vp0 = m7b._vp_colored(driver.capture(win))
        rep.log(f"[INFO] viewport at boot={vp0:.4f}")

        rep.check("基线项目保存", save_project(driver, win, rep, p0)
                  and p0.exists())
        plates0 = mac_3mf.read_plates(p0)
        base_n = len(plates0)
        rep.log(f"[INFO] baseline plates={base_n} "
                f"{ {k: len(v) for k, v in plates0.items()} }")
        rep.check("基线盘数 >= 2", base_n >= 2, f"plates={base_n}")
        if base_n < 2:
            raise RuntimeError("fixture has too few plates")

        tip = tooltip(driver, win, *ADD_PLATE_XY)
        rep.log(f"[INFO] Add plate tooltip={tip!r}")
        rep.check("「添加新盘」按钮", "add plate" in tip.lower(), f"tip={tip!r}")

        plates1 = None
        added_file = None
        for attempt in range(1, 4):
            driver.click(win.rect.x + ADD_PLATE_XY[0],
                         win.rect.y + ADD_PLATE_XY[1])
            time.sleep(2.0)
            cand = work / f"m8x_186_add{attempt}.3mf"
            if not save_project(driver, win, rep, cand):
                continue
            plates = mac_3mf.read_plates(cand)
            rep.log(f"[INFO] add attempt {attempt}: plates={len(plates)}")
            if len(plates) == base_n + 1:
                plates1, added_file = plates, cand
                break
            if len(plates) > base_n + 1:
                rep.log("[INFO] multiple plates added; aborting retries")
                plates1, added_file = plates, cand
                break
        rep.check("「添加新盘」后盘数 +1",
                  plates1 is not None and len(plates1) == base_n + 1,
                  f"baseline={base_n} now={len(plates1) if plates1 else None}")
        if plates1 is None or len(plates1) != base_n + 1:
            raise RuntimeError("add plate did not produce exactly +1")

        new_pid = str(max(int(pid) for pid in plates1))
        new_objs = plates1.get(new_pid, [])
        rep.check("新盘为空白盘", new_objs == [],
                  f"plate={new_pid} objects={new_objs}")
        keep_ok = all(sorted(plates1.get(pid, [])) == sorted(objs)
                      for pid, objs in plates0.items())
        rep.check("原有盘对象集不变", keep_ok,
                  f"p0={ {k: len(v) for k, v in plates0.items()} } "
                  f"now={ {k: len(v) for k, v in plates1.items()} }")

        rows = [c for c in driver.controls(win, max_depth=12)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("import ")
                and "3mf" in c.title.lower()]
        rep.check("导入入口可用", bool(rows))
        driver.click_control(rows[0])
        imported = driver.open_file_dialog(win, cube)
        rep.check("新盘导入 cube20（流程走通）", imported)
        arrived, frame, vp = wait_arrival(driver, win)
        if frame is not None:
            frame.save_png(OUT / "after_import.png")
        title = driver._refresh(win).title
        rep.check("新盘可添加对象（模型出现）", arrived,
                  f"viewport={vp:.4f} title={title!r}")
        if not arrived:
            raise RuntimeError("import into the new plate failed")

        rep.check("导入后项目保存", save_project(driver, win, rep, p1)
                  and p1.exists())
        plates2 = mac_3mf.read_plates(p1)
        rep.log(f"[INFO] after import plates={ {k: v for k, v in plates2.items()} }")
        on_new = plates2.get(new_pid, [])
        rep.check("cube20 落在新盘",
                  len(on_new) == 1 and "cube20" in on_new[0].lower(),
                  f"plate={new_pid} objects={on_new}")
        keep2 = all(sorted(plates2.get(pid, [])) == sorted(objs)
                    for pid, objs in plates0.items())
        rep.check("原盘对象仍不受影响", keep2,
                  f"now={ {k: len(v) for k, v in plates2.items()} }")
        rep.check("盘数量保持 +1", len(plates2) == base_n + 1,
                  f"plates={len(plates2)}")

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
        exit_code = rep.save({"covered": ["#186"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
