#!/usr/bin/env python3
# diag_m8_probe2.py — round 2: fixes + the facts round 1 missed.
#
# Run A (default, no --model):
#   A1 dump ALL children (any class) in the Filaments row band
#   A2 switch the filament preset combo to 'Snapmaker PLA' (m3e row-probe
#      loop; ChangeExtruderColor only opens the OFFICIAL dialog for
#      Snapmaker-named presets — PresetComboBoxes.cpp:1067)
#   A3 click the 20x20 clr_picker button -> FilamentColorDialog dump
#      (children, screenshot, OCR), close via its Cancel button
#   A4 toolbar 'Assembly View' slot (x~1636) -> viewport diff + Fit click
#      -> zoom_to_volumes diff (assemble view #21 evidence)
# Run B (--model fixtures\snapmates_nonmixed.3mf):
#   B1 nozzle band dump on a real U1 0.4 project (diameter/flow values)
#   B2 plate strip: capture + blob per plate after switching current plate
#      (click plate 2 area), Fit click -> viewport diff

import ctypes
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import export_util, topbar_util, winutil  # noqa: E402
from harness.anchors import capture_bgr  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[probe2]"
ART = HERE / "artifacts" / "m8_probe"
ART.mkdir(parents=True, exist_ok=True)
user32 = ctypes.WinDLL("user32")


def shot(session, name):
    import cv2
    img = capture_bgr(session)
    cv2.imwrite(str(ART / f"{name}.png"), img)
    return img


def dump_band(hwnd, y0, y1, x_max=470):
    out = []
    for text, rect, ch in export_util._children_texts(hwnd):
        if y0 <= rect[1] <= y1 and rect[0] < x_max:
            out.append({"text": text.strip()[:60], "rect": list(rect),
                        "hwnd": f"0x{ch:x}"})
    return out


def find_filament_combo(session):
    for text, rect, ch in export_util._children_texts(session.hwnd):
        if rect[0] < 100 and 395 < rect[1] < 445 and rect[2] - rect[0] > 150 \
                and ("Filament" in text or "PLA" in text or "PETG" in text
                     or "ABS" in text):
            return text, rect, ch
    return None, None, None


def preset_switch(session, ch, rect, target, tries=8):
    """m3e row-probe loop for the filament preset combo."""
    txt = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(ch, txt, 256)
    if target in txt.value:
        return True
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    for attempt in range(tries):
        winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            return False
        pr = popup[2]
        shot(session, f"filament_popup_try{attempt}")
        px = (pr[0] + pr[2]) // 2
        py = pr[1] + 14 + attempt * 28
        winutil.msg_click_screen(px, py)
        time.sleep(0.8)
        user32.GetWindowTextW(ch, txt, 256)
        print(f"{LOG} after row {attempt}: {txt.value!r}")
        if target in txt.value:
            return True
    return False


