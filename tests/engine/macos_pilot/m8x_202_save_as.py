#!/usr/bin/env python3
# m8x_202_save_as.py — macOS port: Feishu #202 Save Project As.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_202,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions (file MD5 + window title, never UI state guesses):
#   1) Save As A -> A exists
#   2) dirty again -> Save As B -> B exists, A MD5 unchanged
#   3) title shows B (the current project points at the new file)
#   4) dirty again -> File > Save Project -> B changes, A unchanged
#
# macOS mapping:
#   dirty action  -> Add Primitive > Cube (AX context menu; no gizmo, no file
#                    dialog).  Two cubes stand in for "arrange" / "import
#                    prism12": the point is a scene change, not the operation.
#   Save As       -> File > "Save Project as..." opens a native NSSavePanel in
#                    a separate AXDialog window.  The panel starts in the
#                    directory of the model passed on the command line, so a
#                    copy of the fixture lives in this case's work dir and the
#                    .3mf files are written next to it.
#   Save Project  -> enabled once the project is named; writes silently.
#
# Artifacts: artifacts/mac/pilot/m8x_202/{report.log,result.json,work/*.3mf}.

from __future__ import annotations

import argparse
import hashlib
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
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import m7b_new_project as m7b  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_202"
DEFAULT_MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest() if path.exists() else ""


def title_of(driver, win) -> str:
    return driver._refresh(win).title


def menu_item(driver, win, title):
    return next((c for c in driver.controls(win, max_depth=12)
                 if c.role == "AXMenuItem"
                 and c.title.strip().lower() == title.lower()), None)


def dirty(driver, app, win, rep, tag: str) -> bool:
    """Add a cube, then close any lingering context menu."""
    added = m7b._add_cube(driver, app, win)
    driver.send_key("escape")
    time.sleep(0.8)
    title = title_of(driver, win)
    rep.log(f"[INFO] {tag}: added={added} title={title!r}")
    return added and title.startswith("*")


def open_save_as(driver, win, rep, attempts: int = 3) -> bool:
    """Press File > Save Project as... until the native panel appears."""
    for attempt in range(attempts):
        # Cube/context-menu work can leave the app non-key; the menu press then
        # does not raise the native panel (observed in m8x_196/197 reruns).
        try:
            driver.set_foreground(win)
        except Exception:
            pass
        time.sleep(0.4)
        item = menu_item(driver, win, "Save Project as...")
        if item is None:
            rep.log("[INFO] Save Project as... menu item missing")
            return False
        pressed = driver.click_control(item)
        panel = driver.find_file_dialog(
            win.pid, titles=driver._SAVE_PANEL_TITLES,
            exclude_id=win.id, timeout_s=8.0)
        rep.log(f"[INFO] Save Project as... attempt {attempt + 1}: "
                f"pressed={pressed} panel={panel.title if panel else None}")
        if panel is not None:
            return True
        # macOS Save As shortcut fallback (some runs swallow the AXPress).
        driver.send_key("s", modifiers=("cmd", "shift"))
        time.sleep(0.8)
        panel = driver.find_file_dialog(
            win.pid, titles=driver._SAVE_PANEL_TITLES,
            exclude_id=win.id, timeout_s=5.0)
        rep.log(f"[INFO] Save Project as... shortcut: "
                f"panel={panel.title if panel else None}")
        if panel is not None:
            return True
    return False


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
    model = work / "m8x_202_model.3mf"
    shutil.copy2(args.model, model)
    proj_a = work / "m8x_202_a.3mf"
    proj_b = work / "m8x_202_b.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_202 macOS Save Project As ===")
    rep.log(f"datadir={args.datadir} work={work}")

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

        # --- 1) dirty + Save As A --------------------------------------
        rep.check("第一次改动（Add Cube）", dirty(driver, app, win, rep, "改动 1"))
        rep.check("打开另存为面板 A", open_save_as(driver, win, rep))
        saved_a = driver.save_file_dialog(win, proj_a, default_dir=work)
        a_md5 = md5(proj_a)
        rep.check("另存为 A（生成新 3mf）", saved_a and bool(a_md5),
                  f"size={proj_a.stat().st_size if proj_a.exists() else 0} "
                  f"md5={a_md5[:8]}")
        if not a_md5:
            raise RuntimeError("save-as A produced no file")

        # --- 2) dirty + Save As B; A must not change -------------------
        rep.check("第二次改动（Add Cube）", dirty(driver, app, win, rep, "改动 2"))
        rep.check("打开另存为面板 B", open_save_as(driver, win, rep))
        saved_b = driver.save_file_dialog(win, proj_b, default_dir=work)
        rep.check("另存为 B", saved_b and proj_b.exists(),
                  f"size={proj_b.stat().st_size if proj_b.exists() else 0}")
        rep.check("原项目文件 A 未被改动（MD5）", md5(proj_a) == a_md5,
                  f"A md5={md5(proj_a)[:8]}")
        title_b = title_of(driver, win)
        rep.check("当前项目指向 B（标题）",
                  "m8x_202_b" in (title_b or "").lower(), f"title={title_b!r}")
        if not proj_b.exists():
            raise RuntimeError("save-as B produced no file")

        # --- 3) dirty + plain Save Project -> B changes, A stays --------
        rep.check("第三次改动（Add Cube）", dirty(driver, app, win, rep, "改动 3"))
        b_md5 = md5(proj_b)
        item = menu_item(driver, win, "Save Project")
        rep.check("普通保存可用（已命名项目）",
                  item is not None and item.enabled,
                  f"enabled={getattr(item, 'enabled', None)}")
        if item is not None:
            driver.click_control(item)
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and md5(proj_b) == b_md5:
            time.sleep(0.5)
        b_changed = md5(proj_b) != b_md5
        a_changed = md5(proj_a) != a_md5
        rep.check("保存写入新文件 B（B 变、A 不变）",
                  b_changed and not a_changed,
                  f"B_changed={b_changed} A_changed={a_changed}")

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
        exit_code = rep.save({"covered": ["#202"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
