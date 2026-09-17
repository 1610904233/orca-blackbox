#!/usr/bin/env python3
# diag_m8_probe3.py — round 3, on the MIXED fixture (embeds U1 0.8 +
# Snapmaker-named slots, so the official color dialog path is live):
#   1. sidebar dump (nozzle + filament band on a real U1 project)
#   2. filament preset combo popup: open, dump popup rect + probe rows
#      (count + names via readback), look for Generic ABS / PLA Rainbow
#   3. clr_picker click -> FilamentColorDialog: rect, children texts,
#      OCR, screenshot; close via Cancel
#   4. select model -> Fit click -> blob growth (mixed fixture baseline)

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import export_util, winutil  # noqa: E402
from harness.anchors import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[probe3]"
ART = HERE / "artifacts" / "m8_probe"
ART.mkdir(parents=True, exist_ok=True)
user32 = ctypes.WinDLL("user32")


def shot(session, name):
    import cv2
    img = capture_bgr(session)
    cv2.imwrite(str(ART / f"{name}.png"), img)
    return img


def dump_band(hwnd, y0, y1, x_max=470, label=""):
    for text, rect, ch in export_util._children_texts(hwnd):
        if y0 <= rect[1] <= y1 and rect[0] < x_max:
            print(f"  {label}[{rect[0]},{rect[1]},{rect[2]},{rect[3]}] "
                  f"{text.strip()[:50]!r}")


def find_filament_combo(session):
    hits = []
    for text, rect, ch in export_util._children_texts(session.hwnd):
        low = text.lower()
        if (("pla" in low or "petg" in low or "filament" in low)
                and rect[0] < 100 and 380 < rect[1] < 460
                and rect[2] - rect[0] > 150):
            hits.append((text, rect, ch))
    return hits[0] if hits else (None, None, None)


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=str(HERE / "fixtures" / "mixed_filament_test.3mf"))
    args = ap.parse_args()

    session = boot_session(args, model=args.model)
    try:
        ok, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} model arrives: {ok} ({frac:.2%})")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        time.sleep(1.0)

        print(f"{LOG} --- nozzle band (240-340) ---")
        dump_band(session.hwnd, 240, 340, label="nz")
        print(f"{LOG} --- filament band (330-460) ---")
        dump_band(session.hwnd, 330, 460, label="fl")

        text, rect, ch = find_filament_combo(session)
        print(f"{LOG} filament combo: {text!r} {rect}")
        if not ch:
            return 1
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(ch, buf, 256)
        cur = buf.value
        print(f"{LOG} combo text: {cur!r}")

        # --- popup rows: probe rows via readback (m3e pattern), but each
        # click CHANGES the preset — so first just open + dump + close
        cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
        winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if popup:
            pr = popup[2]
            print(f"{LOG} popup rect: {pr} (rows @28px pitch)")
            rows = export_util._children_texts(popup[3])
            txt_rows = [t for t, _r, _h in rows if t.strip()]
            print(f"{LOG} popup child texts: {txt_rows[:24]}")
            shot(session, "filament_popup_mixed")
            # count rows visually: probe OCR on the popup region
            try:
                from harness import mix_dialog_util as mdu
                img = capture_bgr(session)
                crop = img[pr[1]:pr[3], pr[0]:pr[2]]
                words = mdu.ocr_words_img(crop, scale=2)
                line = " ".join(w for w, *_ in words)
                print(f"{LOG} popup OCR: {line[:400]}")
            except Exception as exc:
                print(f"{LOG} popup OCR failed: {exc}")
            winutil.msg_key(popup[3], 0x1B)  # Esc
            time.sleep(0.6)
        else:
            print(f"{LOG} popup did not open")

        # --- picker -> official dialog -------------------------------
        picker = None
        for t, r, h_ in export_util._children_texts(session.hwnd):
            if not t and r[0] < 40 and 395 < r[1] < 450:
                w, hgt = r[2] - r[0], r[3] - r[1]
                if 14 <= w <= 34 and 14 <= hgt <= 34:
                    picker = r
                    break
        print(f"{LOG} picker rect: {picker}")
        if picker:
            px = (picker[0] + picker[2]) // 2
            py = (picker[1] + picker[3]) // 2
            winutil.msg_click_screen(px, py, session.hwnd)
            dlg = export_util.wait_popup(session.pid, timeout_s=5.0)
            time.sleep(1.2)
            shot(session, "color_dialog_mixed")
            if dlg:
                print(f"{LOG} dialog rect: {dlg[2]}")
                kids = export_util._children_texts(dlg[3])
                for t, r, h_ in kids:
                    if t.strip():
                        print(f"  dlg[{r[0]},{r[1]},{r[2]},{r[3]}] {t.strip()[:56]!r}")
                try:
                    from harness import mix_dialog_util as mdu
                    img = capture_bgr(session)
                    d = dlg[2]
                    crop = img[d[1]:d[3], d[0]:d[2]]
                    words = mdu.ocr_words_img(crop, scale=2)
                    print(f"{LOG} dialog OCR: "
                          + " ".join(w for w, *_ in words)[:500])
                except Exception as exc:
                    print(f"{LOG} dialog OCR failed: {exc}")
                cancels = [(t, r, h_) for t, r, h_ in kids
                           if "cancel" in t.lower()]
                if cancels:
                    r = cancels[0][1]
                    winutil.msg_click_screen((r[0] + r[2]) // 2,
                                             (r[1] + r[3]) // 2)
                    time.sleep(1.0)
                    print(f"{LOG} cancelled")
            else:
                print(f"{LOG} no dialog popup (see screenshot)")

        # --- select + fit on the mixed fixture -----------------------
        if m7.select_model(session):
            img0 = shot(session, "m_fit_before")
            b0 = m7 and None
            h = img0.shape[0]
            sx, sy = m7.client(session, m7.VIEWPORT_X0 + 152, h - 44)
            winutil.msg_click_screen(sx, sy, session.hwnd)
            time.sleep(1.5)
            img1 = shot(session, "m_fit_after")
            print(f"{LOG} fit view diff: "
                  f"{float((abs(img1.astype(int) - img0.astype(int)).sum(axis=2) > 40).mean()):.3%}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
