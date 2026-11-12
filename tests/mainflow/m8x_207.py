#!/usr/bin/env python3
# m8x_207.py — 飞书基线 #207: 【非法输入·抽样】压力提前弹窗非法输入均被拒绝
# feishu: baseline#207
# 行文: 校准 > 压力提前 → Start PA 输入 abc / 清空 / 粘贴「1a！@」→ 每次确定
#       都弹警告框且不生成模型；对话框保持打开、app 不崩
#
# 入口 = 顶栏 Calibration（offset 250）→ Pressure advance 行（真实点击，
# 候选 y 扫描）→ 原生 #32770 'PA Calibration'。字段结构（probe_242_pa207）：
# Start PA / End PA / PA step / Accelerations / Speeds 五个 Edit + OK。
# 输入通道 = 真实键盘（probe_242_pa207b/c：WM_CHAR 消息通道被字段忽略）：
# 字母用 keybd_event，粘贴用剪贴板 + 真 Ctrl+V。
# 拒绝 oracle = 新的 #32770 'Snapmaker Orca info'，OCR 正文含
# 'Please input valid values'（实测：Start PA >= 0.0 / End PA > Start PA /
# PA step >= 0.001）；关掉后 PA 对话框仍在，热床彩色占比不上升（无模型）。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x207]"
PA_TITLE = "PA Calibration"
WARN_KEYWORDS = ("valid", "start pa")


