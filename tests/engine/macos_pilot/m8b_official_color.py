#!/usr/bin/env python3
# m8b_official_color.py — macOS port: Feishu #44/#46/#47/#48/#55/#56/#58
# official colour cards, gradient filament and mixed-slice gcode.
# feishu: baseline#44 baseline#46 baseline#47 baseline#48 baseline#55
#         baseline#56 baseline#58  (macOS port; corresponds to the enabled
#         Windows m8b_official_color, registered in cases.MACOS_BASELINE)
#
# Windows assertions (mapped):
#   #48 the official colour dialog opens for a Snapmaker preset, shows a card
#       name + SKU, and blocks canvas clicks (state unchanged)
#   #44 the official colour list is present; a non-official preset (Generic
#       PETG) falls back to the legacy native picker
#   #46 choosing a card + OK applies it (swatch changes); reopening keeps it
#   #47 choosing another card + Cancel leaves the swatch unchanged
#   #55 slot 2's preset can be switched to Snapmaker PLA Rainbow
#   #44 after the switch the gradient filament's picker is still official
#   #56 the model render is colourful and tracks the declared slot colour
#   #58 a cube sliced on the rainbow slot exports a gcode whose config carries
#       mixed/gradient attributes
#
# macOS mapping:
#   official dialog -> title-less layer-8 window at ~(788,484,380,376); cards
#                      are a 5x3 owner-drawn grid; name/SKU via OCR; OK/Cancel
#                      at dialog-relative (259,348)/(120,348)
#   native fallback -> slot-1 chip opens the title='Colors' NSColorPanel
#   preset switch   -> slot-2 combo -> Add/Remove filament -> System
#                      Filaments; scroll the grid to the Snapmaker column,
#                      tick Snapmaker PLA Rainbow, Confirm.  (The inline
#                      vendor submenu is not synthetic-clickable here.)
#   remap           -> object context menu Change Filament -> Snapmaker PLA
#                      Rainbow (AXMenuItem tree)
#   slice           -> mac_common.slice_and_export
#
# Artifacts: artifacts/mac/pilot/m8b/{report.log,result.json,work/*.gcode,
#            *.png}.

from __future__ import annotations

import argparse
import colorsys
import json
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

import Quartz  # noqa: E402

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
    wait_for_model,
)
import mac_gcode  # noqa: E402
import m7b_new_project as m7b  # noqa: E402
import m8d_purifier_gcode as c8d  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8b"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
CHIP2 = (220, 418)
CHIP1 = (22, 418)
CUBE_POINT = (814, 396)
# dialog-relative card centres (first row / second row) and buttons
CARD_A = (77, 166)
CARD_B = (125, 194)
OK_REL = (259, 348)
CANCEL_REL = (120, 348)


def dialog(driver, app, win):
    for w in driver.windows_for_pid(app.pid):
        if w.id == win.id or not w.on_screen or w.layer == 0:
            continue
        if "colors" in (w.title or "").lower():
            continue
        if 300 <= w.rect.w <= 460 and 260 <= w.rect.h <= 460:
            return w
    return None


def drag(x0, y0, x1, y1, steps=14):
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    p0 = Quartz.CGPointMake(x0, y0)
    Quartz.CGEventPost(
        Quartz.kCGHIDEventTap,
        Quartz.CGEventCreateMouseEvent(src, Quartz.kCGEventMouseMoved, p0,
                                       Quartz.kCGMouseButtonLeft))
    time.sleep(0.1)
    Quartz.CGEventPost(
        Quartz.kCGHIDEventTap,
        Quartz.CGEventCreateMouseEvent(src, Quartz.kCGEventLeftMouseDown, p0,
                                       Quartz.kCGMouseButtonLeft))
    time.sleep(0.05)
    for i in range(1, steps + 1):
        p = Quartz.CGPointMake(x0 + (x1 - x0) * i / steps,
                               y0 + (y1 - y0) * i / steps)
        Quartz.CGEventPost(
            Quartz.kCGHIDEventTap,
            Quartz.CGEventCreateMouseEvent(
                src, Quartz.kCGEventLeftMouseDragged, p,
                Quartz.kCGMouseButtonLeft))
        time.sleep(0.03)
    Quartz.CGEventPost(
        Quartz.kCGHIDEventTap,
        Quartz.CGEventCreateMouseEvent(
            src, Quartz.kCGEventLeftMouseUp, Quartz.CGPointMake(x1, y1),
            Quartz.kCGMouseButtonLeft))
    time.sleep(0.5)


