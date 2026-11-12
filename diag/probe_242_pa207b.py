#!/usr/bin/env python3
# probe_242_pa207b.py — #207 behavior with REAL input channels.
#
# probe_242_pa207 showed msg_text('abc') does not land in 'Start PA' (field
# still reads '0'), and OK then generated the default PA tower. This probe
# re-tests the three Feishu inputs with real keyboard/clipboard input and
# records, per case: field readback, whether a warning dialog appears, whether
# the PA dialog stays open, and the bed color fraction (model generated?).
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

LOG = "[p242pab]"
user32 = winutil.user32
kernel32 = ctypes.WinDLL("kernel32")
PA_TITLE = "PA Calibration"


def pa_dialog(session):
    for cls, t, r, h in m7._visible_toplevels(session.pid):
        if cls == "#32770" and PA_TITLE.lower() in (t or "").lower():
            return (cls, t, r, h)
    return None


def warn_dialogs(session, known):
    out = []
    for cls, t, r, h in m7._visible_toplevels(session.pid):
        if h == session.hwnd or cls != "#32770" or h in known:
            continue
        out.append((cls, t, r, h))
    return out


def dump_children(h, label="dlg"):
    print(f"{LOG} --- {label} {winutil.window_class(h)} "
          f"{winutil.window_title(h)!r} rect={winutil.window_rect(h)}")
    for t, r, ch in export_util._children_texts(h):
        cls = winutil.window_class(ch)
        if winutil.user32.IsWindowVisible(ch) and (t.strip() or cls in ("Edit",)):
            print(f"{LOG}    {cls:12s} {t!r} rect={r}")


def real_click(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.25)
    winutil.real_click_screen(x, y, hold_ms=60)


def key(vk, shift=False):
    if shift:
        user32.keybd_event(0x10, 0, 0, 0)
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk, 0, 2, 0)
    if shift:
        user32.keybd_event(0x10, 0, 2, 0)
    time.sleep(0.12)


def clear_edit(h):
    r = winutil.window_rect(h)
    real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    time.sleep(0.3)
    key(0x23)  # END
    for _ in range(20):
        key(0x08)  # BACK
    time.sleep(0.3)
    return winutil.edit_text(h)


def type_real(text):
    for ch in text:
        key(ord(ch.upper()))


def set_clipboard(text):
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    data = text.encode("utf-16-le") + b"\x00\x00"
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    p = kernel32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    user32.OpenClipboard(None)
    user32.EmptyClipboard()
    user32.SetClipboardData(CF_UNICODETEXT, h)
    user32.CloseClipboard()


def paste():
    user32.keybd_event(0x11, 0, 0, 0)  # CTRL
    time.sleep(0.05)
    user32.keybd_event(0x56, 0, 0, 0)  # V
    time.sleep(0.08)
    user32.keybd_event(0x56, 0, 2, 0)
    time.sleep(0.05)
    user32.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.4)


def open_pa(session):
    menu = topbar_util.open_calibration_menu(session)
    if not menu:
        return None
    rect, _mhwnd, hm = menu
    idx = topbar_util.find_item(hm, "pressure advance")
    if idx is None:
        return None
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
    if not lab:
        return None
    ly = (lab[1][1] + lab[1][3]) // 2
    for t, r, h in kids:
        if winutil.window_class(h) == "Edit" and \
                abs(((r[1] + r[3]) // 2) - ly) <= 14 and \
                winutil.user32.IsWindowVisible(h):
            return h
    return None


def ok_button(dlg):
    for t, r, h in export_util._children_texts(dlg[3]):
        if t.strip().lower() == "ok" and winutil.user32.IsWindowVisible(h):
            return h, r
    return None, None


def click_ok(dlg):
    h, r = ok_button(dlg)
    if not h:
        return False
    real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    return True


def close_dialog(h):
    user32.SetForegroundWindow(h)
    time.sleep(0.3)
    key(0x1B)
    time.sleep(0.5)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        base_frac = m7.model_colored_frac(session)
        print(f"{LOG} base frac={base_frac:.4%}")

        for tag, action in (
            ("A abc", "abc"),
            ("B empty", None),
            ("C paste", "paste"),
        ):
            dlg = open_pa(session)
            print(f"{LOG} === {tag}: dialog={bool(dlg)}")
            if not dlg:
                continue
            dump_children(dlg[3], tag + " dialog")
            ed = start_edit_of(dlg)
            print(f"{LOG} {tag}: start edit={ed}")
            if not ed:
                close_dialog(dlg[3])
                continue
            before_frac = m7.model_colored_frac(session)
            cleared = clear_edit(ed)
            print(f"{LOG} {tag}: cleared readback={cleared!r}")
            if action == "abc":
                type_real("abc")
            elif action == "paste":
                set_clipboard("1a\uff01@")
                paste()
            time.sleep(0.4)
            print(f"{LOG} {tag}: readback={winutil.edit_text(ed)!r}")
            known = {dlg[3]}
            click_ok(dlg)
            time.sleep(2.0)
            warns = warn_dialogs(session, known)
            print(f"{LOG} {tag}: warning dialogs={[(c, t, r) for c, t, r, h in warns]}")
            for cls, t, r, h in warns:
                dump_children(h, tag + " warning")
                close_dialog(h)
                time.sleep(0.5)
            still = pa_dialog(session)
            after_frac = m7.model_colored_frac(session)
            print(f"{LOG} {tag}: PA dialog still={bool(still)} "
                  f"frac {before_frac:.4%} -> {after_frac:.4%}")
            if still:
                close_dialog(still[3])
            if after_frac > base_frac + 0.005:
                print(f"{LOG} {tag}: MODEL GENERATED — deleting all (Ctrl+D)")
                user32.SetForegroundWindow(session.hwnd)
                time.sleep(0.3)
                user32.keybd_event(0x11, 0, 0, 0)
                key(0x44)
                user32.keybd_event(0x11, 0, 2, 0)
                time.sleep(2.0)
                print(f"{LOG} {tag}: frac after delete-all="
                      f"{m7.model_colored_frac(session):.4%}")
            time.sleep(0.8)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
