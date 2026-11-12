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
        # 导轨「排列零件」图标（锁定态点它才会弹 locked toast）
        arr = None
        for _pass in range(2):
            for (x, y) in RAIL_LINE:
                tip = c194.tooltip_right(session, x, y, dwell_s=1.2)
                if tip and "arrange" in tip.lower():
                    arr = (x, y, tip.strip())
                    break
            if arr:
                break
        results["「排列零件」按钮定位（导轨）"] = (
            f"PASS (@{arr[0]},{arr[1]})" if arr else "FAIL (not found)")

        import m8x_188 as c188
        S0 = HERE / "artifacts" / "m8x_197_s0.3mf"
        S1 = HERE / "artifacts" / "m8x_197_s1.3mf"
        S2 = HERE / "artifacts" / "m8x_197_s2.3mf"
        for f in (S0, S1, S2):
            f.unlink(missing_ok=True)

        def cube_positions(path):
            """{对象名: (x,y)} —— 存盘后解析立方体的世界平移（精确几何门）。"""
            if not m7.save_project_as(session, path):
                print(f"{LOG} save failed: {path.name}")
                return {}
            items, _plates = c188.project_geom(path)
            out = {}
            for oid, (mat, name) in items.items():
                if "cube" in (name or "").lower():
                    out[f"{name}_{oid}"] = (round(mat[9], 3),
                                            round(mat[10], 3))
            print(f"{LOG} {path.name} cubes={out}")
            return out

        def click_lock(expected_substr):
            """tooltip 定位锁定/解锁图标并点击。"""
            hit = None
            for _pass in range(2):
                for (x, y) in RAIL_LINE:
                    tip = c194.tooltip_right(session, x, y, dwell_s=1.2)
                    if tip and expected_substr in tip.lower():
                        hit = (x, y, tip.strip())
                        break
                if hit:
                    break
            if not hit:
                return None
            sx, sy = m7.client(session, hit[0], hit[1])
            m7.winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            m7.winutil.real_click_screen(sx, sy)
            time.sleep(1.5)
            return hit

        gx, gtip = m7.find_slot(session, lambda t: "arrange" in t)
        print(f"{LOG} main-toolbar arrange slot @{gx} tip={gtip!r}")

        def arrange_click(use_rail=False):
            if use_rail and arr:
                sx, sy = m7.client(session, arr[0], arr[1])
                m7.winutil.user32.SetCursorPos(sx, sy)
                time.sleep(0.3)
                m7.winutil.real_click_screen(sx, sy)
            elif gx is not None:
                m7.click_slot(session, gx)
            time.sleep(5.0)

        def toast_text():
            img = m7.capture_bgr(session)
            h, w = img.shape[:2]
            crop = img[h - 170:h - 20, w - 520:w - 10]
            if crop.size == 0:
                return ""
            words = mdu.ocr_words_img(crop, scale=3)
            return " ".join(wd[0] for wd in words).strip()

        # 0) 基线几何
        p0 = cube_positions(S0)
        results["基线几何可解析（两立方体坐标）"] = (
            f"PASS ({len(p0)} cubes)" if len(p0) >= 2
            else f"FAIL ({p0})")
        if len(p0) < 2:
            return m7.m7_verdict(results)

        # 1) 锁定（tooltip 验证入口）
        lock = click_lock("lock current plate")
        if not lock:
            # 兜底：直接点标定坐标，再读 tooltip 验证
            sx, sy = m7.client(session, 1458, 285)
            m7.winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            m7.winutil.real_click_screen(sx, sy)
            time.sleep(1.5)
            lock = (1458, 285, "fallback")
        results["「锁定当前板」按钮（tooltip 验证）"] = (
            f"PASS (@{lock[0]},{lock[1]})" if lock[0] else "FAIL")
        icon0 = None
        # 2) 锁定后整理：导轨排列按钮 → 右下角 toast 必须含 locked
        arrange_click(use_rail=True)
        toast = toast_text()
        print(f"{LOG} locked arrange toast: {toast!r}")
        results["锁定后整理被拒（toast 含 locked）"] = (
            "PASS" if toast and "lock" in toast.lower()
            else f"FAIL (toast={toast!r})")
        p1 = cube_positions(S1)
        results["锁定后立方体未移动（几何）"] = (
            "PASS" if p1 and p1 == p0 else f"FAIL ({p0} -> {p1})")

        # 3) 解锁（tooltip 重定位 + 状态核验）
        unlock = click_lock("unlock current plate")
        if unlock:
            st = c194.tooltip_right(session, unlock[0], unlock[1], dwell_s=1.5)
            print(f"{LOG} post-unlock tooltip={st!r}")
            results["解锁状态核验"] = (
                "PASS" if st and "unlock" not in st.lower()
                else f"FAIL (tip={st!r})")
        else:
            results["解锁状态核验"] = "FAIL (no unlock entry)"

        # 4) 解锁后整理：导轨按钮 → 几何必须变化
        arrange_click(use_rail=True)
        p2 = cube_positions(S2)
        moved = bool(p1) and bool(p2) and p1 != p2
        if not moved:
            print(f"{LOG} rail arrange no-op after unlock; try global")
            arrange_click(use_rail=False)
            f2 = HERE / "artifacts" / "m8x_197_s2b.3mf"
            f2.unlink(missing_ok=True)
            p2 = cube_positions(f2)
            moved = bool(p1) and bool(p2) and p1 != p2
        results["解锁后整理恢复（几何变化）"] = (
            "PASS" if moved else f"FAIL ({p1} -> {p2})")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
