#!/usr/bin/env python3
# m8x_197.py — 飞书基线 #197: 【锁定当前板】盘侧按钮 → 锁定态、对象不可整理、再点解锁
# feishu: baseline#197
# 行文: 选中目标盘 → 点击盘右侧工具栏「锁定当前板」按钮
#       预期: 盘标记锁定态(锁图标) / 盘上对象不可自动摆放、全局/单盘整理 / 再点解除
#
# 入口 = 盘侧斜排工具栏 tooltip 含 'lock' 的图标（自定位，同 #196 机制；
# 242d 实测 'Lock current plate' @~(1450,284)）。
# 判定（行为对照，最硬口径）：
#   1) 锁定后按 A（全局整理）→ 盘上零件质心集合不变（整理被拒）
#   2) 解锁后再按 A → 零件分离（整理恢复）
#   3) 锁图标视觉变化记录为证据行
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x197]"

RAIL_LINE = [(1360, 222), (1374, 231), (1388, 240), (1402, 249),
             (1416, 258), (1430, 267), (1444, 276), (1458, 285),
             (1472, 294), (1486, 303), (1500, 312), (1514, 321)]


def main() -> int:
    import argparse
    import numpy as np
    import m7_common as m7
    import m8_common as m8
    import m8x_194 as c194
    from m3_common import add_common_args, boot_session

    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=None)
    try:
        m7.ensure_maximized(session)
        time.sleep(6.0)
        # 双盘布局（盘侧斜排图标完整）
        added = c194.add_plate_verified(session)
        results["双盘布局就绪"] = "PASS" if added else "FAIL (add plate)"
        if not added:
            return m7.m7_verdict(results)
        time.sleep(2.0)
        # 当前盘（新盘）加两个重叠立方体
        c1 = m7.op_add_primitive(session, "cube")
        time.sleep(1.0)
        c2 = m7.op_add_primitive(session, "cube")
        results["两个零件已添加"] = (
            "PASS" if (c1 and c2) else f"FAIL ({c1}, {c2})")
        if not (c1 and c2):
            return m7.m7_verdict(results)
        time.sleep(2.0)
        # 自定位「锁定当前板」按钮
        lock = None
        for (x, y) in RAIL_LINE:
            tip = c194.tooltip_right(session, x, y, dwell_s=1.2)
            if tip and "lock" in tip.lower():
                print(f"{LOG} lock icon @({x},{y}) tip={tip!r}")
                lock = (x, y, tip.strip())
                break
        results["「锁定当前板」按钮定位"] = (
            f"PASS (@{lock[0]},{lock[1]})" if lock else
            "FAIL (no 'lock' tooltip on rail)")
        if not lock:
            return m7.m7_verdict(results)
        lx, ly = lock[0], lock[1]

        def click_icon():
            sx, sy = m7.client(session, lx, ly)
            m7.winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            m7.winutil.real_click_screen(sx, sy)
            time.sleep(1.5)

        def press_arrange():
            m7.winutil.force_set_foreground(session.hwnd)
            m7.winutil.user32.keybd_event(ord("A"), 0, 0, 0)
            time.sleep(0.06)
            m7.winutil.user32.keybd_event(ord("A"), 0, 2, 0)
            time.sleep(7.0)   # arranger 异步

        def cents():
            return sorted(m7.find_centroids(session, limit=4))

        # 锁定（图标区留证）
        icon0 = m7.capture_bgr(session)[ly - 30:ly + 30, lx - 30:lx + 30]
        click_icon()
        icon1 = m7.capture_bgr(session)[ly - 30:ly + 30, lx - 30:lx + 30]
        icon_mad = float(np.mean(np.abs(icon1.astype(int) - icon0.astype(int))))
        print(f"{LOG} lock icon visual mad={icon_mad:.2f}")
        results["锁定态图标变化（证据行）"] = (
            f"PASS (icon mad={icon_mad:.2f})")
        b0 = cents()
        print(f"{LOG} locked centroids before A: {b0}")
        press_arrange()
        b1 = cents()
        print(f"{LOG} locked centroids after A:  {b1}")
        locked_ok = len(b0) == len(b1) and all(
            abs(a[0] - b[0]) <= 12 and abs(a[1] - b[1]) <= 12
            for a, b in zip(b0, b1))
        results["锁定后整理被拒（质心不动）"] = (
            "PASS" if locked_ok else f"FAIL ({b0} -> {b1})")

        # 解锁
        click_icon()
        press_arrange()
        b2 = cents()
        print(f"{LOG} unlocked centroids after A: {b2}")
        moved = (len(b2) >= 2 and any(
            abs(a[0] - b[0]) > 20 or abs(a[1] - b[1]) > 20
            for a, b in zip(b1, b2)))
        if len(b2) >= 2:
            dist = float(np.hypot(b2[0][0] - b2[1][0],
                                  b2[0][1] - b2[1][1]))
            moved = moved or dist > 120
            print(f"{LOG} unlocked centroid distance: {dist:.0f}px")
        results["解锁后整理恢复（质心变化）"] = (
            "PASS" if moved else f"FAIL ({b1} -> {b2})")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