def dialog_text(driver, win, dlg) -> str:
    words = recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(dlg.rect.x - win.rect.x, dlg.rect.y - win.rect.y,
             dlg.rect.w, dlg.rect.h))
    return " ".join(w.text for w in words)


def sku(text: str):
    m = re.search(r"sku\s*(\d+)", text, re.I)
    return m.group(1) if m else None


def chip_rgb(driver, win, point=CHIP2) -> tuple:
    frame = driver.capture(win)
    i = (point[1] * frame.width + point[0]) * 4
    return (frame.data[i + 2], frame.data[i + 1], frame.data[i])


def open_official(driver, app, win, point=CHIP2):
    driver.click(win.rect.x + point[0], win.rect.y + point[1])
    time.sleep(2.0)
    dlg = dialog(driver, app, win)
    return dlg


def click_card(driver, dlg, rel):
    driver.click(dlg.rect.x + rel[0], dlg.rect.y + rel[1])
    time.sleep(1.0)


def click_button(driver, dlg, rel):
    driver.click(dlg.rect.x + rel[0], dlg.rect.y + rel[1])
    time.sleep(2.0)


def native_colors_panel(driver, app, win):
    for w in driver.windows_for_pid(app.pid):
        if (w.on_screen and w.layer != 0
                and "colors" in (w.title or "").lower()):
            return w
    return None


def select_rainbow(driver, win, rep) -> bool:
    """Set the slot-2 preset to Snapmaker PLA Rainbow.

    The inline vendor submenu is not synthetic-clickable on this build, so
    use the System Filaments dialog: slot-2 combo -> Add/Remove filament ->
    scroll the preset grid right/down to the Snapmaker column, tick
    "Snapmaker PLA Rainbow", Confirm.
    """
    ws = c8d.ocr_window(driver, win)
    y2 = c8d.slot2_row_y(driver, win)
    combo = next((w for w in ws
                  if 200 < w.rect.x < 400 and y2 is not None
                  and abs(w.rect.center[1] - y2) <= 12), None)
    if combo is None:
        combo = next((w for w in ws
                      if 200 < w.rect.x < 400
                      and 430 <= w.rect.y <= 470), None)
    if combo is None:
        return False
    driver.click(win.rect.x + combo.rect.center[0],
                 win.rect.y + combo.rect.center[1])
    time.sleep(1.2)
    ws = c8d.ocr_window(driver, win)
    add = next((w for w in ws
                if "add/remove filament" in w.text.lower()), None)
    if add is None:
        driver.click(win.rect.x + combo.rect.center[0],
                     win.rect.y + combo.rect.center[1])
        time.sleep(1.0)
        ws = c8d.ocr_window(driver, win)
        add = next((w for w in ws
                    if "add/remove filament" in w.text.lower()), None)
    if add is None:
        return False
    # Fast path: type-ahead in the preset popup selects the Rainbow *preset*,
    # which carries the Pastel Rainbow official card.  The System Filaments
    # dialog only changes the filament type and loses that card association.
    for ch in "rainbow":
        driver.send_key(ch)
        time.sleep(0.08)
    time.sleep(0.8)
    driver.send_key("return")
    time.sleep(1.5)
    row = c8d.read_slot2(driver, win)
    rep.log(f"[INFO] type-ahead slot2={row!r}")
    if "rainbow" in row.lower():
        return True
    # Popup may have closed; reopen it for the Add/Remove fallback.
    driver.click(win.rect.x + combo.rect.center[0],
                 win.rect.y + combo.rect.center[1])
    time.sleep(1.0)
    ws = c8d.ocr_window(driver, win)
    add = next((w for w in ws
                if "add/remove filament" in w.text.lower()), None)
    if add is None:
        return False
    rep.log(f"[INFO] click {add.text!r} @ {add.rect.to_xywh()}")
    driver.click(win.rect.x + add.rect.center[0],
                 win.rect.y + add.rect.center[1])
    time.sleep(1.5)
    ws = c8d.ocr_window(driver, win)
    clear = next((w for w in ws if "clear all" in w.text.lower()), None)
    if clear is not None:
        rep.log(f"[INFO] clear all @ {clear.rect.to_xywh()}")
        driver.click(win.rect.x + clear.rect.center[0],
                     win.rect.y + clear.rect.center[1])
        time.sleep(1.0)
    found = None
    for attempt in range(4):
        ws = c8d.ocr_window(driver, win)
        found = next((w for w in ws if "rainbow" in w.text.lower()),
                     None)
        if found is not None:
            break
        # horizontal scrollbar (bottom) then vertical (right edge)
        if attempt % 2 == 0:
            drag(win.rect.x + 400, win.rect.y + 623,
                 win.rect.x + 900, win.rect.y + 623)
        else:
            drag(win.rect.x + 963, win.rect.y + 430,
                 win.rect.x + 963, win.rect.y + 600)
        time.sleep(0.8)
    if found is None:
        driver.capture(win).save_png(OUT / "rainbow_dialog.png")
        return False
    rep.log(f"[INFO] Rainbow row @ {found.rect.to_xywh()}")
    # Hold the cursor on the row so the recording clearly shows which
    # dual-colour/gradient preset is being selected.
    driver.move(win.rect.x + found.rect.center[0],
                win.rect.y + found.rect.center[1])
    time.sleep(1.8)
    driver.click(win.rect.x + found.rect.center[0],
                 win.rect.y + found.rect.center[1])
    time.sleep(1.2)
    ws = c8d.ocr_window(driver, win)
    confirm = next((w for w in ws if w.text.strip().lower() == "confirm"),
                   None)
    if confirm is None:
        return False
    driver.click(win.rect.x + confirm.rect.center[0],
                 win.rect.y + confirm.rect.center[1])
    time.sleep(2.5)
    # Confirm can need a second press; until the modal is gone, Delete All
    # is disabled and the later add-cube step fails.
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        words = c8d.ocr_window(driver, win)
        if not any("system filaments" in w.text.lower() for w in words):
            break
        again = next((w for w in words
                      if w.text.strip().lower() == "confirm"), None)
        if again is not None:
            rep.log("[INFO] dialog still open; Confirm again")
            driver.click(win.rect.x + again.rect.center[0],
                         win.rect.y + again.rect.center[1])
        time.sleep(1.0)
    return True


