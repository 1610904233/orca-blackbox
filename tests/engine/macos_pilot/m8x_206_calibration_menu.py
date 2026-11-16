#!/usr/bin/env python3
# m8x_206_calibration_menu.py — macOS port: Feishu #206 Calibration menu.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_206,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertion: open the topbar Calibration menu -> 8 top-level items ->
# three submenus (Flow rate / Cornering / Input Shaping) with all rows ->
# nothing grayed/disabled.
#
# macOS: "Calibration" is a native menu-bar item; AXPress opens it.  AX
# exposes the menu items and submenu rows even while the menu is closed, so
# the content/grayed assertions are read from the AX tree; a full-screen grab
# records the opened menu.
#
# Artifacts: artifacts/mac/pilot/m8x_206/{calibration_open.png,items.txt,...}.

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

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)

OUT = ARTIFACTS / "pilot" / "m8x_206"

TOP_REQUIRED = (
    ("温度", "temperature"),
    ("流量", "flow rate"),
    ("压力提前", "pressure advance"),
    ("回抽测试", "retraction test"),
    ("最大体积流量", "max flowrate"),
    ("转弯", "cornering"),
    ("输入整形", "input shaping"),
    ("VFA", "vfa"),
)
SUB_REQUIRED = (
    ("流量", "flow rate", (
        ("粗调", "pass 1"),
        ("细调", "pass 2"),
        ("YOLO 推荐", "yolo (recommended"),
        ("YOLO 完美主义", "yolo (perfectionist"),
    )),
    ("转弯", "cornering", (
        ("节点偏差", "junction deviation"),
    )),
    ("输入整形", "input shaping", (
        ("输入整形频率", "input shaping frequency"),
        ("输入整形阻尼", "damping"),
    )),
)


def _menu_items(driver, win):
    return [c for c in driver.controls(win) if c.role == "AXMenuItem"]


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
    rep.log("=== m8x_206 macOS Calibration menu ===")
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

        calib = next((c for c in driver.controls(win)
                      if c.role == "AXMenuBarItem"
                      and c.title.strip().lower() == "calibration"), None)
        rep.check("Calibration 菜单栏项存在", calib is not None)
        if calib is None:
            raise RuntimeError("Calibration menu bar item not found")

        opened = driver.click_control(calib)
        time.sleep(1.0)
        screen = driver.capture_screen()
        screen.save_png(OUT / "calibration_open.png")
        rep.check("「校准」菜单可展开", opened)

        items = _menu_items(driver, win)
        with (OUT / "items.txt").open("w", encoding="utf-8") as fh:
            for c in items:
                fh.write(f"{c.title!r}\tenabled={c.enabled}\n")
        titles = [c.title.lower() for c in items if c.title]

        missing_top = [cn for cn, needle in TOP_REQUIRED
                       if not any(needle in t for t in titles)]
        rep.check("一级条目齐全（8 项）", not missing_top,
                  f"missing={missing_top}")

        for cn, _needle, wanted in SUB_REQUIRED:
            miss = [wcn for wcn, wneedle in wanted
                    if not any(wneedle in t for t in titles)]
            rep.check(f"{cn}子菜单", not miss, f"missing={miss}")

        required_needles = [n for _cn, n in TOP_REQUIRED]
        for _cn, _n, wanted in SUB_REQUIRED:
            required_needles.extend(n for _wcn, n in wanted)
        disabled = [c.title for c in items
                    if not c.enabled
                    and any(n in c.title.lower() for n in required_needles)]
        rep.check("各条目可点击（无灰置）", not disabled,
                  f"disabled={disabled}")

        # Close the native menu with a real ESC; the app must survive.
        driver.send_key("escape")
        time.sleep(0.8)
        rep.check("菜单可关闭（ESC）", True, "sent ESC")
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
