#!/usr/bin/env python3
# probe_242_tipwin.py — 2.4.2 tooltip 是否走原生 ToolTips_class32 窗口
# 悬停几个工具条槽位，枚举进程所有顶层窗口（类名 + 标题），看是否出现
# 带文本的 tooltips_class32 —— 若是，m7.tooltip_text 的 OCR 路线要换成
# GetWindowText。
import argparse
import ctypes
import ctypes.wintypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7
import m8_common as m8
from harness import winutil as wu
from m3_common import add_common_args, boot_session

LOG = "[p242w]"
user32 = ctypes.WinDLL("user32")
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                 ctypes.c_void_p)


def tops(session):
    """[(cls, title, hwnd, visible)] of the app process. 另含 tooltip 类。"""
    out = []
    pid = session.pid

    def cb(h, _lp):
        tid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(tid))
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(h, cls, 128)
        txt = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, txt, 256)
        vis = bool(user32.IsWindowVisible(h))
        if cls.value.lower().startswith("tooltips") or (
                tid.value == pid and (cls.value == "#32770"
                                      or txt.value.strip())):
            out.append((cls.value, txt.value, h, vis, tid.value == pid))
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
        sx, sy = m7.client(session, m7.VIEWPORT_X0 + 60, 700)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(1.0)

        for tag, cx, cy in (("add756", 756, 84), ("arrange844", 844, 84),
                            ("rotate1108", 1108, 84), ("scale1152", 1152, 84)):
            sx, sy = m7.client(session, cx, cy)
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(1.8)
            wins = [w for w in tops(session) if w[0].lower().startswith("tooltips")]
            print(f"{LOG} hover ({cx},{cy}) tooltip windows={wins}")
            for _i in range(3):
                time.sleep(0.6)
                wins2 = [w for w in tops(session)
                         if w[0].lower().startswith("tooltips")]
                if wins2:
                    print(f"{LOG}   t+{( _i + 1) * 0.6:.1f}s: {wins2}")
                    break
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
