#!/usr/bin/env python3
# m8x_196.py — 飞书基线 #196: 【排列零件】盘侧工具栏按钮 → 零件全部落入盘内且互不重叠
# feishu: baseline#196
# 行文: 选中目标盘 → 点击盘右侧工具栏「排列零件」按钮 → 零件排布到盘内、互不重叠
#
# 入口 = 盘侧斜排工具栏上 tooltip 含 'arrange' 的图标（自定位：沿已标定
# 五图标所在的斜线逐点读 tooltip —— 右侧竖列实测无 tooltip，斜排线有，
# probe_242_plateicons v3 得到 remove/orient/lock/customize/move-front 五枚）。
# 判定 = 两个重叠零件 click 后质心分离 ≥120px（m7g_arrange 同口径）。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x196]"
STL = HERE / "fixtures" / "Prusa.stl"

# 盘侧斜排图标线（probe_242_plateicons 标定：remove@1360,222 /
# orient@1382,242 / lock@1450,284 / customize@1490,302 / move-front@1520,308）
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

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        results["载入模型"] = "PASS" if ok else f"FAIL ({frac:.2%})"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)
        time.sleep(2.0)
        # 双盘布局（盘侧工具栏在双盘视图下形态稳定，同 #194/#195）
        added = c194.add_plate_verified(session)
        results["双盘布局就绪"] = "PASS" if added else "FAIL (add plate)"
        if not added:
            return m7.m7_verdict(results)
        time.sleep(2.0)
        # 两个重叠零件
        c1 = m7.op_add_primitive(session, "cube")
        time.sleep(1.0)
        c2 = m7.op_add_primitive(session, "cube")
        results["两个零件已添加"] = (
            "PASS" if (c1 and c2) else f"FAIL ({c1}, {c2})")
        if not (c1 and c2):
            return m7.m7_verdict(results)
        time.sleep(2.0)
        before = m7.find_centroids(session, limit=4)
        print(f"{LOG} before arrange: {before}")
        # 自定位「排列零件」按钮：沿斜排图标线读 tooltip
        arr = None
        for (x, y) in RAIL_LINE:
            tip = c194.tooltip_right(session, x, y, dwell_s=1.2)
            if tip and "arrange" in tip.lower():
                print(f"{LOG} arrange icon @({x},{y}) tip={tip!r}")
                arr = (x, y)
                break
        results["「排列零件」按钮定位"] = (
            f"PASS (@{arr})" if arr else "FAIL (no 'arrange' tooltip on rail)")
        if not arr:
            return m7.m7_verdict(results)
        # 点击并验证分离
        sx, sy = m7.client(session, *arr)
        m7.winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        m7.winutil.real_click_screen(sx, sy)
        time.sleep(6.0)   # arranger 异步（m7g 口径）
        after = m7.find_centroids(session, limit=4)
        print(f"{LOG} after arrange: {after}")
        results["两个零件仍然存在"] = (
            "PASS" if len(after) >= 2 else f"FAIL ({len(after)})")
        if len(after) >= 2:
            dist = float(np.hypot(after[0][0] - after[1][0],
                                  after[0][1] - after[1][1]))
            print(f"{LOG} centroid distance: {dist:.0f}px")
            results["零件排布后互不重叠（质心距 ≥120px）"] = (
                f"PASS ({dist:.0f}px)" if dist > 120 else
                f"FAIL ({dist:.0f}px)")
        else:
            results["零件排布后互不重叠（质心距 ≥120px）"] = "FAIL (missing)"
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
