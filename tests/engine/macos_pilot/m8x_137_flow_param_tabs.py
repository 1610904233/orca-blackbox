#!/usr/bin/env python3
# m8x_137_flow_param_tabs.py — macOS port: Feishu #137 Standard/High Flow.
# feishu: baseline#137  (macOS port; corresponds to the enabled Windows
#         m8x_137_flow_param_tabs, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   A. the STD-TEST process/filament flow packs select successfully
#   B. the material editor exposes [Standard flow] / [High flow]
#   C. flow-marked parameters differ per mode (print temperature 210/220) and
#      editing one mode does not leak into the other
#   D. an unmarked parameter (Idle temperature) syncs across both modes
#   E. the process sidebar exposes Speed after Advanced ON; its flow-marked
#      speed values differ per mode (60/50, 100/105, ...) and editing one
#      mode does not leak; Advanced is restored afterwards
#
# macOS mapping:
#   empty boot -> right-click cube.  Adding the cube auto-slices and a
#   'Warning' sheet asks to close the generated gcode; Yes returns to an
#   unsliced Untitled project, then the Prepare tab is clicked.
#   presets -> doc default.zip's prepared 标准测试 process/filament (the
#              same flow-marked values the Windows STD-TEST package carries).
#   editor  -> slot-2 row menu (196,418) -> Edit (198,446); its color panel
#              ('Colors') is closed first.  Tab text OCRs as
#              '[Standard flow] [High flow]'; left/right thirds are the tabs.
#   fields  -> AXTextField snapshots by screen rect; AXSetValue + AXConfirm.
#   process -> Advanced switch at the OCR 'Advanced' label's right edge;
#              Speed tab at (164,603); flow tabs at the top of the page.
#
# Artifacts: artifacts/mac/pilot/m8x_137/{report.log,result.json,*.png}.

from __future__ import annotations

import argparse
import re
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

import ApplicationServices as AS  # noqa: E402

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos import _ax_perform, _ax_set  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, teal_fraction,
)
import m7b_new_project as m7b  # noqa: E402
import m8f_nozzle_flow as c8f  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_137"
PREP = Rect(55, 31, 115, 29)
EDITOR_FIRST_TEMP = (972, 667)     # screen coords (AX field centres)
EDITOR_OTHER_TEMP = (1216, 667)
EDITOR_IDLE = (872, 403)
SPEED_FILTER = (180, 600, 330, 950)  # window-relative AX field area on Speed


def ocr_window(driver, win):
    return recognize_text(driver.capture(win))


def dlg_words(driver, win, dlg):
    return recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(dlg.rect.x - win.rect.x, dlg.rect.y - win.rect.y,
             dlg.rect.w, dlg.rect.h))


def find_word(words, needle):
    return next((w for w in words if needle.lower() in w.text.lower()), None)


def warning_window(driver, app):
    return next((w for w in driver.windows_for_pid(app.pid)
                 if w.on_screen and (w.title or "").lower() == "warning"), None)


def dismiss_warning(driver, app, win, rep) -> bool:
    w = warning_window(driver, app)
    if w is None:
        return False
    words = recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(w.rect.x - win.rect.x, w.rect.y - win.rect.y,
             w.rect.w, w.rect.h))
    rep.log(f"[INFO] Warning: {[x.text for x in words]}")
    yes = next((x for x in words if x.text.strip().lower() == "yes"), None)
    if yes is None:
        return False
    driver.click(win.rect.x + yes.rect.center[0],
                 win.rect.y + yes.rect.center[1])
    time.sleep(1.5)
    return True


def ensure_prepare(driver, app, win, rep) -> bool:
    """Switch to Prepare, clearing the generated-gcode Warning first."""
    for _ in range(4):
        if warning_window(driver, app) is not None:
            dismiss_warning(driver, app, win, rep)
            time.sleep(1.2)
            continue
        driver.click(win.rect.x + 113, win.rect.y + 45)
        time.sleep(1.5)
        if warning_window(driver, app) is not None:
            dismiss_warning(driver, app, win, rep)
            time.sleep(1.2)
            continue
        if teal_fraction(driver.capture(win), PREP) > 0.5:
            return True
    return False


