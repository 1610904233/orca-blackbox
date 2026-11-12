#!/usr/bin/env python3
# ⚠️ 结论已被推翻（10-12）：见 probe_241_rainbow_enable.py 头部与 PITFALLS §21.3 ——
#    Rainbow 无需任何人工勾选，它就在 Snapmaker 二级列表里。
# probe_241_rainbow_enable2.py — 2.4.1：按截图坐标点侧栏那几个图标，找"配置可选材料"清单
#
# 第一轮没定位到入口（过滤条件漏了真正的小图标）。本轮回合按 1920x1080 截图里的坐标直接点：
#   Filament Management 行 (y≈352)：x≈337 / 361 / 385 / 408 四个小图标
#   Printer 行 (y≈157)：x≈385（铅笔/齿轮）
# 每次点击后：dump 新出现的顶层窗口/弹层 + 侧栏文字变化 + 截图；找到含 brand/mixing/材料清单的界面就深入。
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

LOG = "[pk253]"
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
    cv2.imwrite(str(ART / f"m8xPD_{name}.png"), img)
    print(f"{LOG} shot -> m8xPD_{name}.png")


def click_at(x, y, pause=1.4):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def toplevels(pid):
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


def side_texts():
    return [t.strip() for t, r, _h in export_util._children_texts(session.hwnd)
            if t.strip() and r[0] < 430 and 300 < r[1] < 1100]


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
        base_side = side_texts()
        print(f"{LOG} sidebar texts before: {base_side[:18]}")

        candidates = [
            ("filament_row_337", 337, 352), ("filament_row_361", 361, 352),
            ("filament_row_385", 385, 352), ("filament_row_408", 408, 352),
            ("printer_row_385", 385, 157),
        ]
        for tag, x, y in candidates:
            before = {t[3] for t in toplevels(session.pid)}
            click_at(x, y)
            shot(f"01_{tag}")
            now = [t for t in toplevels(session.pid) if t[3] not in before]
            side = side_texts()
            changed = [t for t in side if t not in base_side]
            print(f"{LOG} --- click {tag} @({x},{y}): new_tops="
                  f"{[(t[0], t[1], t[2]) for t in now]}")
            print(f"{LOG}     sidebar new texts: {changed[:14]}")
            for t in now:
                if t[0] in ("tooltips_class32", "SysShadow"):
                    continue
                kids = [k.strip() for k, _r, _h in export_util._children_texts(t[3]) if k.strip()]
                print(f"{LOG}     {t[0]!r} {t[1]!r} kids: {kids[:16]}")
                blob = " ".join(kids).lower()
                if any(w in blob for w in ("brand", "mixing", "rainbow", "material")):
                    print(f"{LOG}     >>> 命中（含 brand/mixing/rainbow/material）")
                    shot(f"02_{tag}_popup", t[2])
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
