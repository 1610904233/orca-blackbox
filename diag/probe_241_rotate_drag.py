#!/usr/bin/env python3
# probe_241_rotate_drag.py — 标定 Rotate 圆环/箭头的可拖拽点（一次性）
#
# 背景（10-19，测试方口径）：模型快速调整里"旋转 = 点住对应箭头拖动"。实测
# 难点有两个：
#   1) 激活 Rotate 后对象屏幕位置会变（不能沿用激活前的质心）；
#   2) 拖到床面 = **相机/热床整体环绕**，投影角度变化会伪装成旋转成功。
# 本探针在对象周围打网格点，每个点做一次小位移拖拽，同时记录：
#   dobj   = 对象 bbox 的相对变化（%）
#   dplate = 热床投影 bbox 的相对变化（%）
# 目标 = 找到 dobj 大、dplate 小的点 → 那就是"拖箭头旋转"的可点位置。
#
# 产出：artifacts/probe_241_rotate_drag.log + 取证帧（打印触发的 L 帧）
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkRot]"
STL = HERE / "fixtures" / "Prusa.stl"


def shape(session):
    import cv2
    import numpy as np
    import m7_common as m7
    import m8_common as m8
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    st = m8.blob_stats(img)
    obj = tuple(st["bbox"]) if st else None
    h, w = img.shape[:2]
    x0, y0 = m7.VIEWPORT_X0 + 10, 110
    roi = img[y0:h - 60, x0:w - 10]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    dark = ((hsv[:, :, 2] < 130) & (hsv[:, :, 1] < 90)).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, _l, stats, _c = cv2.connectedComponentsWithStats(dark, 8)
    plate = None
    if n > 1:
        i = max(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA])
        if stats[i, cv2.CC_STAT_AREA] > 5000:
            plate = (int(stats[i, 2]), int(stats[i, 3]))
    return obj, plate


def delta(a, b):
    """相对变化（%）。a/b 可以是 (x,y,w,h) 或 (w,h)，两种都兼容。"""
    if not a or not b or len(a) != len(b):
        return None
    if len(a) == 4:
        a, b = (a[2], a[3]), (b[2], b[3])
    return round(max(abs(b[0] - a[0]) / max(a[0], 1),
                     abs(b[1] - a[1]) / max(a[1], 1)) * 100.0, 1)


