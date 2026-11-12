#!/usr/bin/env python3
# probe_242_pa207f.py — last OS-level channels for 'abc' before falling back.
#
# d: disabling the IME context on the EDIT changed nothing (old=None).
# e: WM_CHAR and SendInput VK_PACKET also never reach the field.
# Here: 1) ImmAssociateContext on the DIALOG top-level hwnd (the IME attaches
# there, not to the child Edit); 2) WM_INPUTLANGCHANGEREQUEST sent (not
# posted) to the main frame with an en-US HKL; then real keys.
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
from harness import export_util, topbar_util, winutil

LOG = "[p242paf]"
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
    time.sleep(0.12)


def clear_edit(ed):
    r = winutil.window_rect(ed)
    real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    time.sleep(0.3)
    key(0x23)
    for _ in range(20):
        key(0x08)
    time.sleep(0.3)
    return winutil.edit_text(ed)


def type_abc():
    for ch in "abc":
        key(ord(ch.upper()))


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
        dlg = open_pa(session)
        print(f"{LOG} dialog={bool(dlg)}")
        if not dlg:
            return 1
        ed = start_edit_of(dlg)

        old = imm32.ImmAssociateContext(dlg[3], None)
        print(f"{LOG} dialog IME old={old!r}")
        print(f"{LOG} 1) clear={clear_edit(ed)!r}")
        type_abc()
        time.sleep(0.4)
        rb = winutil.edit_text(ed)
        print(f"{LOG} 1) readback after dialog-IME-off={rb!r}")

        if "abc" not in rb.lower():
            hkl = user32.LoadKeyboardLayoutW("00000409", 1)
            for target, name in ((dlg[3], "dialog"), (session.hwnd, "frame")):
                print(f"{LOG} 2) WM_INPUTLANGCHANGEREQUEST to {name} hkl={hkl!r}")
                user32.SendMessageW(target, WM_INPUTLANGCHANGEREQUEST, 0, hkl)
                time.sleep(0.8)
                print(f"{LOG} 2) clear={clear_edit(ed)!r}")
                type_abc()
                time.sleep(0.4)
                rb = winutil.edit_text(ed)
                print(f"{LOG} 2) readback after {name} layout={rb!r}")
                if "abc" in rb.lower():
                    break

        imm32.ImmAssociateContext(dlg[3], old)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
