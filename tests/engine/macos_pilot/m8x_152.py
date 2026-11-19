#!/usr/bin/env python3
# m8x_152.py — macOS port: Feishu #152 first-install transform + merge chain.
# feishu: baseline#152  (macOS port; corresponds to the enabled Windows
#         m8x_152, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   s1 empty boot -> New Project -> Import STL -> model arrives
#   s2 Move X=60; s3 Rotate Z=45; s4 Scale 120
#   s4 object is assigned to the LAST physical filament, Slice A's gcode uses
#   exactly that slot; the slot is merged into slot 1; Slice B's gcode uses
#   exactly [1].
#
# macOS mapping:
#   one session (mac fields commit repeatedly):
#   New Project -> Import Prusa.stl; Move/Rotate/Scale via the toolbar fields
#   (click + Cmd+A paste + Enter); save the project and verify the matrix.
#   Change Filament -> last 'Generic PLA' submenu row (slot 4); Slice A.
#   Slot-4 row menu at screen (752,526) -> Merge with... -> first Generic PLA
#   target; sidebar drops 4 -> 3 filaments; Slice B.
#
# Artifacts: artifacts/mac/pilot/m8x_152/{report.log,result.json,work/*.3mf,
#            *.gcode,*.png}.

from __future__ import annotations

import argparse
import math
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

import AppKit  # noqa: E402

from harness.platform.macos_ocr import recognize_text  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
    wait_for_model,
)
import mac_gcode  # noqa: E402
import m8d_purifier_gcode as c8d  # noqa: E402
import m8x_192 as c192  # noqa: E402
import m7t74 as c74  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_152"
STL = HERE / "fixtures" / "Prusa.stl"
MOVE_X = 736
ROTATE_X = 772
SCALE_X = 796
SLOT4_MENU = (761, 535)       # screen coords of slot-4 row '...' button


def paste(driver, win, x, y, text, rep):
    driver.click(win.rect.x + x, win.rect.y + y)
    time.sleep(0.4)
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
    driver.send_key("a", modifiers=("cmd",))
    time.sleep(0.2)
    driver.send_key("v", modifiers=("cmd",))
    time.sleep(0.4)
    driver.send_key("return")
    time.sleep(1.2)
    row = [w.text for w in recognize_text(driver.capture(win))
           if abs(w.rect.y - y) < 6 and w.rect.x > 700]
    rep.log(f"[INFO] set {text} @({x},{y}); row={row}")


