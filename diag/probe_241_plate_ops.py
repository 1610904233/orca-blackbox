#!/usr/bin/env python3
# probe_241_plate_ops.py — 盘操作面摸底（#186/187/189/194/195/196/197/198 需要）
#
# 目标：
#   1) 底部盘列表 & 「+ 添加新盘」按钮的几何；
#   2) 视口右侧那列图标（盘右侧工具栏：调整朝向/排列零件/锁定/编辑名称/移除…）
#      的 tooltip 与中心坐标；
#   3) 快捷键 Q / Shift+Q / A / Shift+A 各自的效果（对象位置/数量变化）。
# 产出：artifacts/probe_241_plate_ops.log + 打印触发的取证帧。
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

LOG = "[pkPlate]"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"


def blobs(session, min_area=400):
    import cv2
    import numpy as np
    import m7_common as m7
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    h, w = img.shape[:2]
    x0, y0 = m7.VIEWPORT_X0 + 10, 110
    band = img[y0:h - 60, x0:w - 10].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _l, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        a = int(stats[i, cv2.CC_STAT_AREA])
        bw, bh = int(stats[i, 2]), int(stats[i, 3])
        if a < min_area or not (0.3 <= bw / max(bh, 1) <= 4.0):
            continue
        cx, cy = int(cents[i][0]) + x0, int(cents[i][1]) + y0
        if not (900 <= cx <= 1450 and 400 <= cy <= 800):
            continue
        out.append((cx, cy, a))
    return sorted(out)


def keys(*vks, pause=2.5):
    from harness import winutil as wu
    for vk, shift in vks:
        if shift:
            wu.user32.keybd_event(0x10, 0, 0, 0)
        wu.user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.06)
        wu.user32.keybd_event(vk, 0, 2, 0)
        if shift:
            time.sleep(0.06)
            wu.user32.keybd_event(0x10, 0, 2, 0)
        time.sleep(0.3)
    time.sleep(pause)


def main() -> int:
    import m7_common as m7
    import m8_common as m8
    import m8x_152 as base
    import m8x_158 as c158
    from m3_common import add_common_args
    from harness import winutil as wu

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = base.m7_boot(args, model=STL)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        # 再加一个模型，便于观察"排列/朝向"
        c158.import_model(session, CUBE)
        time.sleep(6.0)
        print(f"{LOG} blobs after import: {blobs(session)}")

        # 1) 底部栏 + 右侧列 的子控件 census
        kids = [(t.strip(), r) for t, r, _h in
                __import__("harness").export_util._children_texts(session.hwnd)]
        bottom = [(t, r) for t, r in kids if r[1] >= 780 and r[3] <= 1040 and t]
        right = [(t, r) for t, r in kids if r[0] >= 1440 and 250 <= r[1] <= 700]
        print(f"{LOG} bottom-bar texts: {bottom[:14]}")
        print(f"{LOG} right-column texts: {right[:14]}")
        print(f"{LOG} LABEL-LAYOUT")
        time.sleep(0.4)

        # 2) 右侧列图标：hover 读 tooltip
        x_hover = 1495
        for y in range(300, 620, 22):
            tip = m7.tooltip_text(session, x_hover, y, dwell_s=1.0)
            if tip:
                print(f"{LOG} right-icon @({x_hover},{y}): {tip!r}")
        # 3) 底栏「+」附近 hover
        for x in range(700, 780, 16):
            tip = m7.tooltip_text(session, x, 1000, dwell_s=1.0)
            if tip:
                print(f"{LOG} bottom-icon @({x},1000): {tip!r}")

        # 4) 快捷键效果
        before = blobs(session)
        print(f"{LOG} baseline blobs: {before}")
        for name, combo in (("Q", ((0x51, False),)),
                            ("Shift+Q", ((0x51, True),)),
                            ("A", ((0x41, False),)),
                            ("Shift+A", ((0x41, True),))):
            b0 = blobs(session)
            keys(*combo)
            b1 = blobs(session)
            print(f"{LOG} after {name}: {b1} (was {b0})")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
