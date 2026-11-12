#!/usr/bin/env python3
# probe_242_pa207c.py — #207 follow-up: deterministic 'abc' rejection + paste.
#
# B (empty) produced a 'Snapmaker Orca info' dialog while A (abc) apparently
# did not, although both fields read empty. This probe repeats A with a
# second OK attempt and OCRs any warning dialog's body, then fixes the
# clipboard handle types and tests the paste input.
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

LOG = "[p242pac]"
user32 = winutil.user32
kernel32 = ctypes.WinDLL("kernel32")
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
user32.OpenClipboard.argtypes = [ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
PA_TITLE = "PA Calibration"


def pa_dialog(session):
    for cls, t, r, h in m7._visible_toplevels(session.pid):
        if cls == "#32770" and PA_TITLE.lower() in (t or "").lower():
            return (cls, t, r, h)
    return None


def new_dialogs(session, known):
    return [(c, t, r, h) for c, t, r, h in m7._visible_toplevels(session.pid)
            if c == "#32770" and h not in known]


def real_click(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def key(vk):
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk, 0, 2, 0)
    time.sleep(0.15)


def set_clipboard(text):
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    data = text.encode("utf-16-le") + b"\x00\x00"
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    print(f"{LOG} clipboard handle={h!r}")
    p = kernel32.GlobalLock(h)
    print(f"{LOG} clipboard lock={p!r}")
    ctypes.memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    user32.OpenClipboard(None)
    user32.EmptyClipboard()
    user32.SetClipboardData(CF_UNICODETEXT, h)
    user32.CloseClipboard()


def paste():
    user32.keybd_event(0x11, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(0x56, 0, 0, 0)
    time.sleep(0.08)
    user32.keybd_event(0x56, 0, 2, 0)
    user32.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.5)


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
            return h, r
    return None, None


def click_ok(dlg):
    h, r = ok_button(dlg)
    if not h:
        return False, None
    real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    return True, h


def close_dialog(h):
    user32.SetForegroundWindow(h)
    time.sleep(0.3)
    key(0x1B)
    time.sleep(0.6)


def clear_and_read(ed):
    r = winutil.window_rect(ed)
    real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    time.sleep(0.3)
    key(0x23)
    for _ in range(20):
        key(0x08)
    time.sleep(0.3)
    return winutil.edit_text(ed)


def run_step(session, tag, fill):
    dlg = open_pa(session)
    print(f"{LOG} === {tag} dialog={bool(dlg)}")
    if not dlg:
        return
    ed = start_edit_of(dlg)
    print(f"{LOG} {tag} edit={ed} cleared={clear_and_read(ed)!r}")
    if fill == "abc":
        for ch in "abc":
            key(ord(ch.upper()))
    elif fill == "paste":
        set_clipboard("1a\uff01@")
        paste()
    time.sleep(0.4)
    print(f"{LOG} {tag} readback={winutil.edit_text(ed)!r}")
    known = {h for _c, _t, _r, h in m7._visible_toplevels(session.pid)}
    done, okh = click_ok(dlg)
    print(f"{LOG} {tag} ok clicked={done} enabled={user32.IsWindowEnabled(okh) if okh else None}")
    time.sleep(2.5)
    warns = new_dialogs(session, known)
    print(f"{LOG} {tag} new dialogs={[(c, t, r) for c, t, r, h in warns]}")
    for cls, t, r, h in warns:
        try:
            txt = ocr_util.ocr_hwnd(h, scale=2)
        except Exception as exc:
            txt = f"<ocr failed: {exc}>"
        print(f"{LOG} {tag} warning hwnd={h} text={txt!r}")
        close_dialog(h)
    still = pa_dialog(session)
    print(f"{LOG} {tag} PA still={bool(still)} frac={m7.model_colored_frac(session):.4%}")
    if still and not warns:
        print(f"{LOG} {tag} retry OK click")
        known2 = {h for _c, _t, _r, h in m7._visible_toplevels(session.pid)}
        click_ok(still)
        time.sleep(2.5)
        warns2 = new_dialogs(session, known2)
        print(f"{LOG} {tag} retry new dialogs={[(c, t, r) for c, t, r, h in warns2]}")
        for cls, t, r, h in warns2:
            try:
                txt = ocr_util.ocr_hwnd(h, scale=2)
            except Exception as exc:
                txt = f"<ocr failed: {exc}>"
            print(f"{LOG} {tag} retry warning text={txt!r}")
            close_dialog(h)
        still = pa_dialog(session)
    if still:
        close_dialog(still[3])
    time.sleep(0.5)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        print(f"{LOG} base frac={m7.model_colored_frac(session):.4%}")
        run_step(session, "A1 abc", "abc")
        run_step(session, "A2 abc", "abc")
        run_step(session, "C paste", "paste")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