def open_editor(driver, app, win):
    # The filament row's right-side round button opens Edit/Delete/Merge;
    # clicking the name itself only focuses the preset combo in this build.
    driver.click(win.rect.x + 399, win.rect.y + 418)
    time.sleep(1.0)
    words = recognize_text(driver.capture_screen().crop(win.rect))
    edit_word = next((w for w in words if w.text.strip().lower() == "edit"
                      and w.rect.y > 420 and w.rect.x > 350), None)
    if edit_word is not None:
        driver.click(win.rect.x + edit_word.rect.center[0],
                     win.rect.y + edit_word.rect.center[1])
    else:
        driver.click(win.rect.x + 198, win.rect.y + 446)
    time.sleep(2.5)
    return next((w for w in driver.windows_for_pid(app.pid)
                 if w.on_screen
                 and "material settings" in (w.title or "").lower()), None)


def close_colors(driver, app) -> bool:
    w = next((w for w in driver.windows_for_pid(app.pid)
              if w.on_screen and (w.title or "").lower() == "colors"), None)
    if w is None:
        return True
    driver.click(w.rect.x + 12, w.rect.y + 12)
    time.sleep(1.0)
    return not any(x.on_screen and (x.title or "").lower() == "colors"
                   for x in driver.windows_for_pid(app.pid))


def fields(driver, dlg):
    return [(c, str(c.value), c.rect.center)
            for c in driver.controls(dlg)
            if c.role == "AXTextField" and c.handle is not None
            and c.rect is not None]


def field_at(driver, dlg, center, tol=10):
    for c, value, _pt in fields(driver, dlg):
        if (abs(c.rect.center[0] - center[0]) <= tol
                and abs(c.rect.center[1] - center[1]) <= tol):
            return c, value
    return None, None


def set_field(driver, fld, value: str) -> None:
    if fld is None or fld.handle is None:
        return
    _ax_set(fld.handle, AS.kAXValueAttribute, value)
    time.sleep(0.3)
    if "AXConfirm" in (fld.actions or ()):
        _ax_perform(fld.handle, "AXConfirm")
    # The AX value updates asynchronously; callers re-read after a short wait.
    time.sleep(1.2)


