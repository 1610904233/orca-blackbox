#!/usr/bin/env python3
# m3a_empty_slice.py — macOS pilot: an empty plate must reject Slice.
# feishu: none  (macOS pilot probe, not registered in cases.py)
#
# macOS equivalent of the Windows m3a negative assertion: click "Slice plate"
# on an empty scene and prove no slice result appears.  The deterministic
# signal is File > "Export G-code..." staying disabled; we also record frame
# stats and any modal window that appears.
#
# Artifacts: artifacts/mac/pilot/m3a/{before,after}.png + report/result.

from __future__ import annotations

import argparse
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
    ARTIFACTS, Reporter, close_app, dismiss_dialogs, launch_and_focus,
)

OUT = ARTIFACTS / "pilot" / "m3a"


def _export_item(driver, win):
    return driver.find_control(win, role="AXMenuItem",
                               title="Export G-code", timeout_s=3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--wait", default=10.0, type=float,
                    help="seconds to watch after clicking Slice")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m3a macOS empty-slice pilot ===")
    rep.log(f"datadir={args.datadir}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, timeout_s=args.timeout,
            log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")

        before = driver.capture(win)
        before.save_png(OUT / "before.png")
        b_stats = before.stats()
        rep.check("empty scene", b_stats["colored_fraction"] < 0.03,
                  f"colored={b_stats['colored_fraction']:.4f} "
                  f"mean_luma={b_stats['mean_luma']:.2f}")

        export = _export_item(driver, win)
        rep.check("Export G-code item found", export is not None,
                  f"enabled={export.enabled if export else None}")
        rep.check("Export disabled before Slice",
                  export is not None and not export.enabled,
                  f"enabled={export.enabled if export else None}")

        sx = win.rect.w / 1200.0
        sy = win.rect.h / 800.0
        rep.log(f"[INFO] click Slice plate at "
                f"({win.rect.x + 1000 * sx:.0f},{win.rect.y + 45 * sy:.0f})")
        driver.click(win.rect.x + 1000 * sx, win.rect.y + 45 * sy)

        seen: set = set()
        stayed_disabled = True
        enabled_seen = False
        deadline = time.monotonic() + args.wait
        while time.monotonic() < deadline:
            seen = dismiss_dialogs(driver, app, win, seen)
            cur = _export_item(driver, win)
            if cur is None:
                stayed_disabled = False
                break
            if cur.enabled:
                enabled_seen = True
                stayed_disabled = False
                break
            time.sleep(1.0)

        rep.check("Slice rejected (Export stays disabled)", stayed_disabled,
                  f"enabled_seen={enabled_seen}")
        after = driver.capture(win)
        after.save_png(OUT / "after.png")
        a_stats = after.stats()
        diff = before.difference(after)
        rep.log(f"[INFO] after: colored={a_stats['colored_fraction']:.4f} "
                f"mean_luma={a_stats['mean_luma']:.2f} frame_diff={diff:.4f}")

        extra = [w for w in driver.windows_for_pid(app.pid)
                 if w.id != win.id and w.on_screen and w.rect.area > 1000]
        rep.log(f"[INFO] extra on-screen windows: "
                f"{[(w.id, w.title, w.rect.to_xywh()) for w in extra]}")
        rep.check("no toolpath rendered",
                  a_stats["colored_fraction"] < 0.03,
                  f"colored={a_stats['colored_fraction']:.4f}")
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
