#!/usr/bin/env python3
# probe_242_pa207e.py — letter injection into Start PA, IME-proof.
#
# probe_242_pa207d: the Edit has no IME context (old=None), an en-US layout
# request changed nothing, and real VK_A/B/C never reach the field — the
# guest's Chinese IME consumes letter keys at the thread level. This probe
# compares three channels on the same field:
#   1) direct WM_CHAR to the Edit
#   2) SendInput KEYEVENTF_UNICODE (VK_PACKET) — layout/IME independent
#   3) EM_REPLACESEL (message-level last resort)
# then clicks OK and records the rejection warning.
import argparse
import ctypes
import ctypes.wintypes as wt
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

LOG = "[p242pae]"
user32 = winutil.user32
PA_TITLE = "PA Calibration"
WM_CHAR = 0x0102
EM_REPLACESEL = 0x00C2
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", INPUTUNION)]


def send_unicode(text):
    for ch in text:
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            inp = INPUT(type=1)
            inp.u.ki = KEYBDINPUT(0, ord(ch), flags, 0, None)
            n = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            if n != 1:
                print(f"{LOG} SendInput({ch!r},{flags}) -> {n}")
            time.sleep(0.08)


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


def ok_rect(dlg):
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
        dlg = open_pa(session)
        print(f"{LOG} dialog={bool(dlg)}")
        if not dlg:
            return 1
        ed = start_edit_of(dlg)
        print(f"{LOG} edit=0x{ed:x}")

        print(f"{LOG} 1) clear={clear_edit(ed)!r}")
        for ch in "abc":
            user32.SendMessageW(ed, WM_CHAR, ord(ch), 0)
        time.sleep(0.4)
        print(f"{LOG} 1) WM_CHAR readback={winutil.edit_text(ed)!r}")

        print(f"{LOG} 2) clear={clear_edit(ed)!r}")
        send_unicode("abc")
        time.sleep(0.5)
        print(f"{LOG} 2) VK_PACKET readback={winutil.edit_text(ed)!r}")

        print(f"{LOG} 3) clear={clear_edit(ed)!r}")
        user32.SendMessageW(ed, EM_REPLACESEL, 1, ctypes.c_wchar_p("abc"))
        time.sleep(0.4)
        print(f"{LOG} 3) EM_REPLACESEL readback={winutil.edit_text(ed)!r}")

        r = ok_rect(dlg)
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
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
