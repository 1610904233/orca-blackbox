#!/usr/bin/env python3
# m8x_200_open_project.py — macOS port: Feishu #200 open project.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_200,
#         registered in cases.MACOS_BASELINE)
#
# Windows flow: edit (Move X=40) -> Save As -> New Project (discard) ->
# File > Open Project -> load -> model back, edit restored (X=40.00), title.
#
# macOS mapping:
#   edit           -> Add Primitive > Cube (platform-equivalent scene edit;
#                     no gizmo dependency, same as m8x_199's dirty action)
#   Save As        -> File > "Save Project as..." + driver.save_file_dialog
#   New Project    -> AXMenuItem "New Project" (save prompt -> No)
#   Open Project   -> AXMenuItem "Open Project" + driver.open_file_dialog
#   edit restored  -> the project's 3D/3dmodel.model object count after the
#                     round trip equals the saved project's count (the added
#                     cube survives), plus model arrival and the project title.
#
# Artifacts: artifacts/mac/pilot/m8x_200/{report.log,result.json,work/*.3mf}.

from __future__ import annotations

import argparse
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

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import (  # noqa: E402
    find_text, joined_text, recognize_text,
)
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import m7b_new_project as m7b  # noqa: E402
import m8x_202_save_as as c202  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_200"
DEFAULT_MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"
EMPTY_BED_MAX = 0.015
COLORED_GATE = 0.0025


def object_count(path: Path) -> int:
    """Geometry entries in the 3MF root model.

    The app stores each placed object as a ``<component>`` in
    3D/3dmodel.model (the fixture has 185); Add Cube appends one component.
    Counting ``<object>`` would stay at the plate count and miss the edit.
    """
    with zipfile.ZipFile(path) as z:
        text = z.read("3D/3dmodel.model").decode("utf-8", "replace")
    return len(re.findall(r"<component\s", text))


def menu_item(driver, win, title, *, prefix: bool = False):
    for c in driver.controls(win, max_depth=12):
        if c.role != "AXMenuItem":
            continue
        text = c.title.strip().lower()
        if (text.startswith(title.lower()) if prefix else text == title.lower()):
            return c
    return None


