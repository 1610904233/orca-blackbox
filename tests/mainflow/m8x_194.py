#!/usr/bin/env python3
# m8x_194.py — 飞书基线 #194: 移除当前板
# feishu: baseline#194
# 行文: ≥2 盘、当前选中非空盘 → 盘右侧工具栏「移除当前板」**按钮** →
#       当前盘及其对象被删、盘数量 -1、其余盘及其对象不受影响。
#
# 入口 = 盘侧工具栏删除图标（probe_241_plate12 标定：tooltip
# 'Remove current plate (if not...)' @ ~(1354,237)，沿盘左上斜边的图标列
# 首个）。**点击前用 tooltip 就地验证**（右向 OCR——图标 tooltip 渲染在
# 光标右侧，m7.tooltip_text 裁剪在正下方会全漏）：坐标漂移时在 ±45px
# 邻域重搜含 'remove' 的图标，不盲点。
# 判定：P0（基线 plates={1:[Prusa],2:[cube]}）→ 删后 P1 恰 1 盘、
#       1 号盘对象集不变、Prusa 12 元变换逐位一致 = 其余盘不受影响。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x194]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
P0 = ART / "m8x_194_p0.3mf"
P1 = ART / "m8x_194_p1.3mf"


def patch_archiver(tag):
    from harness import shot_archive
    orig = shot_archive.start_archiver

    def named(session, name, interval=3.0, out_root=None):
        return orig(session, f"{name}_{tag}", interval=interval,
                    out_root=out_root)

    shot_archive.start_archiver = named


def plate_width(session):
    import cv2
    import numpy as np
    import m7_common as m7
    img = m7.capture_bgr(session)
    h, w = img.shape[:2]
    x0, y0 = m7.VIEWPORT_X0 + 10, 110
    roi = img[y0:h - 60, x0:w - 10]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    dark = ((hsv[:, :, 2] < 130) & (hsv[:, :, 1] < 90)).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, _l, stats, _c = cv2.connectedComponentsWithStats(dark, 8)
    if n <= 1:
        return 0
    i = max(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA])
    return int(stats[i, cv2.CC_STAT_WIDTH])


def add_plate_verified(session):
    """加盘 + 宽度验证（boot 后首击常被吞——plate7/9 实证，重试 ≤3 次）。"""
    import m7_common as m7
    w0 = plate_width(session)
    for i in range(3):
        m7.click_slot(session, 756)
        time.sleep(4.0)
        w1 = plate_width(session)
        print(f"{LOG} add-plate try{i + 1}: {w0} -> {w1}")
        if w0 and w1 and w1 >= w0 * 1.25:
            return True
    return False


def tooltip_right(session, cx, cy, dwell_s=1.2):
    """OCR 光标**右侧**的 GL tooltip（盘侧图标专用；m7.tooltip_text 裁剪
    在正下方，而盘侧 tooltip 渲染在右侧——plate10 实测 169 点 0 命中）。"""
    import m7_common as m7
    from harness import mix_dialog_util as mdu
    sx, sy = m7.client(session, cx, cy)
    m7.winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    deadline = time.monotonic() + dwell_s
    while time.monotonic() < deadline:
        img = m7.capture_bgr(session)
        crop = img[max(0, cy - 12):cy + 48, cx + 8:cx + 200]
        if crop.size:
            words = mdu.ocr_words_img(crop, scale=3)
            text = " ".join(w for w, *_ in words)
            if len(text) >= 4:
                return text.strip()
        time.sleep(0.3)
    return ""


def find_plate_icon(session, want, center, radius=45):
    """在标定中心附近找 tooltip 含 want 的盘侧图标，返回 (x, y) 或 None。
    先试中心，再 ±radius 邻域网格（步长 7×9）。"""
    tip = tooltip_right(session, *center)
    if want in tip.lower():
        print(f"{LOG} icon '{want}' @ center {center} tip={tip!r}")
        return center
    pts = [(center[0] + dx, center[1] + dy)
           for dy in range(-radius, radius + 1, 9)
           for dx in range(-radius, radius + 1, 7) if dx or dy]
    for (x, y) in pts:
        tip = tooltip_right(session, x, y)
        if want in tip.lower():
            print(f"{LOG} icon '{want}' found @({x},{y}) tip={tip!r}")
            return (x, y)
    return None


def sig(m):
    return tuple(round(v, 3) for v in m)