def flow_tab_click(driver, win, dlg, word, which: str):
    """'[Standard flow] [High flow]' OCRs as one word; click its thirds."""
    if "standard" in word.text.lower() and "high" in word.text.lower():
        x = word.rect.x + 40 if which == "standard" else word.rect.right - 30
    else:
        target = find_word([word], "standard" if which == "standard" else "high")
        x = target.rect.center[0] if target else word.rect.center[0]
    driver.click(win.rect.x + x, win.rect.y + word.rect.center[1])
    time.sleep(1.5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    c8f.prepare_doc_presets(args.datadir)

    rep = Reporter(OUT)
    rep.log("=== m8x_137 macOS Standard/High Flow parameter tabs ===")
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
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        rep.check("empty boot (no fixture)", True, win.title)
        time.sleep(4.0)
        rep.check("cube created", m7b._add_cube(driver, app, win))
        time.sleep(3.0)
        rep.check("Prepare ready", ensure_prepare(driver, app, win, rep))
        driver.capture(win).save_png(OUT / "prepare.png")

        # --- A: doc 标准测试 flow pack -------------------------------------
        ok = c8f.select_state(driver, win, rep, "STD", "STD", "Standard", "137")
        rep.check("#137 工艺/耗材预设 = 标准测试包（doc default.zip）", ok)
        if not ok:
            # a late Warning can appear right after the menus; clear + retry
            ensure_prepare(driver, app, win, rep)
            ok = c8f.select_state(driver, win, rep, "STD", "STD",
                                  "Standard", "137-retry")
            rep.check("#137 预设重试", ok)
        if not ok:
            return rep.save({"stage": "presets"})
        driver.capture(win).save_png(OUT / "presets.png")

        # --- B/C/D: material editor ---------------------------------------
        dlg = open_editor(driver, app, win)
        rep.check("#137 耗材编辑器打开", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({"stage": "editor"})
        rep.check("颜色面板已关闭", close_colors(driver, app))
        driver.capture(win).save_png(OUT / "editor.png")
        words = dlg_words(driver, win, dlg)
        text = " ".join(w.text for w in words).lower()
        rep.check("#137 出现 Standard/High Flow 两个 tab",
                  "standard flow" in text and "high flow" in text,
                  text[:160])
        flow_word = find_word(words, "high flow")
        if flow_word is None:
            return rep.save({"stage": "flow-tabs"})

        std_snap = {pt: v for _c, v, pt in fields(driver, dlg)}
        flow_tab_click(driver, win, dlg, flow_word, "high")
        hf_snap = {pt: v for _c, v, pt in fields(driver, dlg)}
        diff = [(pt, std_snap.get(pt), v) for pt, v in hf_snap.items()
                if std_snap.get(pt) != v]
        rep.log(f"[INFO] Standard->High Flow field diff={diff}")
        rep.check("#137 带标志参数在两模式取值不同", len(diff) >= 1,
                  f"diff={diff}")
        rep.check("#137 喷嘴温度 210->220（包内两档）",
                  any(a == "210" and b == "220" for _pt, a, b in diff),
                  f"diff={diff}")
        driver.capture(win).save_png(OUT / "editor_highflow.png")

        # --- C2: edit a marked field on Standard; High Flow stays put -----
        flow_tab_click(driver, win, dlg, flow_word, "standard")
        fld, before = field_at(driver, dlg, EDITOR_FIRST_TEMP)
        set_field(driver, fld, "235")
        _fld2, landed = field_at(driver, dlg, EDITOR_FIRST_TEMP)
        rep.check("C2 Standard 喷嘴温度改 235 生效",
                  before == "210" and landed == "235",
                  f"{before!r} -> {landed!r}")
        flow_tab_click(driver, win, dlg, flow_word, "high")
        fld_hf, hf_val = field_at(driver, dlg, EDITOR_FIRST_TEMP)
        hf_all = [v for _c, v, _pt in fields(driver, dlg)]
        rep.check("C2 High Flow 不受影响",
                  hf_val == "220" and "235" not in hf_all,
                  f"hf={hf_val!r} values={hf_all}")
        flow_tab_click(driver, win, dlg, flow_word, "standard")
        fld_std, std_val = field_at(driver, dlg, EDITOR_FIRST_TEMP)
        rep.check("C2 返回 Standard 仍为 235", std_val == "235",
                  f"std={std_val!r}")
        set_field(driver, fld_std, "210")

        # --- D: unmarked Idle temperature syncs across tabs ---------------
        flow_tab_click(driver, win, dlg, flow_word, "high")
        idle, idle0 = field_at(driver, dlg, EDITOR_IDLE)
        set_field(driver, idle, "5")
        _idle_set_fld, idle_set = field_at(driver, dlg, EDITOR_IDLE)
        flow_tab_click(driver, win, dlg, flow_word, "standard")
        _idle_std, idle_std = field_at(driver, dlg, EDITOR_IDLE)
        rep.check("#137 不带标志参数(Idle temperature)两模式同步",
                  idle0 == "0" and idle_set == "5" and idle_std == "5",
                  f"{idle0!r} -> {idle_set!r}; std={idle_std!r}")
        flow_tab_click(driver, win, dlg, flow_word, "high")
        _idle2, idle2 = field_at(driver, dlg, EDITOR_IDLE)
        if _idle2 is not None:
            set_field(driver, _idle2, "0")
        driver.capture(win).save_png(OUT / "editor_idle.png")

        driver.click(dlg.rect.x + 10, dlg.rect.y + 8)
        time.sleep(2.0)
        rep.check("#137 耗材编辑器已关闭",
                  not any(w.on_screen and "material settings" in
                          (w.title or "").lower()
                          for w in driver.windows_for_pid(app.pid)))

        # --- E: process sidebar Advanced -> Speed -------------------------
        words = ocr_window(driver, win)
        adv = next((w for w in words if w.text.strip().lower() == "advanced"
                    and w.rect.y > 400), None)
        rep.check("#137 找到 Advanced 开关", adv is not None)
        if adv is None:
            return rep.save({"stage": "advanced"})
        # The simple sidebar puts the switch inside the OCR word's right
        # edge; the wide layout puts it just outside.  Try both and look for
        # the Speed tab that Advanced reveals.
        speed_word = None
        for dx in (-12, 10, -24):
            driver.click(win.rect.x + adv.rect.right + dx,
                         win.rect.y + adv.rect.center[1])
            time.sleep(1.2)
            words = ocr_window(driver, win)
            # At 420px the tab bar OCR merges the middle labels, e.g.
            # 'Strength Speed Support Multimaterial'; accept any word
            # containing Speed and click the fixed Speed tab x.
            speed_word = next((w for w in words
                               if "speed" in w.text.lower()
                               and 500 < w.rect.y < 580), None)
            if speed_word is not None:
                break
        rep.check("#137 Advanced 打开后出现 Speed 页签", speed_word is not None)
        if speed_word is None:
            return rep.save({"stage": "speed-tab"})
        speed_x = (speed_word.rect.center[0]
                   if speed_word.text.strip().lower() == "speed" else 164)
        driver.click(win.rect.x + speed_x,
                     win.rect.y + speed_word.rect.center[1])
        time.sleep(2.0)
        driver.capture(win).save_png(OUT / "advanced_on.png")
        words = ocr_window(driver, win)
        flows = [w for w in words if "flow" in w.text.lower()
                 and w.rect.y > 500]
        rep.log(f"[INFO] process flow tabs={[(w.text, w.rect.to_xywh()) for w in flows]}")
        rep.check("#137 工艺侧 Speed 页出现 Standard/High Flow 两个 tab",
                  bool(flows) and "standard flow" in flows[0].text.lower()
                  and "high flow" in flows[0].text.lower(),
                  f"flows={[w.text for w in flows]}")
        if not flows:
            return rep.save({"stage": "speed"})
        pflow = flows[0]

        def speed_fields():
            out = []
            for c in driver.controls(win):
                if (c.role != "AXTextField" or c.rect is None
                        or c.handle is None):
                    continue
                x = c.rect.x - win.rect.x
                y = c.rect.y - win.rect.y
                if (SPEED_FILTER[0] <= x <= SPEED_FILTER[2]
                        and SPEED_FILTER[1] <= y <= SPEED_FILTER[3]):
                    out.append((c, str(c.value), c.rect.center))
            return out

        # process flow tabs live in the main window, no dialog frame
        if "standard" in pflow.text.lower() and "high" in pflow.text.lower():
            driver.click(win.rect.x + pflow.rect.x + 40,
                         win.rect.y + pflow.rect.center[1])
        else:
            driver.click(win.rect.x + pflow.rect.center[0],
                         win.rect.y + pflow.rect.center[1])
        time.sleep(1.8)
        a_vals = [(v, pt) for _c, v, pt in speed_fields()]
        driver.capture(win).save_png(OUT / "speed_standard.png")
        if "standard" in pflow.text.lower() and "high" in pflow.text.lower():
            driver.click(win.rect.x + pflow.rect.right - 30,
                         win.rect.y + pflow.rect.center[1])
        time.sleep(1.8)
        b_vals = [(v, pt) for _c, v, pt in speed_fields()]
        rep.log(f"[INFO] speed standard={a_vals} high={b_vals}")
        moved = [(av, bv) for (av, ap), (bv, bp) in zip(a_vals, b_vals)
                 if av != bv]
        pack_pairs = {("60", "50"), ("100", "105"), ("90%", "100%"),
                      ("1", "0"), ("550", "600"), ("550", "500")}
        hit = [p for p in moved if p in pack_pairs]
        rep.check("#137 工艺带标志速度参数在两模式取值不同",
                  len(moved) >= 1, f"moved={moved}")
        rep.check("#137 工艺速度参数命中包内两档值", len(hit) >= 1,
                  f"hit={hit} moved={moved}")

        # --- E2: edit a marked speed param only on Standard ---------------
        if "standard" in pflow.text.lower() and "high" in pflow.text.lower():
            driver.click(win.rect.x + pflow.rect.x + 40,
                         win.rect.y + pflow.rect.center[1])
        time.sleep(1.8)
        target = next(((c, v) for c, v, _pt in speed_fields() if v == "60"),
                      None)
        rep.check("E2 找到 Standard 首层速度=60", target is not None)
        if target is not None:
            c60, _v = target
            set_field(driver, c60, "66")
            if "standard" in pflow.text.lower() and "high" in pflow.text.lower():
                driver.click(win.rect.x + pflow.rect.right - 30,
                             win.rect.y + pflow.rect.center[1])
            time.sleep(1.8)
            hf_vals = [v for _c, v, _pt in speed_fields()]
            rep.check("E2 High Flow 保持 50 且无 66",
                      "50" in hf_vals and "66" not in hf_vals,
                      f"hf={hf_vals}")
            if "standard" in pflow.text.lower() and "high" in pflow.text.lower():
                driver.click(win.rect.x + pflow.rect.x + 40,
                             win.rect.y + pflow.rect.center[1])
            time.sleep(1.8)
            std_vals = [v for _c, v, _pt in speed_fields()]
            rep.check("E2 返回 Standard 仍为 66", "66" in std_vals,
                      f"std={std_vals}")
            c66 = next((c for c, v, _pt in speed_fields() if v == "66"), None)
            if c66 is not None:
                set_field(driver, c66, "60")
            driver.capture(win).save_png(OUT / "speed_after_edit.png")

        # restore the Advanced switch
        words = ocr_window(driver, win)
        adv = next((w for w in words if w.text.strip().lower() == "advanced"
                    and w.rect.y > 400), None)
        if adv is not None:
            driver.click(win.rect.x + adv.rect.right - 12,
                         win.rect.y + adv.rect.center[1])
            time.sleep(1.5)
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
        exit_code = rep.save({"covered": ["#137"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
