#!/usr/bin/env python3
# diag_m8_probe.py — ONE-BOOT exploration for the m8 batch (Fit view,
# official color dialog, filament preset rows, nozzle UI). No verdict:
# prints structured findings + saves artifacts/m8_probe/*.png + dumps the
# sidebar control tree so the case scripts can be written against facts.
#
# Sequence (fresh boot, empty plate):
#   1. sidebar child dump (text/rect, x<470)          -> JSON + console
#   2. add a cube (bed right-click > Add Primitive)   -> selectable model
#   3. select it, blob baseline, locate the Fit slot
#      by hover-tooltip scan (bottom-left band), click, viewport diff
#   4. filament preset combo: text read + popup row dump
#   5. color swatch click -> FilamentColorDialog dump (buttons/statics/OCR)
#   6. close dialog via its Cancel button, app close

import ctypes
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import export_util, topbar_util, winutil  # noqa: E402
from harness.anchors import capture_bgr, viewport_crop  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[probe]"
ART = HERE / "artifacts" / "m8_probe"
ART.mkdir(parents=True, exist_ok=True)
user32 = ctypes.WinDLL("user32")


def shot(session, name):
    img = capture_bgr(session)
    import cv2
    cv2.imwrite(str(ART / f"{name}.png"), img)
    return img


def blob_stats(img):
    import cv2
    import numpy as np
    h, w = img.shape[:2]
    x0, y0, x1, y1 = m7.VIEWPORT_X0 + 10, 110, w - 10, h - 60
    band = img[y0:y1, x0:x1].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _lbl, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    best, best_area = None, 0
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a > best_area:
            best, best_area = i, a
    if best is None:
        return None
    i = best
    return {
        "area": int(best_area),
        "bbox": [int(stats[i, cv2.CC_STAT_LEFT]) + x0,
                 int(stats[i, cv2.CC_STAT_TOP]) + y0,
                 int(stats[i, cv2.CC_STAT_WIDTH]),
                 int(stats[i, cv2.CC_STAT_HEIGHT])],
        "centroid": [int(cents[i][0]) + x0, int(cents[i][1]) + y0],
    }


