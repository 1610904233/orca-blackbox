#!/usr/bin/env python3
# probe_242_printbtn.py — 2.4.2 Print 按钮 / Export 模式切换取证
# 4 例（m3e/m4i/m8x_123 + 部分导出）都卡在 switch_to_export_mode：
# 点 Print 右侧下拉 → 期望弹出 wxWindowNR('panel') 的 Export 菜单行。
# 本探针在 2.4.2 上把 find_print_buttons 的几何/标签、点开后的所有顶层
# 窗口（类/标题/子控件文本）全部打出来，定位是哪一环变了。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import cv2
import ctypes
import ctypes.wintypes
import m7_common as m7
import m8_common as m8
from harness import export_util, winutil as wu
from m3_common import add_common_args, boot_session

LOG = "[p242p]"
user32 = ctypes.WinDLL("user32")
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                 ctypes.c_void_p)


def winutil_click_msg(x, y):
    from harness import winutil as _wu
    _wu.msg_click_screen(x, y)


def tops(session):
    out = []

    def cb(h, _lp):
        tid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(tid))
        if tid.value != session.pid or not user32.IsWindowVisible(h):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, cls, 64)
        txt = ctypes.create_unicode_buffer(128)
        user32.GetWindowTextW(h, txt, 128)
        rc = ctypes.wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(rc))
        kids = [t for t, _r, _c in export_util._children_texts(h) if t.strip()]
        out.append((cls.value, txt.value,
                    (rc.left, rc.top, rc.right, rc.bottom), kids[:8]))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(),
                         default_model=HERE / "fixtures" / "Prusa.stl")
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.3%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        opt, main = export_util.find_print_buttons(session.hwnd)
        print(f"{LOG} find_print_buttons: opt={opt} main={main}")
        if not opt:
            print(f"{LOG} no print dropdown found")
            return 1
        _click = getattr(export_util, "_click_center", None)
        if _click:
            _click(session, opt[1])
        else:
            sx, sy = opt[1]
            wu.user32.SetCursorPos(sx, sy)
            wu.real_click_screen(sx, sy)
        time.sleep(1.5)
        print(f"{LOG} after chevron click, windows:")
        for w in tops(session):
            print(f"{LOG}   {w}")
        img = m7.capture_bgr(session)
        cv2.imwrite(str(HERE / "artifacts" / "p242_print_popup.png"), img)
        print(f"{LOG} shot -> p242_print_popup.png")
        # 检查 wxWindowNR 'panel' 是否存在
        popup = export_util.wait_popup(session.pid, timeout_s=3.0)
        print(f"{LOG} wait_popup -> {popup}")
        if popup:
            rows = [r for r in export_util._children_texts(popup[3])
                    if "Export" in r[0]]
            print(f"{LOG} export rows={rows}")
            if rows:
                _t, rect, _h = rows[0]
                cx = (rect[0] + rect[2]) // 2
                cy = (rect[1] + rect[3]) // 2
                # 方式1：消息点击（现状实现）
                winutil_click_msg(cx, cy)
                time.sleep(1.2)
                _o1, m1 = export_util.find_print_buttons(session.hwnd)
                print(f"{LOG} msg-click row -> main={m1}")
                if not (m1 and "Export" in m1[0]):
                    # 方式2：真实点击
                    popup2 = export_util.wait_popup(session.pid, timeout_s=2.0)
                    rows2 = [r for r in export_util._children_texts(
                        popup2[3]) if "Export" in r[0]] if popup2 else []
                    if rows2:
                        _t, rect2, _h = rows2[0]
                        cx2 = (rect2[0] + rect2[2]) // 2
                        cy2 = (rect2[1] + rect2[3]) // 2
                        wu.user32.SetCursorPos(cx2, cy2)
                        time.sleep(0.2)
                        wu.real_click_screen(cx2, cy2)
                        time.sleep(1.5)
                        _o2, m2 = export_util.find_print_buttons(session.hwnd)
                        print(f"{LOG} real-click row -> main={m2}")
                    else:
                        print(f"{LOG} popup gone after msg click")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
