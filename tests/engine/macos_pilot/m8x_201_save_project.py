#!/usr/bin/env python3
# m8x_201_save_project.py — macOS port: Feishu #201 save project.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_201,
#         registered in cases.MACOS_BASELINE)
#
# Windows flow (two app sessions):
#   s1 = edit -> Save As -> edit again -> File > Save Project (silent, file
#        MD5 changes)
#   s2 = fresh app -> open the project -> model back, edit restored
#        (Move Z=45 readback), title shows the project name.
#
# macOS mapping:
#   edit          -> Add Cube (platform-equivalent scene edit; no gizmo)
#   Save As       -> File > "Save Project as..." + driver.save_file_dialog
#   plain save    -> File > "Save Project" (enabled once named); must not open
#                    a save panel and must rewrite the .3mf (MD5 changes)
#   open          -> File > "Open Project..." + driver.open_file_dialog
#   edit restored -> round-trip geometry count (3D/3dmodel.model <component>
#                    entries) equals the saved project's count.
#
# Artifacts: artifacts/mac/pilot/m8x_201/{report.log,result.json,work/*.3mf}.

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
PILOTS = Path(__file__).resolve().parent         # tests/engine/macos_pilot
for path in (str(HERE), str(ENGINE), str(PILOTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import m7b_new_project as m7b  # noqa: E402
import m8x_200_open_project as c200  # noqa: E402
import m8x_202_save_as as c202  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_201"
DEFAULT_MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest() if path.exists() else ""


def save_panel_open(driver, win) -> bool:
    return driver.find_file_dialog(
        win.pid, titles=driver._SAVE_PANEL_TITLES,
        exclude_id=win.id, timeout_s=0.0) is not None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=None, type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    profile_s1 = OUT / "profile_s1"
    profile_s2 = OUT / "profile_s2"
    for path in (work, profile_s1, profile_s2):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    model = work / "m8x_201_model.3mf"
    shutil.copy2(args.model, model)
    proj = work / "m8x_201_proj.3mf"
    roundtrip = work / "m8x_201_roundtrip.3mf"

    rep = Reporter(OUT)
    rep.log("=== m8x_201 macOS save project ===")
    rep.log(f"work={work} model={model}")
    rep.log("[INFO] edit: Add Cube (platform-equivalent to Rotate Z=45)")

    driver = None
    exit_code = 2
    try:
        driver = get_driver()
        # ---------------- session 1: save + plain save ----------------
        app = win = None
        try:
            app, win = launch_and_focus(
                driver, profile_s1, model=model,
                timeout_s=args.timeout, log_path=OUT / "app_launch_s1.log")
            rep.check("s1 启动", True,
                      f"pid={app.pid} title={win.title!r} "
                      f"blockers={app.extra.get('blockers')}")
            arrived, _frame, vp = c200.wait_model(driver, win)
            rep.check("s1 载入模型", arrived, f"viewport={vp:.4f}")

            rep.check("s1 第一次改动（Add Cube）",
                      c202.dirty(driver, app, win, rep, "s1 改动 1"))
            rep.check("s1 打开另存为面板", c202.open_save_as(driver, win, rep))
            saved = driver.save_file_dialog(win, proj, default_dir=work)
            rep.check("s1 项目已命名（另存为）",
                      saved and proj.exists(),
                      f"size={proj.stat().st_size if proj.exists() else 0}")
            if not proj.exists():
                raise RuntimeError("save-as produced no project")

            rep.check("s1 第二次改动（Add Cube）",
                      c202.dirty(driver, app, win, rep, "s1 改动 2"))
            before = md5(proj)
            item = c200.wait_menu_enabled(driver, win, "Save Project")
            rep.check("s1 普通保存可用", item is not None,
                      f"enabled={getattr(item, 'enabled', None)}")
            if item is None:
                raise RuntimeError("Save Project menu unavailable")
            driver.click_control(item)

            dialog_seen = False
            deadline = time.monotonic() + 25.0
            while time.monotonic() < deadline:
                if save_panel_open(driver, win):
                    dialog_seen = True
                    break
                if md5(proj) != before:
                    break
                time.sleep(0.5)
            after = md5(proj)
            rep.check("s1 普通保存无对话框（已命名项目）", not dialog_seen,
                      f"dialog={dialog_seen}")
            rep.check("s1 保存写入文件（MD5 变化）",
                      bool(after) and after != before,
                      f"md5 {before[:8]}->{after[:8]}")
            saved_count = c200.object_count(proj)
            rep.log(f"[INFO] s1 project components={saved_count}")
            rep.check("app alive (s1)", app.alive())
        except Exception as exc:  # noqa: BLE001
            rep.check("s1 unexpected", False, f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
        finally:
            if app is not None:
                rep.check("s1 close", close_app(driver, app, win))

        # ---------------- session 2: reopen the project ----------------
        app = win = None
        try:
            app, win = launch_and_focus(
                driver, profile_s2, model=None,
                timeout_s=args.timeout, log_path=OUT / "app_launch_s2.log")
            rep.check("s2 启动", True, f"pid={app.pid} title={win.title!r}")
            item = c200.wait_menu_enabled(driver, win, "Open Project")
            rep.check("s2 Open Project 菜单可用", item is not None)
            if item is None:
                raise RuntimeError("Open Project menu unavailable")
            driver.click_control(item)
            opened = driver.open_file_dialog(win, proj)
            rep.check("s2 打开项目", opened)

            menu_ok = c200.wait_menu_enabled(
                driver, win, "Open Project", timeout_s=40.0)
            title_deadline = time.monotonic() + 30.0
            title = driver._refresh(win).title
            while time.monotonic() < title_deadline:
                title = driver._refresh(win).title
                if "m8x_201_proj" in (title or "").lower():
                    break
                time.sleep(0.5)
            rep.check("s2 项目加载完成（菜单恢复）", menu_ok is not None)
            arrived, _frame, vp = c200.wait_model(driver, win)
            rep.check("s2 模型回到盘上", arrived, f"viewport={vp:.4f}")
            rep.check("s2 标题显示项目文件名",
                      "m8x_201_proj" in (title or "").lower(),
                      f"title={title!r}")
            if not arrived:
                raise RuntimeError("model did not arrive after open")

            rep.check("s2 打开另存为面板", c202.open_save_as(driver, win, rep))
            saved2 = driver.save_file_dialog(win, roundtrip, default_dir=work)
            rt_count = (c200.object_count(roundtrip)
                        if roundtrip.exists() else -1)
            rep.check("s2 编辑随项目恢复（几何往返一致）",
                      saved2 and rt_count == saved_count,
                      f"saved={saved_count} roundtrip={rt_count}")
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
        exit_code = rep.save({
            "covered": ["#201"],
            "edit_mapping": "Add Cube replaces Rotate Z=45 (no macOS gizmo)",
        })
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