def dump_children_txt(hwnd, x_max=470):
    """Sidebar-relevant children with non-empty text."""
    out = []
    for text, rect, ch in export_util._children_texts(hwnd):
        if text.strip() and rect[0] < x_max and rect[2] - rect[0] > 4:
            out.append({"text": text.strip()[:80], "rect": list(rect),
                        "hwnd": f"0x{ch:x}"})
    return out


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=None)
    args = ap.parse_args()

    session = boot_session(args, model=None)
    try:
        ensure_gl_ready(session)
        m7.ensure_maximized(session)
        time.sleep(1.0)

        # --- 1. sidebar dump -------------------------------------------------
        kids = dump_children_txt(session.hwnd)
        (ART / "sidebar_children.json").write_text(
            json.dumps(kids, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{LOG} sidebar children with text: {len(kids)}")
        for k in kids:
            print(f"  {k['rect']} {k['text']!r}")

        # --- 2. add cube -----------------------------------------------------
        menu = m7.open_context_menu(session, where="bed")
        if not menu:
            print(f"{LOG} FAIL: no bed menu")
            return 1
        hwnd, hmenu = menu
        got = m7.click_menu_row(session, hwnd, hmenu, "add primitive",
                                nested=True)
        if not got:
            m7.dismiss_menus(session); return 1
        _i, (shwnd, shmenu) = got
        m7.click_menu_row(session, shwnd, shmenu, "cube")
        time.sleep(2.5)

        # --- 3. select + Fit --------------------------------------------------
        if not m7.select_model(session):
            print(f"{LOG} FAIL: cube not selectable")
            return 1
        time.sleep(1.0)
        img0 = shot(session, "fit_before")
        b0 = blob_stats(img0)
        print(f"{LOG} blob before fit: {b0}")

        # hover-scan the bottom-left band for the Fit tooltip
        img = capture_bgr(session)
        h, w = img.shape[:2]
        fit_xy = None
        y_band = h - 55
        for x in range(m7.VIEWPORT_X0 + 110, m7.VIEWPORT_X0 + 260, 10):
            tip = m7.tooltip_text(session, x, y_band, dwell_s=0.9)
            if tip:
                print(f"{LOG} hover @{x},{y_band}: {tip!r}")
            if tip and "fit" in tip.lower():
                fit_xy = (x, y_band)
                break
        print(f"{LOG} fit slot: {fit_xy}")
        if fit_xy:
            sx, sy = m7.client(session, *fit_xy)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            winutil.msg_click_screen(sx, sy, session.hwnd)
            time.sleep(1.5)
            img1 = shot(session, "fit_after")
            b1 = blob_stats(img1)
            print(f"{LOG} blob after fit: {b1}")
        else:
            # fall back: click the visually known spot (canvas-local ratio)
            sx, sy = m7.client(session, int(m7.VIEWPORT_X0 + 152), int(h - 44))
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            winutil.msg_click_screen(sx, sy, session.hwnd)
            time.sleep(1.5)
            img1 = shot(session, "fit_after_fallback")
            b1 = blob_stats(img1)
            print(f"{LOG} blob after fallback fit: {b1}")

        # --- 4. filament combo + popup rows ----------------------------------
        combo = None
        for text, rect, ch in export_util._children_texts(session.hwnd):
            low = text.lower()
            if (("pla" in low or "petg" in low or "abs" in low or "filament" in low)
                    and rect[0] < 470 and 90 < rect[1] < 480
                    and rect[2] - rect[0] > 120):
                combo = (text, rect, ch)
                break
        print(f"{LOG} filament combo: {combo and (combo[0], combo[1])}")
        if combo:
            txt = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(combo[2], txt, 256)
            print(f"{LOG} combo text: {txt.value!r}")
            cx = (combo[1][0] + combo[1][2]) // 2
            cy = (combo[1][1] + combo[1][3]) // 2
            winutil.msg_click_screen(cx, cy, session.hwnd)
            popup = export_util.wait_popup(session.pid, timeout_s=4.0)
            if popup:
                pr = popup[2]
                print(f"{LOG} filament popup rect: {pr}")
                rows = export_util._children_texts(popup[3])
                print(f"{LOG} popup rows (hwnd texts): "
                      f"{[t for t, _r, _h in rows][:20]}")
                shot(session, "filament_popup")
                # probe first 12 row positions by OCR-free capture only
                m7.dismiss_menus(session)
            else:
                print(f"{LOG} no filament popup")

        # --- 5. color swatch -> FilamentColorDialog --------------------------
        # swatch = small square at the LEFT of the filament combo row
        if combo:
            rect = combo[1]
            sw_x = rect[0] - 34          # number chip ~28px + margin
            sw_y = (rect[1] + rect[3]) // 2
            sx, sy = m7.client(session, sw_x, sw_y)
            print(f"{LOG} swatch click @ client({sw_x},{sw_y})")
            winutil.msg_click_screen(sx, sy, session.hwnd)
            dlg = export_util.wait_popup(session.pid, timeout_s=5.0)
            time.sleep(1.0)
            shot(session, "color_dialog")
            if dlg:
                drect = dlg[2]
                print(f"{LOG} dialog rect: {drect}")
                kids_d = export_util._children_texts(dlg[3])
                for t, r, _h in kids_d:
                    if t.strip():
                        print(f"  dlg[{r}] {t.strip()[:60]!r}")
            else:
                print(f"{LOG} no dialog popup detected; see color_dialog.png")
            # try OCR for SKU/name lines
            try:
                from harness import mix_dialog_util as mdu
                img_d = capture_bgr(session)
                words = mdu.ocr_words_img(img_d, scale=2)
                texts = [wd for wd, *_ in words]
                print(f"{LOG} ocr sample: {texts[:40]}")
            except Exception as exc:
                print(f"{LOG} ocr skipped: {exc}")

        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
