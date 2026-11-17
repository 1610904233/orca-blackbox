#!/usr/bin/env python3
# m8x_207_pa_invalid.py — macOS port: Feishu #207 PA calibration invalid input.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_207,
#         registered in cases.MACOS_BASELINE)
#
# Windows flow: Calibration > Pressure advance -> PA Calibration -> invalid
# Start PA (abc / empty / "1a！@") -> every OK raises a warning, the PA dialog
# stays open and no model is generated.
#
# macOS mapping:
#   PA dialog      -> native "PA Calibration" window (322x446); the five
#                     fields are AXTextFields (Start/End/Step/Accelerations/
#                     Speeds) and accept AXSetValue.
#   OK             -> OCR-located "OK" + real click (AX buttons have empty
#                     titles and no rects on this dialog).
#   warning        -> "Snapmaker Orca info" window whose text reads
#                     "Please input valid values: Start PA: >= 0.0 ...".
#   no model       -> viewport chromatic fraction stays at the empty-bed level.
#
# Artifacts: artifacts/mac/pilot/m8x_207/{report.log,result.json,*.png}.

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

import ApplicationServices as AS  # noqa: E402

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import m7b_new_project as m7b  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_207"
WARN_TITLE = "Snapmaker Orca info"
WARN_KEYWORDS = ("valid", "start pa")


def _copy(elem, attr):
    err, value = AS.AXUIElementCopyAttributeValue(elem, attr, None)
    return value if err == 0 else None


def _role(elem):
    value = _copy(elem, AS.kAXRoleAttribute)
    return value if isinstance(value, str) else ""


def walk(root, max_depth=12):
    stack = [(root, 0)]
    seen = set()
    keep = [root]
    while stack:
        elem, depth = stack.pop()
        key = id(elem)
        if key in seen:
            continue
        seen.add(key)
        yield elem, depth
        if depth >= max_depth:
            continue
        children = _copy(elem, AS.kAXChildrenAttribute)
        if children:
            keep.extend(children)
            for child in reversed(list(children)):
                stack.append((child, depth + 1))


def window_by_title(driver, app, needle, timeout_s=8.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for w in driver.windows_for_pid(app.pid):
            if w.on_screen and needle.lower() in (w.title or "").lower():
                if w.handle is None:
                    driver._attach_ax_window(w)
                return w
        time.sleep(0.3)
    return None


def ocr_words(driver, win):
    return recognize_text(driver.capture_screen().crop(win.rect))


def click_word(driver, win, word):
    driver.click(win.rect.x + word.rect.center[0],
                 win.rect.y + word.rect.center[1])


def click_ok(driver, win) -> bool:
    word = next((w for w in ocr_words(driver, win)
                 if w.text.strip().lower() == "ok"), None)
    if word is None:
        return False
    click_word(driver, win, word)
    return True


def pa_fields(dlg):
    return [e for e, _d in walk(dlg.handle) if _role(e) == "AXTextField"]


def open_pa(driver, win) -> bool:
    calib = next((c for c in driver.controls(win, max_depth=12)
                  if c.role == "AXMenuBarItem"
                  and c.title.strip().lower() == "calibration"), None)
    if calib is None or not driver.click_control(calib):
        return False
    time.sleep(0.8)
    row = next((c for c in driver.controls(win, max_depth=14)
                if c.role == "AXMenuItem"
                and "pressure advance" in c.title.lower()), None)
    return bool(row is not None and driver.click_control(row))


def dismiss_warning(driver, warning) -> bool:
    ok = next((w for w in ocr_words(driver, warning)
               if w.text.strip().lower() == "ok"), None)
    if ok is not None:
        click_word(driver, warning, ok)
        time.sleep(1.0)
        return True
    driver.send_key("return")
    time.sleep(1.0)
    return True


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
    rep.log("=== m8x_207 macOS PA calibration invalid input ===")
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
        frac0 = m7b._vp_colored(driver.capture(win))
        rep.log(f"[INFO] empty bed viewport={frac0:.4f}")

        rep.check("打开 Calibration > Pressure advance", open_pa(driver, win))
        dlg = window_by_title(driver, app, "PA Calibration")
        rep.check("PA Calibration 对话框打开", dlg is not None,
                  f"rect={dlg.rect.to_xywh() if dlg else None}")
        if dlg is None:
            raise RuntimeError("PA dialog missing")

        fields = pa_fields(dlg)
        rep.check("Start PA 字段可定位", bool(fields),
                  f"fields={len(fields)} values="
                  f"{[str(_copy(f, AS.kAXValueAttribute)) for f in fields]}")
        if not fields:
            raise RuntimeError("no PA fields")
        start = fields[0]

        cases = (
            ("A", "abc", "A 输入 abc 被拒（警告框）"),
            ("B", "", "B 清空后确定被拒（警告框）"),
            ("C", "1a\uff01@", "C 粘贴 1a！@ 被拒（警告框）"),
        )
        for tag, value, label in cases:
            frac_before = m7b._vp_colored(driver.capture(win))
            ok_set = AS.AXUIElementSetAttributeValue(
                start, AS.kAXValueAttribute, value) == 0
            time.sleep(0.4)
            readback = _copy(start, AS.kAXValueAttribute)
            rep.check(f"{tag} 输入进入字段", ok_set and readback == value,
                      f"readback={readback!r}")
            driver.capture_screen().crop(dlg.rect).save_png(
                OUT / f"{tag}_before_ok.png")

            known = {w.id for w in driver.windows_for_pid(app.pid) if w.on_screen}
            clicked = click_ok(driver, dlg)
            time.sleep(2.5)
            warning = next(
                (w for w in driver.windows_for_pid(app.pid)
                 if w.on_screen and w.id not in known and w.id != dlg.id
                 and w.id != win.id and "info" in (w.title or "").lower()),
                None)
            if warning is None:
                rep.log(f"[INFO] {tag}: first OK swallowed, retry")
                click_ok(driver, dlg)
                time.sleep(2.5)
                warning = next(
                    (w for w in driver.windows_for_pid(app.pid)
                     if w.on_screen and w.id not in known and w.id != dlg.id
                     and w.id != win.id and "info" in (w.title or "").lower()),
                    None)
            text = ""
            if warning is not None:
                if warning.handle is None:
                    driver._attach_ax_window(warning)
                driver.capture_screen().crop(warning.rect).save_png(
                    OUT / f"{tag}_warning.png")
                text = " ".join(w.text for w in ocr_words(driver, warning))
                rep.log(f"[INFO] {tag} warning: {text!r}")
            ok_warn = any(k in text.lower() for k in WARN_KEYWORDS)
            rep.check(label, clicked and warning is not None and ok_warn,
                      f"warning={text[:80]!r}")
            if warning is not None:
                dismiss_warning(driver, warning)
            still = window_by_title(driver, app, "PA Calibration", timeout_s=2.0)
            rep.check(f"{tag} 警告后 PA 对话框仍在", still is not None)
            frac = m7b._vp_colored(driver.capture(win))
            rep.check(f"{tag} 未生成模型", frac <= frac_before + 0.005,
                      f"viewport {frac_before:.4f}->{frac:.4f}")
            dlg = still or dlg
            fields = pa_fields(dlg)
            start = fields[0] if fields else start

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
        exit_code = rep.save({"covered": ["#207"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
