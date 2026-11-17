#!/usr/bin/env python3
# m8x_198_plate_name.py — macOS port: Feishu #198 edit plate name.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_198,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions (2.4.2 baseline):
#   A) all-spaces name is accepted (dialog closes; no length/whitespace rule)
#   B) "B@#1" is accepted and the saved plater_name matches exactly
#   C) a 100-char name is accepted and saved with length 100
#
# macOS mapping:
#   entry     -> plate rail "Customize current plate" at (1070,300)
#   dialog    -> "Plate Settings": one AXTextField (Plate name); OK/Cancel are
#                custom-drawn, so OK is clicked via OCR.
#   readback  -> Metadata/model_settings.config plater_name values.
#
# Artifacts: artifacts/mac/pilot/m8x_198/{report.log,result.json,work/*.3mf}.

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
import AppKit  # noqa: E402

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import mac_3mf  # noqa: E402
import m8x_202_save_as as c202  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_198"
DEFAULT_MODEL = HERE / "fixtures" / "snapmates_nonmixed.3mf"
CUSTOMIZE_XY = (1070, 300)


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


def window_by_title(driver, app, needle, timeout_s=6.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for w in driver.windows_for_pid(app.pid):
            if w.on_screen and needle.lower() in (w.title or "").lower():
                if w.handle is None:
                    driver._attach_ax_window(w)
                return w
        time.sleep(0.3)
    return None


def open_plate_settings(driver, win, app):
    driver.click(win.rect.x + CUSTOMIZE_XY[0],
                 win.rect.y + CUSTOMIZE_XY[1])
    return window_by_title(driver, app, "Plate Settings")


def name_field(dlg):
    return next((e for e, _d in walk(dlg.handle)
                 if _role(e) == "AXTextField"), None)


def _paste(driver, text: str) -> None:
    pb = AppKit.NSPasteboard.generalPasteboard()
    old = pb.stringForType_(AppKit.NSPasteboardTypeString)
    pb.clearContents()
    pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
    driver.send_key("v", modifiers=("cmd",))
    time.sleep(0.8)
    if old:
        pb.clearContents()
        pb.setString_forType_(old, AppKit.NSPasteboardTypeString)


def _field_text(driver, dlg) -> str:
    words = recognize_text(driver.capture_screen().crop(dlg.rect))
    return " ".join(w.text for w in words
                    if w.rect.x > 300 and 55 <= w.rect.y <= 100).strip()


def rename(driver, win, app, value):
    """Open Plate Settings, replace the name with real input, press OK.

    The name control has no AX rect and AXSetValue disables OK (no change
    event), so: click the title bar, click the field twice, Cmd+A/Backspace,
    paste, then AXPress the first AXButton (OK).
    """
    dlg = open_plate_settings(driver, win, app)
    if dlg is None:
        return None, False
    driver.click(dlg.rect.x + 325, dlg.rect.y + 10)
    time.sleep(0.3)
    for _ in range(2):
        driver.click(dlg.rect.x + 500, dlg.rect.y + 77)
        time.sleep(0.3)
    driver.send_key("a", modifiers=("cmd",))
    time.sleep(0.2)
    driver.send_key("delete")
    time.sleep(0.3)
    _paste(driver, value)
    readback = _field_text(driver, dlg)

    closed = False
    buttons = [e for e, _d in walk(dlg.handle) if _role(e) == "AXButton"]
    if buttons:
        # Button 0 is OK on this dialog (OK text disappears from OCR while the
        # field editor is active, but the button stays enabled).
        AS.AXUIElementPerformAction(buttons[0], AS.kAXPressAction)
        time.sleep(1.2)
        closed = window_by_title(driver, app, "Plate Settings",
                                 timeout_s=1.0) is None
    if not closed:
        # Last resort: OCR the OK label.
        click_ok(driver, dlg)
        time.sleep(1.0)
        closed = window_by_title(driver, app, "Plate Settings",
                                 timeout_s=1.0) is None
    return readback, closed


def save_project(driver, win, rep, path: Path) -> bool:
    if not c202.open_save_as(driver, win, rep):
        return False
    return driver.save_file_dialog(win, path, default_dir=path.parent)


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
    model = work / "m8x_198_model.3mf"
    shutil.copy2(args.model, model)

    rep = Reporter(OUT)
    rep.log("=== m8x_198 macOS edit plate name ===")
    rep.log(f"datadir={args.datadir} model={model}")

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

        driver.move(win.rect.x + CUSTOMIZE_XY[0],
                    win.rect.y + CUSTOMIZE_XY[1])
        time.sleep(1.2)
        tip = " ".join(w.text for w in recognize_text(
            driver.capture_screen(),
            Rect(win.rect.x + CUSTOMIZE_XY[0] + 5,
                 win.rect.y + CUSTOMIZE_XY[1] - 45, 300, 100)))
        rep.log(f"[INFO] rail tooltip={tip!r}")
        rep.check("盘设置按钮（Customize current plate）",
                  "current plate" in tip.lower(), f"tip={tip!r}")

        # ---- A) all spaces accepted, dialog closes --------------------
        readback_a, closed_a = rename(driver, win, app, "   ")
        rep.check("全空格被接受（对话框关闭）", closed_a,
                  f"readback={readback_a!r} closed={closed_a}")
        pa = work / "m8x_198_a.3mf"
        rep.check("A 项目保存", save_project(driver, win, rep, pa)
                  and pa.exists())

        # ---- B) special characters preserved -------------------------
        readback_b, closed_b = rename(driver, win, app, "B@#1")
        pb = work / "m8x_198_b.3mf"
        rep.check("B 特殊字符输入", closed_b and readback_b == "B@#1",
                  f"readback={readback_b!r} closed={closed_b}")
        rep.check("B 项目保存", save_project(driver, win, rep, pb)
                  and pb.exists())
        names_b = mac_3mf.plate_names(pb) if pb.exists() else []
        rep.check("特殊字符盘名生效（3mf 回读一致）", "B@#1" in names_b,
                  f"names={names_b}")

        # ---- C) 100 characters accepted ------------------------------
        long_name = "X" * 100
        readback_c, closed_c = rename(driver, win, app, long_name)
        pc = work / "m8x_198_c.3mf"
        rep.check("C 100 字符输入",
                  closed_c and (readback_c or "").startswith("XXX"),
                  f"len={len(readback_c or '')} closed={closed_c}")
        rep.check("C 项目保存", save_project(driver, win, rep, pc)
                  and pc.exists())
        names_c = mac_3mf.plate_names(pc) if pc.exists() else []
        got = next((n for n in names_c if n.startswith("XXX")), "")
        rep.check("100 字符被接受（当前无限制，基线已更新）",
                  len(got) == 100, f"len={len(got)}")

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
        exit_code = rep.save({"covered": ["#198"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
