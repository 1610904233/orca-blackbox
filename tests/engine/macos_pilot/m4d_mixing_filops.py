#!/usr/bin/env python3
# m4d_mixing_filops.py — macOS port: Feishu #88/#159 physical-filament
# operations against mixing state.
# feishu: baseline#88 baseline#159  (macOS port; corresponds to the enabled
#         Windows m4d_mixing_filops, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   - the Filaments-row trash deletes the LAST filament
#   - a delete with NO dependent scheme is SILENT while the seeded scheme
#     survives
#   - deleting a filament referenced by a scheme raises the 'Warning'
#     confirm: Cancel keeps everything, OK cascades the scheme away
#   - deleting down to one filament hides the Color Mixing panel and the trash
#   - the mixing entry's Options menu offers Edit / Merge with / Delete;
#     merging the entry into a PHYSICAL filament removes the entry and leaves
#     the physical set untouched
#
# macOS mapping (two sessions):
#   trash      -> middle Filaments-header icon at window-relative (378,375)
#                 (the + is at 391,375; the row '...' menus are at y~448+)
#   options    -> the mixing entry's "..." at (191,562); the menu has
#                 Edit (198,584) / Merge with (196,608) / Delete (198,632);
#                 hovering Merge with flies out the physical targets at
#                 x~350, y 608/633/660/686/712; the first (Generic PETG) is
#                 clicked at (400,615)
#   warning    -> separate window title 'Warning' (~632,422,656,180) with
#                 OCR 'This filament is used in the following mixed filament
#                 configurations ... Continue?' and OK/Cancel at
#                 window-relative (724,476)/(826,478)
#
# Artifacts: artifacts/mac/pilot/m4d/{report.log,result.json,*.png}.

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
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m4d"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
TRASH = (378, 375)
ENTRY_DOTS = (191, 562)


def ocr_win(driver, win):
    return recognize_text(driver.capture(win))


def rows(driver, win):
    return len([w for w in ocr_win(driver, win)
                if w.rect.x < 330 and 400 < w.rect.y < 500
                and any(k in w.text.lower()
                        for k in ("petg", "pla", "silk"))])


def scheme_present(driver, win):
    return any("f3 50%" in w.text.lower() for w in ocr_win(driver, win))


def click_trash(driver, win):
    driver.click(win.rect.x + TRASH[0], win.rect.y + TRASH[1])
    time.sleep(1.5)


def warning_window(driver, app, win):
    for w in driver.windows_for_pid(app.pid):
        if (w.on_screen and w.id != win.id and w.layer != 0
                and "warning" in (w.title or "").lower()):
            return w
    return None


def warning_words(driver, win, w):
    return recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
             w.rect.w, w.rect.h))


def click_button(driver, win, words, label):
    target = next((q for q in words
                   if q.text.strip().lower() == label.lower()), None)
    if target is None:
        return False
    driver.click(win.rect.x + target.rect.center[0],
                 win.rect.y + target.rect.center[1])
    time.sleep(1.5)
    return True


def merge_session(driver, datadir, rep) -> None:
    """Session A: the seeded scheme -> Options -> Merge with -> physical 1."""
    app = None
    win = None
    try:
        app, win = launch_and_focus(driver, datadir, model=DEFAULT_MODEL,
                                    timeout_s=150.0,
                                    log_path=OUT / "app_launch_merge.log")
        ok, _f, _frac, _s = wait_for_model(driver, app, win, timeout_s=120.0)
        rep.check("A 载入 + 基线（5 耗材 + 方案）", ok
                  and rows(driver, win) == 5 and scheme_present(driver, win),
                  f"rows={rows(driver, win)} scheme={scheme_present(driver, win)}")
        driver.click(win.rect.x + ENTRY_DOTS[0],
                     win.rect.y + ENTRY_DOTS[1])
        time.sleep(1.0)
        texts = [w.text.lower() for w in ocr_win(driver, win)]
        rep.check("A 混色条目菜单（Edit/Merge with/Delete）",
                  "edit" in texts and "merge with" in texts
                  and "delete" in texts, str(texts[:8]))
        driver.move(win.rect.x + 210, win.rect.y + 608)
        time.sleep(1.5)
        flyout = [w for w in ocr_win(driver, win)
                  if w.rect.x > 340 and 600 < w.rect.y < 730]
        rep.log(f"[INFO] Merge 目标={[(w.text, w.rect.to_xywh()) for w in flyout]}")
        rep.check("A Merge with 子菜单列出物理耗材", len(flyout) >= 2,
                  f"targets={len(flyout)}")
        driver.click(win.rect.x + 400, win.rect.y + 615)
        time.sleep(2.0)
        rep.check("A 合并后条目消失、物理耗材不变",
                  not scheme_present(driver, win) and rows(driver, win) == 5,
                  f"scheme={scheme_present(driver, win)} rows={rows(driver, win)}")
        rep.check("A app alive", app.alive())
    finally:
        if app is not None:
            try:
                close_app(driver, app, win)
            except Exception:
                pass