def wait_menu_enabled(driver, win, title, timeout_s: float = 15.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        item = menu_item(driver, win, title, prefix=True)
        if item is not None and item.enabled:
            return item
        time.sleep(0.5)
    return None


def modal_window(driver, app, win):
    """Largest on-screen window that is not the main window (dialog/panel)."""
    candidates = [w for w in driver.windows_for_pid(app.pid)
                  if w.on_screen and w.id != win.id and w.rect.area > 1000]
    return max(candidates, key=lambda w: w.rect.area) if candidates else None


def wait_model(driver, win, timeout_s: float = 120.0):
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
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    model = work / "m8x_200_model.3mf"
    shutil.copy2(args.model, model)
    baseline = work / "m8x_200_base.3mf"
    proj = work / "m8x_200_proj.3mf"
    roundtrip = work / "m8x_200_roundtrip.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_200 macOS open project ===")
    rep.log(f"datadir={args.datadir} model={model}")
    rep.log("[INFO] edit: Add Cube (platform-equivalent to Move X=40)")

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

        # --- 0) baseline project before the edit -----------------------
        rep.check("打开另存为面板（基线）", c202.open_save_as(driver, win, rep))
        saved0 = driver.save_file_dialog(win, baseline, default_dir=work)
        base_count = object_count(baseline) if baseline.exists() else -1
        rep.check("基线项目已保存", saved0 and base_count > 0,
                  f"objects={base_count}")

        # --- 1) edit + Save As ----------------------------------------
        added = m7b._add_cube(driver, app, win)
        driver.send_key("escape")
        time.sleep(0.8)
        title = driver._refresh(win).title
        rep.check("制造改动（Add Cube）", added and title.startswith("*"),
                  f"added={added} title={title!r}")
        rep.check("打开另存为面板", c202.open_save_as(driver, win, rep))
        saved = driver.save_file_dialog(win, proj, default_dir=work)
        rep.check("另存为项目文件", saved and proj.exists(),
                  f"size={proj.stat().st_size if proj.exists() else 0}")
        if not proj.exists():
            raise RuntimeError("project file missing")
        proj_count = object_count(proj)
        rep.check("项目含新增对象（基线 + 1）",
                  base_count > 0 and proj_count == base_count + 1,
                  f"baseline={base_count} saved={proj_count}")

        # --- 2) New Project clears the scene ---------------------------
        item = wait_menu_enabled(driver, win, "New Project")
        rep.check("New Project 菜单可用", item is not None)
        if item is None:
            raise RuntimeError("New Project menu unavailable")
        driver.click_control(item)
        time.sleep(2.0)
        dlg = modal_window(driver, app, win)
        if dlg is not None:
            crop = driver.capture_screen().crop(dlg.rect)
            crop.save_png(OUT / "new_project_dialog.png")
            words = recognize_text(crop)
            rep.log(f"[INFO] dialog {dlg.title!r}: {joined_text(words)[:220]}")
            # Two dialogs are possible: the unsaved-project prompt (No) and
            # the modified-settings transfer prompt (Discard).
            clicked = False
            for label in ("Discard", "No", "Don't Save", "Cancel"):
                if find_text(words, label) is not None:
                    clicked = m7b._click_dialog_word(driver, dlg, words, label)
                    rep.log(f"[INFO] pressed dialog word {label!r}: {clicked}")
                    break
            rep.check("New Project 弹窗已处理", clicked,
                      f"title={dlg.title!r}")
            time.sleep(2.0)
        empty = driver.capture(win)
        empty.save_png(OUT / "after_new.png")
        empty_vp = m7b._vp_colored(empty)
        empty_title = driver._refresh(win).title
        rep.check("新建后画布为空",
                  empty_vp < EMPTY_BED_MAX
                  and ("untitled" in (empty_title or "").lower()
                       or "未命名" in (empty_title or "")),
                  f"viewport={empty_vp:.4f} title={empty_title!r}")

        # --- 3) File > Open Project -----------------------------------
        item = wait_menu_enabled(driver, win, "Open Project")
        rep.check("Open Project 菜单可用", item is not None)
        if item is None:
            raise RuntimeError("Open Project menu unavailable")
        driver.click_control(item)
        opened = driver.open_file_dialog(win, proj)
        rep.check("原生打开面板选择项目", opened)

        # The driver clears the post-open preset blocker; wait for loading to
        # finish (title + menus) before judging arrival.
        menu_ok = wait_menu_enabled(driver, win, "Open Project", timeout_s=40.0)
        title_deadline = time.monotonic() + 30.0
        title = driver._refresh(win).title
        while time.monotonic() < title_deadline:
            title = driver._refresh(win).title
            if "m8x_200_proj" in (title or "").lower():
                break
            time.sleep(0.5)
        rep.check("项目加载完成（菜单恢复）", menu_ok is not None)

        arrived, frame, vp = wait_model(driver, win)
        if frame is not None:
            frame.save_png(OUT / "after_open.png")
        rep.check("项目加载（模型回到盘上）", arrived,
                  f"viewport={vp:.4f} title={title!r}")
        rep.check("标题显示项目文件名",
                  "m8x_200_proj" in (title or "").lower(), f"title={title!r}")
        if not arrived:
            raise RuntimeError("model did not arrive after open")

        # --- 4) edit restored: round-trip geometry count ---------------
        item = wait_menu_enabled(driver, win, "Save Project as")
        rep.check("另存为菜单可用（重开项目后）", item is not None)
        rep.check("再次打开另存为面板", c202.open_save_as(driver, win, rep))
        saved2 = driver.save_file_dialog(win, roundtrip, default_dir=work)
        rt_count = object_count(roundtrip) if roundtrip.exists() else -1
        rep.check("编辑随项目恢复（几何往返一致）",
                  saved2 and rt_count == proj_count,
                  f"saved={proj_count} roundtrip={rt_count}")

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
        exit_code = rep.save({
            "covered": ["#200"],
            "edit_mapping": "Add Cube replaces Move X=40 (no macOS gizmo)",
        })
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