def run_a(session):
    # A1: full band dump
    band = dump_band(session.hwnd, 360, 455)
    print(f"{LOG} filaments band children:")
    for k in band:
        print(f"  {k['rect']} {k['text']!r} {k['hwnd']}")

    text, rect, ch = find_filament_combo(session)
    print(f"{LOG} filament combo: {text!r} {rect}")
    if not ch:
        return
    txt = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(ch, txt, 256)
    print(f"{LOG} combo text: {txt.value!r}")

    # A2: switch to a Snapmaker preset
    ok = preset_switch(session, ch, rect, "Snapmaker")
    print(f"{LOG} preset switch to Snapmaker: {ok}")
    if not ok:
        return
    time.sleep(1.5)

    # A3: click the clr_picker (20x20 button in the row band, no text)
    picker = None
    for k in dump_band(session.hwnd, 400, 450):
        w, h = k["rect"][2] - k["rect"][0], k["rect"][3] - k["rect"][1]
        if not k["text"] and 14 <= w <= 30 and 14 <= h <= 30:
            picker = k
            break
    print(f"{LOG} clr picker: {picker}")
    if not picker:
        return
    px = (picker["rect"][0] + picker["rect"][2]) // 2
    py = (picker["rect"][1] + picker["rect"][3]) // 2
    winutil.msg_click_screen(px, py, session.hwnd)
    dlg = export_util.wait_popup(session.pid, timeout_s=5.0)
    time.sleep(1.2)
    shot(session, "color_dialog2")
    if not dlg:
        print(f"{LOG} no dialog after picker click")
        return
    print(f"{LOG} dialog rect: {dlg[2]}")
    kids = export_util._children_texts(dlg[3])
    for t, r, h_ in kids:
        if t.strip():
            print(f"  dlg[{r[0]},{r[1]},{r[2]},{r[3]}] {t.strip()[:50]!r}")
    # close via Cancel row (button whose text contains Cancel)
    cancel = [(t, r, h_) for t, r, h_ in kids if "cancel" in t.lower()]
    if cancel:
        r = cancel[0][1]
        winutil.msg_click_screen((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
        time.sleep(1.0)
        print(f"{LOG} dialog cancelled")


def run_a_assemble(session):
    # A4: Assembly View slot + Fit in assemble view
    img0 = shot(session, "asm_before")
    sx, sy = m7.client(session, 1636, m7.BAR_Y)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.4)
    winutil.msg_click_screen(sx, sy, session.hwnd)
    time.sleep(2.0)
    img1 = shot(session, "asm_after_click")
    diff = float((abs(img1.astype(int) - img0.astype(int)).sum(axis=2) > 40).mean())
    print(f"{LOG} assemble click view diff: {diff:.3%}")

    # fit inside assemble view (no selection -> zoom_to_volumes)
    h = img1.shape[0]
    sx, sy = m7.client(session, m7.VIEWPORT_X0 + 152, h - 44)
    winutil.msg_click_screen(sx, sy, session.hwnd)
    time.sleep(1.5)
    img2 = shot(session, "asm_after_fit")
    diff2 = float((abs(img2.astype(int) - img1.astype(int)).sum(axis=2) > 40).mean())
    print(f"{LOG} assemble fit diff: {diff2:.3%}")
    # back to Prepare
    score, _x, _y = m7.tab_click(session, "prepare") if hasattr(m7, "tab_click") else (0, 0, 0)
    print(f"{LOG} done assemble probe")


def run_b(session):
    ok, frac = wait_model_loaded(session, timeout_s=240)
    print(f"{LOG} model arrives: {ok} ({frac:.2%})")
    m7.ensure_maximized(session)
    band = dump_band(session.hwnd, 240, 340)
    print(f"{LOG} nozzle band on U1 0.4 project:")
    for k in band:
        print(f"  {k['rect']} {k['text']!r}")
    img = shot(session, "b_plates_before")
    # plate 2: click right of the current plate region (plates side by side)
    h, w = img.shape[:2]
    sx, sy = m7.client(session, w - 260, h - 200)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.3)
    winutil.real_click_screen(sx, sy)
    time.sleep(2.0)
    img2 = shot(session, "b_plate2_clicked")
    print(f"{LOG} plate2 click diff: "
          f"{float((abs(img2.astype(int) - img.astype(int)).sum(axis=2) > 40).mean()):.3%}")
    sx, sy = m7.client(session, m7.VIEWPORT_X0 + 152, h - 44)
    winutil.msg_click_screen(sx, sy, session.hwnd)
    time.sleep(1.5)
    img3 = shot(session, "b_after_fit")
    print(f"{LOG} plate fit diff: "
          f"{float((abs(img3.astype(int) - img2.astype(int)).sum(axis=2) > 40).mean()):.3%}")


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=None)
    args = ap.parse_args()

    session = boot_session(args, model=args.model)
    try:
        ensure_gl_ready(session)
        m7.ensure_maximized(session)
        time.sleep(1.0)
        if args.model:
            run_b(session)
        else:
            run_a(session)
            run_a_assemble(session)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
