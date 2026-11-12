#!/usr/bin/env python3
# probe_242_pa207d.py — make real 'abc' land in Start PA (Chinese IME blocks it).
#
# User review: the #207 video shows the field stays empty when typing abc —
# the guest's Chinese IME swallows the letter keys, so step A was actually a
# duplicate of the empty-field step. This probe disables the IME context on
# the target Edit (ImmAssociateContext(hwnd, NULL)) and retries the keystrokes;
# if that is not enough it also posts WM_INPUTLANGCHANGEREQUEST with an en-US
# layout. Then it clicks OK and records the warning as before.
import argparse
import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7
from m3_common import add_common_args, boot_session
from harness import export_util, ocr_util, topbar_util, winutil

LOG = "[p242pad]"
user32 = winutil.user32
imm32 = ctypes.WinDLL("imm32")
imm32.ImmAssociateContext.restype = ctypes.c_void_p
imm32.ImmAssociateContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.LoadKeyboardLayoutW.restype = ctypes.c_void_p
user32.LoadKeyboardLayoutW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
PA_TITLE = "PA Calibration"
WM_INPUTLANGCHANGEREQUEST = 0x0050


def pa_dialog(session):
    for cls, t, r, h in m7._visible_toplevels(session.pid):
        if cls == "#32770" and PA_TITLE.lower() in (t or "").lower():
            return (cls, t, r, h)
    return None


def real_click(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def key(vk):
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk, 0, 2, 0)
    time.sleep(0.15)


def type_abc():
    for ch in "abc":
        key(ord(ch.upper()))


def clear_edit(ed):
    r = winutil.window_rect(ed)
    real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    time.sleep(0.3)
    key(0x23)
    for _ in range(20):
        key(0x08)
    time.sleep(0.3)
    return winutil.edit_text(ed)


def start_edit_of(dlg):
    kids = export_util._children_texts(dlg[3])
    lab = next(((t, r) for t, r, h in kids
                if t.strip().lower().startswith("start pa")), None)
    ly = (lab[1][1] + lab[1][3]) // 2
    for t, r, h in kids:
        if winutil.window_class(h) == "Edit" and \
                abs(((r[1] + r[3]) // 2) - ly) <= 14 and \
                user32.IsWindowVisible(h):
            return h
    return None


def ok_button(dlg):
    for t, r, h in export_util._children_texts(dlg[3]):
        if t.strip().lower() == "ok" and user32.IsWindowVisible(h):
            return r
    return None


def open_pa(session):
    menu = topbar_util.open_calibration_menu(session)
    if not menu:
        return None
    rect, _mhwnd, hm = menu
    idx = topbar_util.find_item(hm, "pressure advance")
    cx = (rect[0] + rect[2]) // 2
    for y in topbar_util.submenu_row_candidates(rect, len(topbar_util.menu_items(hm)), idx):
        real_click(cx, y)
        time.sleep(1.5)
        d = pa_dialog(session)
        if d:
            return d
    return None


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        print(f"{LOG} base frac={m7.model_colored_frac(session):.4%}")
        dlg = open_pa(session)
        print(f"{LOG} dialog={bool(dlg)}")
        if not dlg:
            return 1
        ed = start_edit_of(dlg)
        print(f"{LOG} edit=0x{ed:x}")

        # 1) IME context off for this control
        old = imm32.ImmAssociateContext(ed, None)
        print(f"{LOG} old IME context={old!r}")
        print(f"{LOG} 1) clear={clear_edit(ed)!r}")
        type_abc()
        time.sleep(0.4)
        rb1 = winutil.edit_text(ed)
        print(f"{LOG} 1) readback after IME-off typing={rb1!r}")

        # 2) if still empty: switch the dialog's input language to en-US
        if "abc" not in rb1.lower():
            hkl = user32.LoadKeyboardLayoutW("00000409", 1)
            print(f"{LOG} 2) en-US HKL={hkl!r} -> WM_INPUTLANGCHANGEREQUEST")
            user32.PostMessageW(dlg[3], WM_INPUTLANGCHANGEREQUEST, 0, hkl)
            time.sleep(1.0)
            print(f"{LOG} 2) clear={clear_edit(ed)!r}")
            type_abc()
            time.sleep(0.4)
            rb1 = winutil.edit_text(ed)
            print(f"{LOG} 2) readback after layout switch={rb1!r}")

        # 3) last resort: EM_REPLACESEL (message-level) to prove the validator,
        #    clearly labeled as such in the log
        if "abc" not in rb1.lower():
            clear_edit(ed)
            user32.SendMessageW(ed, 0x00C2, 1, ctypes.c_wchar_p("abc"))  # EM_REPLACESEL
            time.sleep(0.4)
            rb1 = winutil.edit_text(ed)
            print(f"{LOG} 3) readback after EM_REPLACESEL={rb1!r}")

        # OK -> warning?
        r = ok_button(dlg)
        known = {h for _c, _t, _r, h in m7._visible_toplevels(session.pid)}
        real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
        time.sleep(2.5)
        warns = [(c, t, rr, h) for c, t, rr, h in m7._visible_toplevels(session.pid)
                 if c == "#32770" and h not in known]
        print(f"{LOG} after OK new dialogs={[(c, t, rr) for c, t, rr, h in warns]}")
        for c, t, rr, h in warns:
            try:
                print(f"{LOG} warning text={ocr_util.ocr_hwnd(h, scale=2)!r}")
            except Exception as exc:
                print(f"{LOG} OCR failed: {exc}")
        print(f"{LOG} PA still={bool(pa_dialog(session))} "
              f"frac={m7.model_colored_frac(session):.4%}")

        imm32.ImmAssociateContext(ed, old)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