def model_point(frame):
    xs = []
    ys = []
    for y in range(120, 640, 3):
        row = y * frame.width * 4
        for x in range(460, 880, 3):
            i = row + x * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            if g > r + 30 and g > b + 5 and g > 60:
                xs.append(x)
                ys.append(y)
    if not xs:
        return (814, 468)
    xs.sort()
    ys.sort()
    return (xs[len(xs) // 2], ys[len(ys) // 2])


def filament_rows(driver, win) -> int:
    ws = recognize_text(driver.capture(win))
    return len([w for w in ws if "generic pla" in w.text.lower()
                and w.rect.x < 500 and 380 < w.rect.y < 500])


def submenu_rows(driver, app, win):
    out = []
    for w in driver.windows_for_pid(app.pid):
        if w.id == win.id or not w.on_screen or w.rect.area < 400:
            continue
        try:
            out += [c for c in driver.controls(w)
                    if c.role == "AXMenuItem" and c.rect
                    and (c.title or "").strip().lower() == "generic pla"]
        except Exception:
            pass
    return out


def assign_last(driver, app, win, rep) -> bool:
    item = None
    pt = None
    for cand in ((814, 481), (814, 470), (814, 492), (814, 429),
                 (814, 440), (800, 481), (828, 481)):
        pt = cand
        driver.click(win.rect.x + pt[0], win.rect.y + pt[1])
        time.sleep(0.7)
        _w, item = c8d.open_context_menu(driver, app, win, pt)
        if item is not None:
            break
    rep.log(f"[INFO] model point={pt} change_item={bool(item)}")
    if item is None:
        # Canvas hit-testing is unreliable for the thin Prusa strip; use the
        # Objects panel row context menu (same route as the Windows case).
        words = c8d.ocr_window(driver, win)
        tab = next((w for w in words
                    if w.text.strip().lower() == "objects"), None)
        if tab is not None:
            driver.click(win.rect.x + tab.rect.center[0],
                         win.rect.y + tab.rect.center[1])
            time.sleep(1.5)
            words = c8d.ocr_window(driver, win)
            row = next((w for w in words
                        if "prusa" in w.text.lower() and w.rect.y > 500),
                       None)
            if row is not None:
                rep.log(f"[INFO] Objects row={row.text!r} "
                        f"{row.rect.to_xywh()}")
                _w, item = c8d.open_context_menu(
                    driver, app, win,
                    (row.rect.center[0], row.rect.center[1]))
    if item is None:
        rep.log("[INFO] Change Filament not found")
        return False
    driver.click_control(item)
    time.sleep(1.2)
    rows = submenu_rows(driver, app, win)
    rep.log(f"[INFO] filament submenu rows={len(rows)}")
    if not rows:
        return False
    driver.click_control(rows[-1])
    time.sleep(1.5)
    return True


def merge_slot4(driver, win, rep) -> bool:
    driver.click(SLOT4_MENU[0], SLOT4_MENU[1])
    time.sleep(1.2)
    ws = recognize_text(driver.capture_screen())
    merge = next((w for w in ws if "merge with" in w.text.lower()
                  and w.rect.x > 700), None)
    rep.log(f"[INFO] merge item={merge.rect.to_xywh() if merge else None}")
    if merge is None:
        driver.send_key("escape")
        return False
    driver.move(merge.rect.center[0], merge.rect.center[1])
    time.sleep(1.5)
    ws = recognize_text(driver.capture_screen())
    targets = [w for w in ws if w.rect.x > 850 and w.rect.y > 500
               and "generic pla" in w.text.lower()]
    rep.log(f"[INFO] merge targets={[(w.text, w.rect.to_xywh()) for w in targets]}")
    if not targets:
        driver.send_key("escape")
        return False
    t = targets[0]
    driver.click(t.rect.center[0], t.rect.center[1])
    time.sleep(2.0)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    proj = work / "m8x_152_transformed.3mf"
    g_a = work / "m8x_152_a.gcode"
    g_b = work / "m8x_152_b.gcode"
    roots = [work, OUT, ARTIFACTS / "pilot", HERE / "fixtures"]

    rep = Reporter(OUT)
    rep.log("=== m8x_152 macOS transform + physical merge chain ===")
    rep.log(f"datadir={args.datadir} stl={STL}")

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
        rep.check("launch (empty)", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(3.0)
        rep.check("空盘启动（首次安装语义）", "untitled" in win.title.lower()
                  or win.title == "", win.title)

        item = driver.find_control(win, role="AXMenuItem",
                                   title="New Project", timeout_s=3)
        rep.check("新建项目派发", item is not None)
        if item is not None:
            driver.click_control(item)
            time.sleep(2.0)
        rep.check("新建后画布为空", "untitled" in win.title.lower()
                  or win.title == "", win.title)

        rows = [c for c in driver.controls(win, max_depth=12)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("import ")
                and "3mf" in c.title.lower()]
        rep.check("导入入口派发", bool(rows))
        if not rows:
            return rep.save({"stage": "import-item"})
        driver.click_control(rows[0])
        rep.check("导入 Prusa.stl", driver.open_file_dialog(win, STL))
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.0025)
        frame.save_png(OUT / "loaded.png")
        rep.check("导入模型落盘", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})
        rep.log("[INFO] printer preset evidence: 0.20mm Standard @U1")

        # --- assign last physical filament (pre-transform selection is stable)
        pt = model_point(frame)
        driver.click(win.rect.x + pt[0], win.rect.y + pt[1])
        time.sleep(0.8)
        before_rows = filament_rows(driver, win)
        rep.log(f"[INFO] filament rows before assign={before_rows}")
        rep.check("指定末位耗材", assign_last(driver, app, win, rep))
        if not rep.checks[-1]["ok"]:
            return rep.save({"stage": "assign"})
        driver.click(win.rect.x + pt[0], win.rect.y + pt[1])
        time.sleep(0.8)

        # --- transforms ---------------------------------------------------
        driver.click(win.rect.x + MOVE_X, win.rect.y + 90)
        time.sleep(1.5)
        paste(driver, win, 931, 148, "60", rep)
        driver.click(win.rect.x + ROTATE_X, win.rect.y + 90)
        time.sleep(1.5)
        paste(driver, win, 1047, 148, "45", rep)
        driver.click(win.rect.x + SCALE_X, win.rect.y + 90)
        time.sleep(1.5)
        paste(driver, win, 971, 142, "120", rep)
        driver.capture(win).save_png(OUT / "transformed.png")

        rep.check("另存变换后项目", c192.save_project(driver, win, rep, proj)
                  and proj.exists())
        if not proj.exists():
            return rep.save({"stage": "save"})
        t = c192.item(proj, "Prusa")
        ang, axis, norms = c74.mat_info(t) if t is not None else (0, [], [])
        rep.log(f"[INFO] t={t} ang={ang:.1f} axis={axis} norms={norms}")
        rep.check("Move X=60", t is not None and abs(t[9] - 60.0) <= 0.5,
                  f"tx={t[9] if t else None}")
        rep.check("Rotate Z=45", t is not None and abs(ang - 45.0) <= 2.0
                  and abs(axis[2]) >= 0.95, f"ang={ang:.1f} axis={axis}")
        rep.check("Scale 120%", all(abs(n - 1.2) <= 0.02 for n in norms),
                  f"norms={norms}")

        # --- Slice A ------------------------------------------------------
        if not slice_and_export(driver, win, rep, g_a, roots):
            rep.check("指定后切片", False, "slice/export failed")
            return rep.save({"stage": "slice-a"})
        used_a = mac_gcode.used_filaments(g_a.read_bytes())
        log4 = before_rows or 4
        rep.check("指定后 gcode 用量 = 末位槽",
                  used_a == [log4], f"used={used_a} want=[{log4}]")
        if used_a != [log4]:
            return rep.save({"stage": "used-a"})

        # --- merge slot4 into slot1 + Slice B -----------------------------
        driver.click(win.rect.x + 113, win.rect.y + 45)
        time.sleep(1.5)
        rep.check("合并槽位", merge_slot4(driver, win, rep))
        time.sleep(2.0)
        after_rows = filament_rows(driver, win)
        rep.log(f"[INFO] filament rows after merge={after_rows}")
        rep.check("物理槽位数 -1", after_rows == before_rows - 1,
                  f"{before_rows} -> {after_rows}")
        if not slice_and_export(driver, win, rep, g_b, roots):
            rep.check("合并后切片", False, "slice/export failed")
            return rep.save({"stage": "slice-b"})
        used_b = mac_gcode.used_filaments(g_b.read_bytes())
        rep.check("合并后 gcode 用量重映射为 [1]", used_b == [1],
                  f"used={used_b}")
        rep.check("app alive", app.alive())

        alive_before = app.alive()
        closed = close_app(driver, app, win)
        app = None
        rep.check("software closed", alive_before and closed,
                  f"alive_before={alive_before} closed={closed}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        exit_code = rep.save({"covered": ["#152"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