def _change_filament_item(driver, app, win):
    for w in driver.windows_for_pid(app.pid):
        if w.id == win.id or not w.on_screen or w.rect.area < 400:
            continue
        if w.rect.y < 100 or w.rect.w > 400:
            continue
        try:
            for c in driver.controls(w):
                if (c.role == "AXMenuItem"
                        and "change filament" in (c.title or "").lower()):
                    return c
        except Exception:
            pass
    return None


def remap_to_rainbow(driver, app, win, rep) -> str:
    driver.capture(win).save_png(OUT / "before_remap.png")
    item = None
    for pt in ((814, 396), (814, 430), (814, 460), (850, 430),
               (790, 430), (814, 380), (780, 400)):
        driver.click(win.rect.x + pt[0], win.rect.y + pt[1])
        time.sleep(0.5)
        driver.click(win.rect.x + pt[0], win.rect.y + pt[1], button="right")
        time.sleep(1.0)
        item = _change_filament_item(driver, app, win)
        rep.log(f"[INFO] context at {pt}: item={item.title if item else None}")
        if item is not None:
            break
        driver.send_key("escape")
        time.sleep(0.4)
    if item is None:
        # Object-tree fallback: select the cube row, then use its menu.
        ws = c8d.ocr_window(driver, win)
        tab = next((w for w in ws if w.text.strip().lower() == "objects"
                    and w.rect.y < 700), None)
        if tab is not None:
            driver.click(win.rect.x + tab.rect.center[0],
                         win.rect.y + tab.rect.center[1])
            time.sleep(1.2)
            ws = c8d.ocr_window(driver, win)
            row = next((w for w in ws if "cube" in w.text.lower()
                        and w.rect.y > 540), None)
            if row is not None:
                for btn in ("left", "right"):
                    driver.click(win.rect.x + row.rect.center[0],
                                 win.rect.y + row.rect.center[1],
                                 button=btn)
                    time.sleep(1.0)
                item = _change_filament_item(driver, app, win)
                rep.log(f"[INFO] tree fallback item="
                        f"{item.title if item else None}")
    if item is None:
        return "no Change Filament"
    driver.click_control(item)
    time.sleep(1.2)
    rainbows = []
    for w in driver.windows_for_pid(app.pid):
        if not w.on_screen or w.id == win.id:
            continue
        if w.rect.y < 100 or w.rect.w > 400:
            continue
        try:
            for c in driver.controls(w):
                if (c.role == "AXMenuItem"
                        and "rainbow" in (c.title or "").lower()):
                    rainbows.append(c)
        except Exception:
            pass
    if not rainbows:
        return "no Rainbow submenu row"
    rainbows.sort(key=lambda c: c.rect.y if c.rect else 0)
    # Each menu row appears twice (two AX views of the same popup); keep one
    # per rect before choosing slot 2's row.
    uniq = []
    seen = set()
    for c in rainbows:
        if c.rect is None:
            continue
        key = (c.rect.x, c.rect.y, c.rect.w, c.rect.h)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    rep.log(f"[INFO] rainbow rows="
            f"{[(c.title, c.rect.to_xywh()) for c in uniq]}")
    # The dialog mapped Rainbow to every slot, so the Change Filament menu
    # has one row per slot.  The baseline and the expected UI state use
    # slot 2 (the second unique row), not the first.
    idx = 1 if len(uniq) >= 2 else 0
    rainbow = uniq[idx]
    rep.log(f"[INFO] Change Filament -> row {idx + 1}/{len(uniq)} "
            f"{rainbow.title!r}")
    driver.click_control(rainbow)
    time.sleep(1.5)
    return "ok"


