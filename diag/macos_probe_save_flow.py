#!/usr/bin/env python3
# diag/macos_probe_save_flow.py — validate driver.save_file_dialog end to end.
#
# Flow (mirrors the planned m8x_202 macOS port):
#   1. launch with a model copied into the case workdir (save panel defaults
#      to the model's directory)
#   2. dirty via Add Primitive > Cube (AX context menu, no file dialog)
#   3. File > Save Project as... -> save_file_dialog(workdir/A)
#   4. dirty again -> Save Project as... -> B
#   5. dirty again -> File > Save Project (ordinary, silent) -> B changes
#
# Artifacts: artifacts/mac/probe/save_flow/...

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
for path in (str(HERE), str(HERE / "tests" / "engine"),
             str(HERE / "tests" / "engine" / "macos_pilot")):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import Reporter, close_app, launch_and_focus  # noqa: E402
import m7b_new_project as m7b  # noqa: E402

OUT = HERE / "artifacts" / "mac" / "probe" / "save_flow"
MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest() if path.exists() else ""


def menu_item(driver, win, title):
    return next((c for c in driver.controls(win, max_depth=12)
                 if c.role == "AXMenuItem"
                 and c.title.strip().lower() == title.lower()), None)


def title_of(driver, win) -> str:
    return driver._refresh(win).title


def dirty(driver, app, win, rep, tag):
    """Add a cube, then close any lingering context menu."""
    ok = m7b._add_cube(driver, app, win)
    driver.send_key("escape")
    time.sleep(0.8)
    rep.log(f"[INFO] {tag}: added={ok} title={title_of(driver, win)!r}")


def open_save_as(driver, win, rep, work):
    """Press Save Project as... until the save panel appears (retry once)."""
    for attempt in range(2):
        item = menu_item(driver, win, "Save Project as...")
        if item is None:
            rep.log("[INFO] Save Project as... missing")
            return False
        rep.log(f"[INFO] press Save Project as... ({attempt + 1}) -> "
                f"{driver.click_control(item)}")
        panel = driver.find_file_dialog(
            win.pid, titles=driver._SAVE_PANEL_TITLES,
            exclude_id=win.id, timeout_s=5.0)
        if panel is not None:
            rep.log(f"[INFO] save panel: id={panel.id} title={panel.title!r}")
            return True
        rep.log(f"[INFO] no panel yet; windows="
                f"{[(w.id, w.title, w.layer) for w in driver.windows_for_pid(win.pid) if w.on_screen]}")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    work = OUT / "work"
    work.mkdir(parents=True)
    model = work / "probe_model.3mf"
    shutil.copy2(MODEL, model)
    proj_a = work / "m8x_202_a.3mf"
    proj_b = work / "m8x_202_b.3mf"

    rep = Reporter(OUT)
    rep.log("=== macOS save_file_dialog flow probe ===")

    driver = None
    app = None
    win = None
    code = 2
    try:
        driver = get_driver()
        app, win = launch_and_focus(driver, args.datadir, model=model,
                                    timeout_s=150.0,
                                    log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(3.0)

        dirty(driver, app, win, rep, "dirty 1")
        rep.check("title dirty", title_of(driver, win).startswith("*"),
                  title_of(driver, win))
        rep.check("open Save Project as...", open_save_as(driver, win, rep, work))
        saved_a = driver.save_file_dialog(win, proj_a, default_dir=work)
        rep.check("save A", saved_a, f"md5={md5(proj_a)} title={title_of(driver, win)!r}")
        a_md5 = md5(proj_a)

        dirty(driver, app, win, rep, "dirty 2")
        rep.check("open Save Project as... (B)", open_save_as(driver, win, rep, work))
        saved_b = driver.save_file_dialog(win, proj_b, default_dir=work)
        rep.check("save B", saved_b,
                  f"size={proj_b.stat().st_size if proj_b.exists() else 0} "
                  f"title={title_of(driver, win)!r}")
        rep.check("A unchanged after save-as B", md5(proj_a) == a_md5)
        rep.check("title points at B", "m8x_202_b" in title_of(driver, win).lower(),
                  title_of(driver, win))

        dirty(driver, app, win, rep, "dirty 3")
        b_md5 = md5(proj_b)
        plain = menu_item(driver, win, "Save Project")
        rep.check("Save Project enabled", plain is not None and plain.enabled,
                  f"item={plain is not None} enabled={getattr(plain, 'enabled', None)}")
        if plain is not None:
            driver.click_control(plain)
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and md5(proj_b) == b_md5:
            time.sleep(0.5)
        rep.check("plain save rewrites B", md5(proj_b) != b_md5,
                  f"B {b_md5[:8]} -> {md5(proj_b)[:8]}")
        rep.check("plain save leaves A alone", md5(proj_a) == a_md5)

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
        code = rep.save({})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