def delete_session(driver, datadir, rep) -> None:
    """Session B: silent deletes -> Warning Cancel/OK -> down to one."""
    app = None
    win = None
    try:
        app, win = launch_and_focus(driver, datadir, model=DEFAULT_MODEL,
                                    timeout_s=150.0,
                                    log_path=OUT / "app_launch_delete.log")
        ok, _f, _frac, _s = wait_for_model(driver, app, win, timeout_s=120.0)
        rep.check("B 载入 + 基线（5 耗材 + 方案）", ok
                  and rows(driver, win) == 5 and scheme_present(driver, win),
                  f"rows={rows(driver, win)}")
        click_trash(driver, win)
        silent1 = warning_window(driver, app, win) is None
        rep.check("B 删除 F5 静默、方案保留",
                  silent1 and rows(driver, win) == 4
                  and scheme_present(driver, win),
                  f"rows={rows(driver, win)} scheme={scheme_present(driver, win)}")
        click_trash(driver, win)
        silent2 = warning_window(driver, app, win) is None
        rep.check("B 删除 F4 静默、方案保留",
                  silent2 and rows(driver, win) == 3
                  and scheme_present(driver, win),
                  f"rows={rows(driver, win)}")

        click_trash(driver, win)
        warn = warning_window(driver, app, win)
        rep.check("B 删除方案引用耗材弹出 Warning", warn is not None,
                  warn.rect.to_xywh() if warn else "no dialog")
        if warn is None:
            return
        words = warning_words(driver, win, warn)
        text = " ".join(w.text for w in words)
        driver.capture_screen().save_png(OUT / "warning.png")
        rep.log(f"[INFO] warning text={text[:200]!r}")
        rep.check("B Warning 文案（mixed filament configurations / Continue）",
                  "mixed filament configurations" in text.lower()
                  and "continue" in text.lower(), text[:160])
        rep.check("B Cancel 保留（盘数/方案不变）",
                  click_button(driver, win, words, "Cancel")
                  and rows(driver, win) == 3 and scheme_present(driver, win),
                  f"rows={rows(driver, win)} scheme={scheme_present(driver, win)}")

        click_trash(driver, win)
        warn2 = warning_window(driver, app, win)
        if warn2 is None:
            rep.check("B 再次删除弹出 Warning", False, "no second dialog")
            return
        words2 = warning_words(driver, win, warn2)
        rep.check("B OK 级联删除方案",
                  click_button(driver, win, words2, "OK")
                  and rows(driver, win) == 2
                  and not scheme_present(driver, win),
                  f"rows={rows(driver, win)} scheme={scheme_present(driver, win)}")

        click_trash(driver, win)
        panel = [w for w in ocr_win(driver, win)
                 if w.text.strip().lower() == "color mixing"
                 and w.rect.x < 200]
        rep.check("B 删到 1 个耗材：Color Mixing 面板隐藏",
                  rows(driver, win) == 1 and not panel,
                  f"rows={rows(driver, win)} panel={[w.rect.to_xywh() for w in panel]}")
        click_trash(driver, win)
        rep.check("B 只剩 1 个时 trash 不再删除", rows(driver, win) == 1,
                  f"rows={rows(driver, win)}")
        rep.check("B app alive", app.alive())
    finally:
        if app is not None:
            try:
                close_app(driver, app, win)
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    base = OUT / "datadir"
    merge_dir = base / "merge"
    delete_dir = base / "delete"
    for path in (merge_dir, delete_dir):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m4d macOS filament ops against mixing state ===")

    driver = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        merge_session(driver, merge_dir, rep)
        delete_session(driver, delete_dir, rep)
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        try:
            import subprocess
            subprocess.run(["pkill", "-f", "Snapmaker_Orca --datadir"],
                           capture_output=True)
        except Exception:
            pass
        exit_code = rep.save({"covered": ["#88", "#159"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