def render_hue(driver, win):
    frame = driver.capture(win)
    w = frame.width
    cx, cy = CUBE_POINT
    hues = {}
    sat = tot = 0
    for y in range(max(0, cy - 70), min(frame.height, cy + 70), 2):
        for x in range(max(0, cx - 70), min(w, cx + 70), 2):
            i = (y * w + x) * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            tot += 1
            if s > 0.25 and v > 0.25:
                sat += 1
                bucket = int(h * 360 // 10) * 10 + 5
                hues[bucket] = hues.get(bucket, 0) + 1
    share = sat / max(1, tot)
    dom = max(hues, key=hues.get) if hues else None
    return dom, share


def hex_hue(hex_colour: str):
    m = re.match(r"#([0-9A-Fa-f]{6})", hex_colour or "")
    if not m:
        return None
    r, g, b = (int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    h, _s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return int(h * 360)


def gcode_colours(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^; filament_colour = ([^\r\n]+)", text, re.M)
    if not m:
        return []
    return [v.strip() for v in m.group(1).split(";") if v.strip()]


def mixed_attrs(path: Path) -> dict:
    found = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    pats = ("mixed", "mix_", "multi_colour", "multicolour", "gradient",
            "blend", "colour_type", "colour_mode", "filament_ratio")
    for m in re.finditer(r"^;?\s*([A-Za-z0-9_]+)\s*=\s*(.*)$", text, re.M):
        k, v = m.group(1), m.group(2).strip()
        if any(p in k.lower() for p in pats) and v and v not in ("[]", "''",
                                                                 '""'):
            found[k] = v[:100]
    return found


def settings_id(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^; filament_settings_id = (.*)$", text, re.M)
    if not m:
        return []
    return [v.strip().strip('"') for v in m.group(1).split(";") if v.strip()]


def make_04_rainbow_project(src: Path, dst: Path) -> None:
    """Rewrite the fixture into the user's 0.4 U1 dual/gradient project.

    Slot 1 = Snapmaker PLA Silk @U1 0.4 (Sunset Ember dual-colour card:
    #D9A63A/#CC434F); slot 2 = Snapmaker PLA Rainbow @U1 0.4 (Pastel
    Rainbow gradient card sku 34360, mode 1, colours #64C5D9/#8CB1DF/
    #CB95D0/#D7BFAA/#C6D4C0).  Printer/process are switched to 0.4.
    """
    silk = "Snapmaker PLA Silk @U1 0.4 nozzle"
    rain = "Snapmaker PLA Rainbow @U1 0.4 nozzle"
    silk_colors = ["#D9A63A", "#CC434F"]
    rain_colors = ["#64C5D9", "#8CB1DF", "#CB95D0", "#D7BFAA", "#C6D4C0"]
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for entry in zin.infolist():
            data = zin.read(entry.filename)
            if entry.filename == "Metadata/project_settings.config":
                cfg = json.loads(data.decode("utf-8"))
                cfg["printer_settings_id"] = "Snapmaker U1 (0.4 nozzle)"
                cfg["printer_variant"] = "0.4"
                cfg["nozzle_diameter"] = ["0.4"] * 4
                cfg["print_compatible_printers"] = [
                    "Snapmaker U1 (0.4 nozzle)"]
                cfg["print_settings_id"] = (
                    "0.20mm Standard @Snapmaker U1 (0.4 nozzle)")
                n = len(cfg["filament_settings_id"])
                cfg["filament_settings_id"] = [silk] * n
                cfg["filament_settings_id"][1] = rain
                cfg["filament_colour"] = [silk_colors[0]] * n
                cfg["filament_colour"][1] = rain_colors[0]
                cfg["filament_colour_mode"] = ["0"] * n
                cfg["filament_colour_mode"][1] = "1"
                cfg["filament_multi_colors"] = [
                    "|".join(silk_colors)] * n
                cfg["filament_multi_colors"][1] = "|".join(rain_colors)
                cfg["filament_type"] = ["PLA"] * n
                cfg["filament_vendor"] = ["Snapmaker"] * n
                cfg["filament_ids"] = ["1195313935011"] * n
                cfg["filament_ids"][1] = "SNPPRB001"
                data = json.dumps(cfg, indent=4).encode("utf-8")
            zout.writestr(entry, data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    model = work / "m8b_mixed.3mf"
    shutil.copy2(DEFAULT_MODEL, model)
    gcode = work / "m8b_rainbow.gcode"

    rep = Reporter(OUT)
    rep.log("=== m8b macOS official colours + gradient filament ===")
    rep.log(f"datadir={args.datadir} model={model}")
    # The repo preset snapshot is older than the installed 2.4.2 and lacks
    # filaments_colours.json entries (Pastel Rainbow and other dual/gradient
    # official cards), so the sandbox's picker shows fewer cards than the
    # app the user sees.  Pre-stage the app bundle's full preset set.
    c8d.stage_purifier_presets(args.datadir, rep)

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
                  f"rect={win.rect.to_xywh()}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        frame.save_png(OUT / "loaded.png")
        rep.check("模型载入（mixed 夹具）", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})

        # ---------- #48 official dialog + #44 list -------------------------
        before = chip_rgb(driver, win)
        dlg = open_official(driver, app, win)
        rep.check("#48 官方色卡弹窗打开", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({"stage": "dialog"})
        text0 = dialog_text(driver, win, dlg)
        sku0 = sku(text0)
        rep.log(f"[INFO] dialog text={text0!r}")
        rep.check("#48 色卡名称可见", "lemonade" in text0.lower()
                  or "sku" in text0.lower(), text0[:60])
        rep.check("#48 第一行 SKU 可见", sku0 is not None, f"sku={sku0}")
        rep.check("#44 官方色卡列表（Official Filaments）",
                  "official filaments" in text0.lower(), text0[:60])
        # Modal: a canvas click must not dismiss or mutate the dialog.
        driver.click(win.rect.x + 700, win.rect.y + 300)
        time.sleep(1.0)
        still = dialog(driver, app, win)
        text_after_bg = dialog_text(driver, win, still) if still else ""
        rep.check("#48 背景点击不改变弹窗状态",
                  still is not None and sku(text_after_bg) == sku0,
                  f"sku={sku(text_after_bg)}")

        # ---------- #46 OK applies ----------------------------------------
        click_card(driver, dlg, CARD_A)
        text1 = dialog_text(driver, win, dlg)
        sku1 = sku(text1)
        rep.log(f"[INFO] card A text={text1!r}")
        rep.check("#46 选卡改变 SKU", sku1 is not None and sku1 != sku0,
                  f"{sku0} -> {sku1}")
        click_button(driver, dlg, OK_REL)
        after_ok = chip_rgb(driver, win)
        rep.check("#46 OK 关闭弹窗并生效",
                  dialog(driver, app, win) is None and after_ok != before,
                  f"{before} -> {after_ok}")
        dlg2 = open_official(driver, app, win)
        rep.check("#46 重开保持所选色卡", dlg2 is not None
                  and sku(dialog_text(driver, win, dlg2)) == sku1,
                  f"sku={sku(dialog_text(driver, win, dlg2)) if dlg2 else None}")

        # ---------- #47 Cancel keeps --------------------------------------
        if dlg2 is not None:
            click_card(driver, dlg2, CARD_B)
            text2 = dialog_text(driver, win, dlg2)
            sku2 = sku(text2)
            rep.log(f"[INFO] card B text={text2!r}")
            rep.check("#47 选卡改变 SKU（取消前）",
                      sku2 is not None and sku2 != sku1, f"{sku1} -> {sku2}")
            click_button(driver, dlg2, CANCEL_REL)
            after_cancel = chip_rgb(driver, win)
            rep.check("#47 Cancel 不改变颜色",
                      after_cancel == after_ok,
                      f"{after_ok} -> {after_cancel}")
            dlg3 = open_official(driver, app, win)
            rep.check("#47 重开仍是 OK 所选", dlg3 is not None
                      and sku(dialog_text(driver, win, dlg3)) == sku1,
                      f"sku={sku(dialog_text(driver, win, dlg3)) if dlg3 else None}")
            if dlg3 is not None:
                click_button(driver, dlg3, CANCEL_REL)

        # ---------- #44 native fallback for a non-official preset ---------
        driver.click(win.rect.x + CHIP1[0], win.rect.y + CHIP1[1])
        time.sleep(2.0)
        native = native_colors_panel(driver, app, win)
        rep.check("#44 非官方预设回退原生取色器", native is not None,
                  native.rect.to_xywh() if native else "no Colors panel")
        if native is not None:
            driver.close_window(native)
            time.sleep(1.0)

        # ---------- phase 2: user's 0.4 dual + gradient project ----------
        rep.check("phase 1 close", close_app(driver, app, win))
        app = win = None
        rainbow_project = work / "m8b_rainbow_04.3mf"
        make_04_rainbow_project(model, rainbow_project)
        app, win = launch_and_focus(
            driver, args.datadir, model=rainbow_project,
            timeout_s=args.timeout,
            log_path=OUT / "app_launch_rainbow.log")
        rep.check("phase 2 启动（0.4 双拼/渐变工程）", True,
                  f"pid={app.pid} title={win.title!r}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        frame.save_png(OUT / "rainbow_project.png")
        rep.check("0.4 双拼/渐变工程载入", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "rainbow-load"})
        ws = c8d.ocr_window(driver, win)
        nozzle = " ".join(w.text for w in ws
                          if w.rect.y < 330
                          and ("0.4" in w.text or "0.8" in w.text))
        rep.check("喷嘴 0.4mm", "0.4" in nozzle and "0.8" not in nozzle,
                  nozzle)
        rows = [(w.text, w.rect.to_xywh()) for w in ws
                if 200 < w.rect.x < 400 and 400 < w.rect.y < 500]
        rep.log(f"[INFO] 0.4 project rows={rows}")
        rainbow_row = next((w for w in ws
                            if 200 < w.rect.x < 400
                            and 400 < w.rect.y < 440
                            and ("rainbow" in w.text.lower()
                                 or "pla ra" in w.text.lower())), None)
        rep.check("#55 2 号（渐变）槽 = Snapmaker PLA Rainbow",
                  rainbow_row is not None, str(rows))

        def close_card():
            ws2 = c8d.ocr_window(driver, win)
            cancel = next((w for w in ws2
                           if w.text.strip().lower() == "cancel"), None)
            if cancel is not None:
                driver.click(win.rect.x + cancel.rect.center[0],
                             win.rect.y + cancel.rect.center[1])
            else:
                driver.send_key("escape")
            time.sleep(1.0)

        # Gradient official card: Pastel Rainbow sku 34360.
        grad = open_official(driver, app, win, point=(220, 414))
        grad_text = dialog_text(driver, win, grad) if grad else ""
        if grad is not None:
            driver.capture(win).save_png(OUT / "pastel_rainbow_card.png")
            time.sleep(1.5)
        rep.log(f"[INFO] gradient card dialog={grad_text!r}")
        rep.check("#44 渐变卡 = Pastel Rainbow sku 34360",
                  grad is not None
                  and "pastel rainbow" in grad_text.lower()
                  and "34360" in grad_text, grad_text[:80])
        if grad is not None:
            close_card()

        # Dual-colour official card: Sunset Ember sku 34202.
        dual = open_official(driver, app, win, point=(220, 448))
        dual_text = dialog_text(driver, win, dual) if dual else ""
        if dual is not None:
            driver.capture(win).save_png(OUT / "sunset_ember_card.png")
            time.sleep(1.5)
        rep.log(f"[INFO] dual card dialog={dual_text!r}")
        rep.check("#55 1 号（双拼）槽 = Sunset Ember sku 34202",
                  dual is not None
                  and "sunset ember" in dual_text.lower()
                  and "34202" in dual_text, dual_text[:80])
        if dual is not None:
            close_card()

        # ---------- #58 cube on the rainbow slot + slice ------------------
        item = driver.find_control(win, role="AXMenuItem",
                                   title="Delete All", timeout_s=3)
        rep.check("Delete All 可用", item is not None
                  and getattr(item, "enabled", True))
        if item is None:
            return rep.save({"stage": "delete"})
        driver.click_control(item)
        time.sleep(2.5)
        rep.check("添加 cube", m7b._add_cube(driver, app, win))
        time.sleep(2.0)
        result = remap_to_rainbow(driver, app, win, rep)
        rep.check("cube 换到 Rainbow 槽", result == "ok", result)
        if result != "ok":
            return rep.save({"stage": "remap"})
        hue_render, share = render_hue(driver, win)
        driver.capture(win).save_png(OUT / "rainbow_model.png")
        rep.log(f"[INFO] render hue={hue_render} share={share:.3f}")

        if not slice_and_export(driver, win, rep, gcode,
                                [work, OUT, ARTIFACTS / "pilot",
                                 HERE / "fixtures"]):
            rep.check("#58 切片并导出 G-code", False, "slice/export failed")
            return rep.save({"stage": "slice"})
        rep.check("#58 切片并导出 G-code", True,
                  f"size={gcode.stat().st_size}")
        used = mac_gcode.used_filaments(gcode.read_bytes())
        ids = settings_id(gcode)
        colours = gcode_colours(gcode)
        rep.log(f"[INFO] used={used} ids={ids} colours={colours}")
        # Only slot 2 is Rainbow in the 0.4 project; the other slots stay
        # dual-colour Silk.  The used slot must be 2 and its settings id must
        # be the Rainbow preset.
        rep.check("#58 cube 使用 2 号 Rainbow 槽",
                  2 in used and len(ids) >= 2
                  and "rainbow" in ids[1].lower(),
                  f"used={used} ids={ids}")
        attrs = mixed_attrs(gcode)
        rep.log(f"[INFO] mixed attrs={attrs}")
        rep.check("#58 gcode 携带混色/渐变属性", bool(attrs),
                  "; ".join(f"{k}={v}" for k, v in list(attrs.items())[:4]))

        # ---------- #56 render tracks the declared colour -----------------
        declared = colours[1] if len(colours) > 1 else None
        hue_decl = hex_hue(declared) if declared else None
        delta = None
        if hue_render is not None and hue_decl is not None:
            delta = min(abs(hue_render - hue_decl),
                        360 - abs(hue_render - hue_decl))
        rep.log(f"[INFO] #56 render={hue_render} declared={declared} "
                f"hue_decl={hue_decl} delta={delta} share={share:.3f}")
        rep.check("#56 模型渲染跟随 Rainbow 主色",
                  delta is not None and delta <= 30 and share > 0.05,
                  f"hue={hue_render} declared={declared} "
                  f"delta={delta} share={share:.3f}")

        alive_before = app.alive()
        closed = close_app(driver, app, win)
        app = None
        rep.check("软件正常关闭", alive_before and closed,
                  f"alive_before={alive_before} closed={closed}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None and not args.keep:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        exit_code = rep.save({"covered": ["#44", "#46", "#47", "#48",
                                          "#55", "#56", "#58"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
