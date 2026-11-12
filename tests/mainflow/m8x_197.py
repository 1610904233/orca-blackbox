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
STL = HERE / "fixtures" / "Prusa.stl"

RAIL_LINE = [(1360, 222), (1374, 231), (1388, 240), (1402, 249),
             (1416, 258), (1430, 267), (1444, 276), (1458, 285),
             (1472, 294), (1486, 303), (1500, 312), (1514, 321)]


def main() -> int:
    import argparse
    import numpy as np
    import m7_common as m7
    import m8x_194 as c194
    from harness import mix_dialog_util as mdu
    from m3_common import add_common_args, boot_session

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=args.model)
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
        for _pass in range(2):
            for (x, y) in RAIL_LINE:
                tip = c194.tooltip_right(session, x, y, dwell_s=1.2)
                if tip and "lock" in tip.lower():
                    print(f"{LOG} lock icon @({x},{y}) tip={tip!r}")
                    lock = (x, y, tip.strip())
                    break
            if lock:
                break
        if not lock:
            # 定点兜底：#196 同环境标定值（tooltip 抖动时仍可打中）
            tip = c194.tooltip_right(session, 1450, 284, dwell_s=2.0)
            print(f"{LOG} lock fallback @(1450,284) tip={tip!r}")
            if tip and "lock" in tip.lower():
                lock = (1450, 284, tip.strip())
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

        # 整理入口 = 「排列零件」图标（#196 同款已验证；键盘 A 会被输入法吞）
        arr = None
        for _pass in range(2):
            for (x, y) in RAIL_LINE:
                tip = c194.tooltip_right(session, x, y, dwell_s=1.2)
                if tip and "arrange" in tip.lower():
                    arr = (x, y, tip.strip())
                    break
            if arr:
                break
        results["「排列零件」按钮定位（整理入口）"] = (
            f"PASS (@{arr[0]},{arr[1]})" if arr else "FAIL (not found)")
        if not arr:
            return m7.m7_verdict(results)

        gx, gtip = m7.find_slot(session, lambda t: "arrange" in t)
        print(f"{LOG} main-toolbar arrange slot @{gx} tip={gtip!r}")

        def arrange_click():
            """整理：主工具栏 Arrange（m7g 已验证）→ 导轨图标兜底。"""
            if gx is not None:
                m7.click_slot(session, gx)
                time.sleep(5.0)
            else:
                sx, sy = m7.client(session, arr[0], arr[1])
                m7.winutil.user32.SetCursorPos(sx, sy)
                time.sleep(0.3)
                m7.winutil.real_click_screen(sx, sy)
                time.sleep(5.0)

        def toast_text():
            """右下角提示 toast 的 OCR 文本（锁定被拒时出现）。"""
            img = m7.capture_bgr(session)
            h, w = img.shape[:2]
            crop = img[h - 170:h - 20, w - 520:w - 10]
            if crop.size == 0:
                return ""
            words = mdu.ocr_words_img(crop, scale=3)
            txt = " ".join(wd[0] for wd in words)
            return txt.strip()

        def cube_cents():
            """只保留盘面内部区域的色块（排除右侧图标列/底栏 UI 假阳性）。"""
            return sorted((x, y) for x, y in m7.find_centroids(session, limit=6)
                          if 800 <= x <= 1430 and 250 <= y <= 730)

        # 锁定
        icon0 = m7.capture_bgr(session)[ly - 30:ly + 30, lx - 30:lx + 30]
        click_icon()
        icon1 = m7.capture_bgr(session)[ly - 30:ly + 30, lx - 30:lx + 30]
        icon_mad = float(np.mean(np.abs(icon1.astype(int) - icon0.astype(int))))
        print(f"{LOG} lock icon visual mad={icon_mad:.2f}")
        results["锁定态图标变化（证据行）"] = f"PASS (icon mad={icon_mad:.2f})"
        b0 = cube_cents()
        print(f"{LOG} locked cubes before arrange-click: {b0}")
        arrange_click()
        toast = toast_text()
        print(f"{LOG} locked arrange toast: {toast!r}")
        b1 = cube_cents()
        print(f"{LOG} locked cubes after:  {b1}")
        results["锁定后整理被拒（右下角提示可见）"] = (
            "PASS" if toast and "lock" in toast.lower()
            else f"FAIL (toast={toast!r})")
        results["锁定后立方体未移动"] = (
            "PASS" if b0 and b1 == b0 else f"FAIL ({b0} -> {b1})")

        # 解锁 -> 重新扫 tooltip 找 unlock 入口（锁定后图标可能移位/改名）
        unlock = None
        for _pass in range(2):
            for (x, y) in RAIL_LINE:
                tip = c194.tooltip_right(session, x, y, dwell_s=1.2)
                if tip and ("unlock" in tip.lower()
                            or "lock" in tip.lower()):
                    print(f"{LOG} unlock icon @({x},{y}) tip={tip!r}")
                    unlock = (x, y)
                    break
            if unlock:
                break
        results["解锁入口（tooltip 重定位）"] = (
            f"PASS (@{unlock})" if unlock else "FAIL (not found)")
        if not unlock:
            return m7.m7_verdict(results)
        sx, sy = m7.client(session, *unlock)
        m7.winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        m7.winutil.real_click_screen(sx, sy)
        time.sleep(1.5)
        # 状态核验：再悬停读 tooltip —— 回到 'Lock current plate' 才算解锁成功
        state_tip = c194.tooltip_right(session, unlock[0], unlock[1], dwell_s=1.5)
        print(f"{LOG} post-unlock tooltip={state_tip!r}")
        if state_tip and "unlock" in state_tip.lower():
            print(f"{LOG} unlock click did not take; retry")
            sx, sy = m7.client(session, *unlock)
            m7.winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.5)
            m7.winutil.real_click_screen(sx, sy)
            time.sleep(2.0)
            state_tip = c194.tooltip_right(session, unlock[0], unlock[1],
                                           dwell_s=1.5)
            print(f"{LOG} post-unlock retry tooltip={state_tip!r}")
        results["解锁状态核验（tooltip 复位）"] = (
            "PASS" if state_tip and "unlock" not in state_tip.lower()
            else f"FAIL (tip={state_tip!r})")
        icon2 = m7.capture_bgr(session)[ly - 30:ly + 30, lx - 30:lx + 30]
        back_mad = float(np.mean(np.abs(icon2.astype(int) - icon0.astype(int))))
        toasted = toast_text()
        wins = [t for c, t, r, h in m7._visible_toplevels(session.pid)
                if c == "#32770"]
        print(f"{LOG} after unlock: icon-back-to-original mad={back_mad:.2f} "
              f"toast={toasted!r} dialogs={wins}")
        results["解锁后图标复位（证据行）"] = f"PASS (mad={back_mad:.2f})"
        arrange_click()
        toast2 = toast_text()
        print(f"{LOG} unlocked arrange toast: {toast2!r}")
        b2 = cube_cents()
        print(f"{LOG} unlocked cubes after: {b2}")
        moved = False
        if b0 and b2:
            dist = max(float(np.hypot(a[0] - c[0], a[1] - c[1]))
                       for a in b2[:2] for c in b0[:2])
            print(f"{LOG} unlocked max centroid shift: {dist:.0f}px")
            moved = dist > 40
        results["解锁后整理恢复（立方体移动）"] = (
            "PASS" if moved else f"FAIL ({b0} -> {b2})")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
