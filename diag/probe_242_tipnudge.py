#!/usr/bin/env python3
# probe_242_tipnudge.py — 2.4.2 tooltip 触发方式判别
# 假设：SetCursorPos 跳变不触发 wx/ImGui 的 hover 计时器，需要真实鼠标
# 移动事件（MOUSEEVENTF_MOVE 相对位移）。对比三种：跳变 / 相对微移 /
# 画布内先移动再移入工具条。
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

LOG = "[p242n]"
user32 = ctypes.WinDLL("user32")
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                 ctypes.c_void_p)


def visible_tooltips(session):
    out = []

    def cb(h, _lp):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, cls, 64)
        if cls.value.lower().startswith("tooltips"):
            vis = bool(user32.IsWindowVisible(h))
            if vis:
                txt = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(h, txt, 256)
                rc = ctypes.wintypes.RECT()
                user32.GetWindowRect(h, ctypes.byref(rc))
                out.append((txt.value, (rc.left, rc.top, rc.right, rc.bottom)))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def rel_move(dx, dy, steps=6):
    for _ in range(steps):
        user32.mouse_event(0x0001, dx, dy, 0, 0)
        time.sleep(0.05)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(),
                         default_model=HERE / "fixtures" / "Prusa.stl")
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        sx, sy = m7.client(session, m7.VIEWPORT_X0 + 60, 700)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(1.0)

        for tag, cx, cy in (("add756", 756, 84), ("rotate1108", 1108, 84)):
            # 方式1：跳变
            sx, sy = m7.client(session, cx, cy)
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(1.8)
            print(f"{LOG} [{tag}] jump -> tooltips={visible_tooltips(session)}")
            # 方式2：相对微移（在原地抖动 ±3px）
            rel_move(3, 0)
            time.sleep(0.4)
            rel_move(-3, 0)
            time.sleep(1.8)
            print(f"{LOG} [{tag}] nudge -> tooltips={visible_tooltips(session)}")
            # 方式3：从画布滑入
            bx, by = m7.client(session, cx, cy + 120)
            wu.user32.SetCursorPos(bx, by)
            time.sleep(0.3)
            rel_move(0, -6, steps=20)
            time.sleep(1.8)
            print(f"{LOG} [{tag}] slide-in -> tooltips={visible_tooltips(session)}")
            # OCR 兜底：光标下方/右侧
            img = m7.capture_bgr(session)
            from harness import mix_dialog_util as mdu
            for zn, (a, b, c, d) in (("below", (cx - 100, cy + 12, cx + 220, cy + 90)),
                                     ("right", (cx + 10, cy - 20, cx + 240, cy + 40))):
                crop = img[max(0, b):d, max(0, a):c]
                if crop.size:
                    t = " ".join(w for w, *_ in mdu.ocr_words_img(crop, scale=3))
                    print(f"{LOG} [{tag}] ocr {zn}={t!r}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