def main() -> int:
    import m7_common as m7
    import m8_common as m8
    import m8x_152 as base
    from m3_common import add_common_args
    from harness import winutil as _wu

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = base.m7_boot(args, model=STL)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        pt = m7.select_object_strict(session)
        print(f"{LOG} object point = {pt}")
        # 固定几何：Rotate 槽在 1920x1080 最大化下稳定落在 x=1108（多次实测；
        # hover 扫描偶发读不到 tooltip，探针里不为此多花 30s）
        x = 1108
        print(f"{LOG} rotate slot @{x} (fixed geometry)")
        boxes = []
        for attempt in range(3):
            m7.click_slot(session, x)
            time.sleep(1.5)
            boxes = m7.gizmo_row_boxes(session, "rotate")
            print(f"{LOG} attempt{attempt + 1}: rotate grid = {boxes}")
            if boxes:
                break
            m7.toggle_gizmo_key(session, "rotate")     # 'R'
            time.sleep(1.0)
            boxes = m7.gizmo_row_boxes(session, "rotate")
            print(f"{LOG} attempt{attempt + 1} after 'R': {boxes}")
            if boxes:
                break
        if not boxes:
            print(f"{LOG} rotate tool NEVER activated — aborting "
                  f"(dragging now would only orbit the camera)")
            return 1
        print(f"{LOG} PANEL-OPEN-LABEL")          # 触发取证帧
        time.sleep(0.5)
        obj0, plate0 = shape(session)
        live = m7.find_centroid(session) or pt
        print(f"{LOG} baseline obj={obj0} plate={plate0} live_centroid={live}")
        # 颜色候选（记录用）
        import cv2
        import numpy as np
        from harness.anchors import capture_bgr
        img = capture_bgr(session)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hue = hsv[:, :, 0].astype(int)
        sat = hsv[:, :, 1].astype(int)
        val = hsv[:, :, 2].astype(int)
        okm = (sat > 110) & (val > 50)
        for name, m in (("green", okm & (hue > 45) & (hue < 75)),
                        ("blue", okm & (hue > 100) & (hue < 130)),
                        ("red", okm & ((hue < 8) | (hue > 172)))):
            mm = cv2.morphologyEx((m.astype(np.uint8) * 255),
                                  cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            n, _l, stats, cents = cv2.connectedComponentsWithStats(mm, 8)
            rows = []
            for i in range(1, n):
                if int(stats[i, cv2.CC_STAT_AREA]) < 80:
                    continue
                cx, cy = int(cents[i][0]), int(cents[i][1])
                if max(abs(cx - live[0]), abs(cy - live[1])) > 200:
                    continue
                rows.append((int(stats[i, cv2.CC_STAT_AREA]), cx, cy,
                             int(stats[i, 2]), int(stats[i, 3])))
            print(f"{LOG} blobs {name}: {sorted(rows, reverse=True)[:6]}")
        # 候选：①本体质心；②各色块**真实极值像素**（不是包围盒角——bbox 角
        # 常常是空白，落在床面上要么不动要么触发相机环绕，实测 10-19）。
        cands = [("body", live)]
        for name, m in (("green", okm & (hue > 45) & (hue < 75)),
                        ("blue", okm & (hue > 100) & (hue < 130)),
                        ("red", okm & ((hue < 8) | (hue > 172)))):
            mm = cv2.morphologyEx((m.astype(np.uint8) * 255),
                                  cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            n, _l, stats, cents = cv2.connectedComponentsWithStats(mm, 8)
            for i in range(1, n):
                if int(stats[i, cv2.CC_STAT_AREA]) < 120:
                    continue
                cx, cy = int(cents[i][0]), int(cents[i][1])
                if max(abs(cx - live[0]), abs(cy - live[1])) > 220:
                    continue
                sub = mm[stats[i, 1]:stats[i, 1] + stats[i, 3],
                         stats[i, 0]:stats[i, 0] + stats[i, 2]]
                ys, xs = np.nonzero(sub)
                if len(xs) < 20:
                    continue
                bx, by = int(stats[i, 0]), int(stats[i, 1])
                pts = [(int(xs.min()) + bx, int(ys[xs.argmin()]) + by),
                       (int(xs.max()) + bx, int(ys[xs.argmax()]) + by),
                       (int(xs[ys.argmin()]) + bx, int(ys.min()) + by),
                       (int(xs[ys.argmax()]) + bx, int(ys.max()) + by)]
                for k, (px, py) in enumerate(pts):
                    cands.append((f"{name}{'RLTB'[k]}", (px, py)))
        print(f"{LOG} candidates: {len(cands)} -> {[(c[0], c[1]) for c in cands][:14]}")
        z0 = m7.gizmo_row_boxes(session, "rotate")
        z_before = z0[-1][2] if z0 else ""
        print(f"{LOG} Z before = {z_before!r}")
        hits = []
        for name, (sx, sy) in cands[:20]:
            for ddx, ddy in ((60, 0), (-60, 0), (0, 60), (0, -60)):
                _wu.user32.SetCursorPos(*m7.client(session, sx, sy))
                time.sleep(0.2)
                m7.real_drag_screen(session, (sx, sy), (sx + ddx, sy + ddy))
                time.sleep(0.9)
                boxes = m7.gizmo_row_boxes(session, "rotate")
                z_now = boxes[-1][2] if boxes else ""
                obj1, plate1 = shape(session)
                dobj = delta(obj0, obj1)
                dplate = delta(plate0, plate1)
                good = (z_now and z_before and z_now != z_before) or                        (dobj is not None and dplate is not None
                        and dobj > 8 and dplate < 3)
                print(f"{LOG} {name}({sx},{sy}) d({ddx},{ddy}) Z={z_now!r} "
                      f"obj={obj1} dobj={dobj} dplate={dplate}"
                      f"{'  <<ROTATED' if good else ''}")
                if good:
                    hits.append((name, sx, sy, ddx, ddy, z_before, z_now))
                    break
            if hits:
                break
        print(f"{LOG} HITS: {hits}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