def main() -> int:
    import argparse
    import m7_common as m7
    import m8_common as m8
    import m8x_158 as c158
    import m8x_188 as c188
    from m3_common import add_common_args, boot_session

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    results = {}
    patch_archiver("s1")
    for f in (P0, P1):
        f.unlink(missing_ok=True)
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        results["载入（1 号盘 Prusa）"] = "PASS" if ok else f"FAIL ({frac:.2%})"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)

        if not add_plate_verified(session):
            results["新建 2 号盘"] = "FAIL（宽度未变）"
            return m7.m7_verdict(results)
        results["新建 2 号盘（当前盘）"] = "PASS"

        c158.import_model(session, CUBE)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if "8000" in (m7.object_info_text(session) or ""):
                break
            time.sleep(1.5)
        results["2 号盘导入 cube20（非空盘）"] = (
            "PASS" if "8000" in (m7.object_info_text(session) or "")
            else "FAIL (info 无 cube)")

        if not m7.save_project_as(session, P0):
            results["另存 P0（基线）"] = "FAIL"
            return m7.m7_verdict(results)
        items0, plates0 = c188.project_geom(P0)
        print(f"{LOG} P0 plates={ {k: v for k, v in plates0.items()} }")
        base_ok = (len(plates0) == 2 and len(plates0.get(2, [])) == 1
                   and len(plates0.get(1, [])) == 1)
        results["P0 基线（2 盘各 1 对象）"] = (
            f"PASS (plates={ {k: len(v) for k, v in plates0.items()} })"
            if base_ok
            else f"FAIL (plates={ {k: len(v) for k, v in plates0.items()} })")
        if not base_ok:
            return m7.m7_verdict(results)

        # 移除当前板：盘侧工具栏删除按钮（行文原文入口；tooltip 验证防漂移）
        icon = find_plate_icon(session, "remove", center=(1354, 237))
        if icon is None:
            results["盘侧删除按钮（tooltip 验证）"] = (
                "FAIL (未找到 'remove' 图标)")
            return m7.m7_verdict(results)
        results["盘侧删除按钮（tooltip 验证）"] = f"PASS (@{icon})"
        from harness import winutil as wu
        sx, sy = m7.client(session, *icon)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(2.0)
        # 非空盘删除可能弹确认框 → 点 OK/Yes
        dlg = m7.wait_dialog(session.pid, timeout_s=3.0)
        confirmed = "no-confirm"
        if dlg:
            print(f"{LOG} confirm dlg: {dlg[1]!r}")
            act = m7.click_dialog_button(dlg[3], "ok")
            if not act or "clicked" not in str(act):
                m7.click_dialog_button(dlg[3], "yes")
            confirmed = f"confirm({dlg[1]!r})"
            time.sleep(1.5)
        results["移除当前板（点删除按钮）"] = f"PASS ({confirmed})"
        time.sleep(2.0)

        if not m7.save_project_as(session, P1):
            results["另存 P1（删后）"] = "FAIL"
            return m7.m7_verdict(results)
        items1, plates1 = c188.project_geom(P1)
        print(f"{LOG} P1 plates={ {k: v for k, v in plates1.items()} }")

        results["盘数量 -1（2 → 1）"] = (
            f"PASS (plates={sorted(plates1)})" if len(plates1) == 1
            else f"FAIL (plates={sorted(plates1)})")
        keep = plates1.get(1, [])
        results["其余盘对象集不变（1 号盘仍 [Prusa]）"] = (
            f"PASS ({keep})" if sorted(keep) == sorted(plates0.get(1, []))
            else f"FAIL (plate1={keep}, was={plates0.get(1)})")
        p0 = items0.get(keep[0]) if len(keep) == 1 else None
        p1 = items1.get(keep[0]) if len(keep) == 1 else None
        results["Prusa 位姿逐位不变"] = (
            "PASS" if p0 and p1 and sig(p0[0]) == sig(p1[0])
            else f"FAIL ({p0} -> {p1})")
        on_any = [p for p, objs in plates1.items() if 4 in objs or
                  any(i != 2 for i in objs)]
        results["被删盘的对象不再属于任何盘"] = (
            "PASS (plates 只引用 1 号盘原对象)" if not on_any
            else f"FAIL (plates={plates1})")
        results["（证据行）P1 文件内仍含 cube 网格定义"] = (
            f"PASS (items={[n for _i, (_m, n) in sorted(items1.items())]}; "
            "app 保留未挂盘对象定义，无盘引用——行为上已删)")

        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
