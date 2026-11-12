#!/usr/bin/env python3
# probe_242_calibmenu.py — locate the Calibration entry in the 2.4.2 UI.
#
# Why: Feishu #206-#222 target "Orca > Calibration" (校准). The 2.4.2 topbar
# menu dump (probe_242_submenu, artifacts/p242dd.log) exposed only File + a
# dropdown holding Edit/View/Preferences/Help. This probe OCRs the top band
# for the label, clicks it when found, and dumps whatever popup opens; it
# deliberately avoids a blind full-width click sweep because that band also
# carries the page tabs (clicking them would switch pages mid-probe).
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import ctypes
import ctypes.wintypes as wt

import cv2

import m7_common as m7
from m3_common import add_common_args, boot_session
from harness import mix_dialog_util as mdu
from harness import topbar_util, winutil as wu

LOG = "[p242cm]"
user32 = ctypes.WinDLL("user32")


def dump(hmenu, indent="  "):
    for idx, label in m7.list_menu(hmenu):
        info = topbar_util.item_info(hmenu, idx)
        oid, sub = (info[0], info[1]) if info else (None, None)
        print(f"{LOG}{indent}[{idx}] {label!r} id={oid} sub={bool(sub)}")
        if sub:
            dump(sub, indent + "    ")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        print(f"{LOG} frame=0x{session.hwnd:x}")
        hm = user32.GetMenu(wt.HWND(session.hwnd))
        print(f"{LOG} GetMenu(frame)={hm}")
        if hm:
            dump(hm)
        tb = topbar_util._topbar(session.hwnd)
        print(f"{LOG} topbar={tb}")
        for text, rect, ch, cls in topbar_util._children(session.hwnd):
            if rect[1] < 200 and (rect[3] - rect[1]) <= 80:
                print(f"{LOG} child {cls!r} {text!r} rect={rect}")

        img = m7.capture_bgr(session)
        band = img[0:70, :, :]
        p = HERE / "artifacts" / "p242cm_top.png"
        cv2.imwrite(str(p), band)
        words = mdu.ocr_words_img(band, scale=3, psm=6)
        print(f"{LOG} top OCR: {[(t, x, y, w, h) for t, x, y, w, h in words]}")
        hits = [w for w in words
                if "calib" in w[0].lower() or "\u6821\u51c6" in w[0]]
        print(f"{LOG} calib hits={hits}")

        for t, x, y, w, h in hits:
            sx, sy = m7.client(session, x + w // 2, y + h // 2)
            print(f"{LOG} clicking {t!r} at client=({x + w // 2},{y + h // 2}) screen=({sx},{sy})")
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            wu.msg_click_screen(sx, sy, session.hwnd)
            time.sleep(1.2)
            menus = topbar_util._enum_menu_windows(session.pid)
            if not menus:
                print(f"{LOG} no popup after click on {t!r}")
                continue
            for m in menus:
                hm2 = topbar_util.menu_hmenu(m[4])
                print(f"{LOG} popup rect={m[:4]} rows={[l for _i, l in m7.list_menu(hm2)]}")
                dump(hm2)
            m7.dismiss_menus(session)
            time.sleep(0.5)

        menu = topbar_util.open_dropdown_menu(session)
        if menu:
            print(f"{LOG} DROPDOWN rows={[l for _i, l in m7.list_menu(menu[2])]}")
            m7.dismiss_menus(session)
        else:
            print(f"{LOG} dropdown did not open")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
