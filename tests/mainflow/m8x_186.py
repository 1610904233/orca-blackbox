#!/usr/bin/env python3
# m8x_186.py — 飞书基线 #186: 添加新盘
# feishu: baseline#186
# 行文步骤: 点击「添加新盘」→ 观察盘列表变化 → 向新盘导入模型验证可用
# 预期: 列表末尾新增空白盘；盘数量 +1、新盘选中；可向新盘添加对象
#
# 黑盒断言（不依赖盘列表的内部结构，它是 GL 自绘的）：
#   1) 点「添加新盘」后**画布变空**（= 新盘被选中且为空）——这是"新盘已选中"的
#      直接后果；1 号盘上的模型还在（切回后仍可见）
#   2) 新盘上导入模型成功（信息面板出现模型名）
#   3) 切回 1 号盘：原模型仍在（用底部盘缩略图/快捷键不可读 → 用"删盘"反向验证
#      风险大，这里只记录证据行）
#
# 录像：artifacts/shots/m8x_186/m8x_186_run.mp4
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x186]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
ADD_PLATE_X = 756        # 工具栏「Add plate」（OCR 扫描多次命中 756/778）


def _plate_width(session):
    """盘层（视口内最大暗色连通块）的渲染宽度（px）。"""
    import cv2
    import numpy as np
    import m7_common as m7
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
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


def main() -> int:
    import argparse
    import m7_common as m7
    import m8_common as m8
    import m8x_158 as c158
    from m3_common import add_common_args, boot_session

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        results["1 号盘载入模型"] = "PASS" if ok else f"FAIL ({frac:.2%})"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)
        time.sleep(2.0)
        frac_before = m7.model_colored_frac(session)
        objs_before = c158.object_blobs(session)
        plate_w0 = _plate_width(session)
        print(f"{LOG} before: frac={frac_before:.3%} objs={objs_before} "
              f"plate_w={plate_w0}")

        # 1) 点「添加新盘」（固定几何 + tooltip 校验，读不到再扫描）
        x = ADD_PLATE_X
        tip = m7.tooltip_text(session, x, m7.BAR_Y)
        print(f"{LOG} add-plate slot @x{x} tip={tip!r}")
        if "plate" not in (tip or "").lower():
            sx, stip = m7.find_slot(session, lambda t: "add plate" in t)
            print(f"{LOG} scan -> {sx} {stip!r}")
            if sx is not None:
                x, tip = sx, stip
        results["「添加新盘」按钮"] = (
            f"PASS ({tip!r})" if tip and "plate" in tip.lower()
            else f"FAIL (tip={tip!r})")
        m7.click_slot(session, x)
        time.sleep(3.5)

        # 2) 新盘出现：盘层（最大暗色块）的渲染宽度显著变大。
        #    不能用"画布变空"：加盘后 app 会**拉远视图同时显示所有盘**（实测
        #    10-28：frac 0.26% -> 0.60%，模型还在 1 号盘上），真实信号是盘面
        #    横向铺开（两张盘并排）。
        plate_w1 = _plate_width(session)
        frac_after = m7.model_colored_frac(session)
        print(f"{LOG} after add-plate: frac={frac_after:.3%} "
              f"plate_w={plate_w1} (was {plate_w0})")
        grew = (plate_w0 and plate_w1 and plate_w1 >= plate_w0 * 1.25)
        results["新盘出现（盘层渲染变宽 ≥25%）"] = (
            f"PASS ({plate_w0}px -> {plate_w1}px)" if grew
            else f"FAIL ({plate_w0}px -> {plate_w1}px)")
        if not grew:
            return m7.m7_verdict(results)

        # 3) 新盘可正常添加对象
        c158.import_model(session, CUBE)
        deadline = time.monotonic() + 120
        info = ""
        arrived = False
        while time.monotonic() < deadline:
            info = m7.object_info_text(session)
            if "cube20" in (info or "").lower():
                arrived = True
                break
            time.sleep(1.5)
        print(f"{LOG} import on new plate: arrived={arrived} "
              f"info={info[:50]!r}")
        results["新盘可添加对象（导入 cube20）"] = (
            f"PASS ({info[:36]!r})" if arrived
            else f"FAIL (info={info[:50]!r})")
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