def main() -> int:
    import argparse
    import ctypes
    import m7_common as m7
    from m3_common import add_common_args, boot_session
    from harness import export_util, ocr_util, topbar_util, winutil

    user32 = winutil.user32
    kernel32 = ctypes.WinDLL("kernel32")
    # 64-bit handles: without these argtypes GlobalAlloc's pointer is
    # truncated to 0 and memmove faults (measured in probe_242_pa207b).
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

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
        data = text.encode("utf-16-le") + b"\x00\x00"
        h = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        kernel32.GlobalUnlock(h)
        user32.OpenClipboard(None)
        user32.EmptyClipboard()
        user32.SetClipboardData(13, h)  # CF_UNICODETEXT
        user32.CloseClipboard()

    def paste():
        user32.keybd_event(0x11, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x56, 0, 0, 0)
        time.sleep(0.08)
        user32.keybd_event(0x56, 0, 2, 0)
        user32.keybd_event(0x11, 0, 2, 0)
        time.sleep(0.5)

    def dialogs():
        return [(c, t, r, h) for c, t, r, h in m7._visible_toplevels(session.pid)
                if c == "#32770"]

    def pa_dialog():
        for cls, t, r, h in dialogs():
            if PA_TITLE.lower() in (t or "").lower():
                return (cls, t, r, h)
        return None

    def open_pa():
        menu = topbar_util.open_calibration_menu(session)
        if not menu:
            return None
        rect, _mhwnd, hm = menu
        idx = topbar_util.find_item(hm, "pressure advance")
        if idx is None:
            return None
        cx = (rect[0] + rect[2]) // 2
        for y in topbar_util.submenu_row_candidates(
                rect, len(topbar_util.menu_items(hm)), idx):
            real_click(cx, y)
            time.sleep(1.5)
            d = pa_dialog()
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
            return False
        real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
        return True

    def wait_warning(known, timeout_s=4.0):
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            for d in dialogs():
                if d[3] not in known:
                    return d
            time.sleep(0.3)
        return None

    def warning_text(h):
        try:
            return ocr_util.ocr_hwnd(h, scale=2).strip()
        except Exception as exc:  # OCR must never mask the rejection itself
            print(f"{LOG} warning OCR failed: {exc}")
            return ""

    def close_warning(d):
        user32.SetForegroundWindow(d[3])
        time.sleep(0.3)
        key(0x1B)
        time.sleep(0.6)

    def clear_start(ed):
        r = winutil.window_rect(ed)
        real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
        time.sleep(0.3)
        key(0x23)  # END
        for _ in range(20):
            key(0x08)  # BACKSPACE
        time.sleep(0.3)
        return winutil.edit_text(ed)

    def submit_and_check(tag, frac_before, known):
        """Click OK (retry once: the first real click is sometimes swallowed),
        capture the warning, close it, and check the dialog/bed state."""
        click_ok(dlg)
        time.sleep(2.0)
        warn = wait_warning(known, timeout_s=3.0)
        if not warn:
            print(f"{LOG} {tag}: first OK swallowed — retrying")
            click_ok(dlg)
            time.sleep(2.0)
            warn = wait_warning(known, timeout_s=3.0)
        if not warn:
            return None, "", True, m7.model_colored_frac(session)
        txt = warning_text(warn[3])
        print(f"{LOG} {tag}: warning={warn[1]!r} text={txt!r}")
        close_warning(warn)
        still = bool(pa_dialog())
        return txt, txt, still, m7.model_colored_frac(session)

    ap = add_common_args(argparse.ArgumentParser())  # 空床
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        dlg = open_pa()
        results["PA Calibration 对话框打开"] = "PASS" if dlg else "FAIL (no dialog)"
        if not dlg:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)
        ed = start_edit_of(dlg)
        results["Start PA 字段可定位"] = "PASS" if ed else "FAIL (no edit)"
        if not ed:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        # ---- A 输入 abc ----
        frac0 = m7.model_colored_frac(session)
        cleared = clear_start(ed)
        for ch in "abc":
            key(ord(ch.upper()))
        time.sleep(0.4)
        readback_a = winutil.edit_text(ed)
        print(f"{LOG} A: cleared={cleared!r} readback={readback_a!r}")
        txt, evidence, still, frac = submit_and_check("A", frac0, {dlg[3]})
        ok_a = bool(txt) and any(k in txt.lower() for k in WARN_KEYWORDS)
        results["A 输入 abc 被拒（警告框）"] = (
            "PASS" if ok_a else
            f"FAIL (warning={evidence[:40]!r} dialog_still={still})")
        results["A 未生成模型"] = (
            "PASS" if frac <= frac0 + 0.005 else
            f"FAIL (frac {frac0:.3%} -> {frac:.3%})")
        results["A 警告后 PA 对话框仍在"] = "PASS" if still else "FAIL (closed)"
        if not still:
            dlg = open_pa()
            if not dlg:
                results["app alive"] = "PASS" if session.alive() else "FAIL"
                return m7.m7_verdict(results)
            ed = start_edit_of(dlg)

        # ---- B 清空后直接确定 ----
        frac0 = m7.model_colored_frac(session)
        cleared = clear_start(ed)
        print(f"{LOG} B: cleared={cleared!r}")
        txt, evidence, still, frac = submit_and_check("B", frac0, {dlg[3]})
        ok_b = bool(txt) and any(k in txt.lower() for k in WARN_KEYWORDS)
        results["B 清空后确定被拒（警告框）"] = (
            "PASS" if ok_b else
            f"FAIL (warning={evidence[:40]!r} dialog_still={still})")
        results["B 未生成模型"] = (
            "PASS" if frac <= frac0 + 0.005 else
            f"FAIL (frac {frac0:.3%} -> {frac:.3%})")
        if not still:
            dlg = open_pa()
            if not dlg:
                results["app alive"] = "PASS" if session.alive() else "FAIL"
                return m7.m7_verdict(results)
            ed = start_edit_of(dlg)

        # ---- C 粘贴「1a！@」 ----
        frac0 = m7.model_colored_frac(session)
        clear_start(ed)
        paste_target = "1a\uff01@"
        set_clipboard(paste_target)
        paste()
        time.sleep(0.4)
        readback_c = winutil.edit_text(ed)
        print(f"{LOG} C: readback={readback_c!r} (target {paste_target!r})")
        results["C 粘贴内容进入字段"] = (
            "PASS" if ("1a" in readback_c and "@" in readback_c) else
            f"FAIL (readback={readback_c!r})")
        txt, evidence, still, frac = submit_and_check("C", frac0, {dlg[3]})
        ok_c = bool(txt) and any(k in txt.lower() for k in WARN_KEYWORDS)
        results["C 粘贴 1a！@ 被拒（警告框）"] = (
            "PASS" if ok_c else
            f"FAIL (warning={evidence[:40]!r} dialog_still={still})")
        results["C 未生成模型"] = (
            "PASS" if frac <= frac0 + 0.005 else
            f"FAIL (frac {frac0:.3%} -> {frac:.3%})")

        if still:
            user32.SetForegroundWindow(dlg[3])
            time.sleep(0.3)
            key(0x1B)
            time.sleep(0.4)
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
