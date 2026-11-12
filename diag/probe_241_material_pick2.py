#!/usr/bin/env python3
# ⚠️ 前提已作废（10-12）：Rainbow 不需要任何「材料勾选」就出现在耗材栏里
#    （PITFALLS §21.3）。本文件只记录「材料勾选对话框」这条路的探索过程。
# probe_241_material_pick2.py — 精确定位"耗材管理"行最右侧的 + 按钮（材料勾选入口）
#
# 上一轮 (421,346) 命中的是 Color Mixing Match（chip），不是材料勾选对话框。
# 本轮把 y 330..365、x 0..440 内的**所有**子控件（含无文本）dump 出来（文本/矩形/类/尺寸），
# 逐个点击右侧候选，报告打开了什么（找带 '系统材料/自建材料' 或材料清单的那个对话框）。
import argparse
import ctypes
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pk257]"
ART = HERE / "artifacts"
user32 = winutil.user32


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xPH_{name}.png"), img)
    print(f"{LOG} shot -> m8xPH_{name}.png")


def all_kids(parent):
    out = []

    def cb(hwnd, _lp):
        buf = ctypes.create_unicode_buffer(160)
        user32.GetWindowTextW(hwnd, buf, 160)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((buf.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumChildWindows(ctypes.c_void_p(parent), export_util.WNDENUMPROC(cb), 0)
    return out


def tops(pid):
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(160)
        user32.GetWindowTextW(hwnd, txt, 160)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def click_at(x, y, pause=1.4):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def main() -> int:
    global session
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        m8.wait_slots(session)
        cands = [(t, r, winutil.window_class(h)) for t, r, h in all_kids(session.hwnd)
                 if 300 <= r[0] <= 440 and 325 <= r[1] <= 370
                 and (r[2] - r[0]) >= 6 and (r[3] - r[1]) >= 6]
        print(f"{LOG} controls in the Filament-Management row band ({len(cands)}):")
        for t, r, c in sorted(cands, key=lambda z: (z[1][0], z[1][1])):
            print(f"{LOG}   {t.strip()[:26]!r} {r} {c} {r[2] - r[0]}x{r[3] - r[1]}")
        for i, (_t, r, c) in enumerate(sorted(cands, key=lambda z: -z[1][0])[:5]):
            x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            before = {t[3] for t in tops(session.pid)}
            print(f"{LOG} --- click cand#{i} {c} @({x},{y}) rect={r}")
            click_at(x, y)
            shot(f"01_cand{i}")
            new = [t for t in tops(session.pid) if t[3] not in before
                   and t[0] not in ("tooltips_class32", "SysShadow")]
            print(f"{LOG}     new tops: {[(t[0], t[1], t[2]) for t in new]}")
            for t in new:
                kids = [k.strip() for k, _r, _h in export_util._children_texts(t[3]) if k.strip()]
                print(f"{LOG}     {t[0]!r} {t[1]!r}: {kids[:14]}")
                blob = " ".join(kids).lower()
                if any(w in blob for w in ("material", "材料", "system", "built", "自建")):
                    print(f"{LOG}     >>> 可能就是材料勾选对话框")
                    shot(f"02_cand{i}_dialog", t[2])
            user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.8)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
