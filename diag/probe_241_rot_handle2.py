#!/usr/bin/env python3
# probe_241_rot_handle2.py — 旋转手柄（实心箭头锥）的可靠定位
#
# 前情（10-20/21）：拖"蓝块"有时能转（Z 0.00 -> 171.54），但按色块内部像素
# 采样却全落空。怀疑：色彩分割把**环的弧线**（空心、不可拖）和**箭头锥**
# （实心、可拖）混在一起了。
# 判据：填充率 fill = area / (w*h)。实心三角锥 fill 高（>=0.35），弧线低。
# 本探针在 Rotate 激活态下打印每个色块分量的 (area, bbox, fill, 质心)，
# 然后按 fill 从高到低逐个"点住质心横拖"，用面板 Z 值变化判定命中。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkRot2]"
STL = HERE / "fixtures" / "Prusa.stl"


def components(session, live, radius=240):
    """各色相类的连通分量：[(cls, area, fill, cx, cy, w, h)]（按面积降序）。"""
    import cv2
    import numpy as np
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(int)
    sat = hsv[:, :, 1].astype(int)
    val = hsv[:, :, 2].astype(int)
    ok = (sat > 110) & (val > 50)
    classes = (("blue", ok & (hue > 100) & (hue < 130)),
               ("green", ok & (hue > 45) & (hue < 75)),
               ("red", ok & ((hue < 8) | (hue > 172))))
    out = []
    for cls, m in classes:
        mm = (m.astype(np.uint8) * 255)      # 不做 close：保持锥/弧的形状差异
        n, _l, stats, cents = cv2.connectedComponentsWithStats(mm, 8)
        for i in range(1, n):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < 120:
                continue
            w, h = int(stats[i, 2]), int(stats[i, 3])
            cx, cy = int(cents[i][0]), int(cents[i][1])
            if max(abs(cx - live[0]), abs(cy - live[1])) > radius:
                continue
            fill = area / max(w * h, 1)
            out.append((cls, area, round(fill, 2), cx, cy, w, h))
    out.sort(key=lambda t: -t[1])
    return out


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
        print(f"{LOG} object pt={pt}")
        x = 1108
        for attempt in range(3):
            m7.click_slot(session, x)
            time.sleep(1.5)
            if m7.gizmo_row_boxes(session, "rotate"):
                break
            m7.toggle_gizmo_key(session, "rotate")
            time.sleep(1.0)
        boxes = m7.gizmo_row_boxes(session, "rotate")
        print(f"{LOG} rotate panel boxes={boxes}")
        if not boxes:
            return 1
        print(f"{LOG} LABEL-ROTATE-ACTIVE")
        time.sleep(0.5)
        live = m7.find_centroid(session) or pt
        comps = components(session, live)
        print(f"{LOG} live={live}  components({len(comps)}):")
        for c in comps[:14]:
            print(f"{LOG}   {c}")
        # 按 fill 从高到低（实心优先），逐个横拖
        cands = sorted([c for c in comps if c[2] >= 0.30], key=lambda t: -t[2])
        print(f"{LOG} solid candidates: {[(c[0], c[3], c[4], c[2]) for c in cands][:8]}")
        z_before = boxes[-1][2] if boxes else ""
        zs = []
        hit = None
        for cls, area, fill, cx, cy, w, h in cands[:8]:
            for ddx in (45, -45):
                m7.real_drag_screen(session, (cx, cy), (cx + ddx, cy))
                time.sleep(0.9)
                b2 = m7.gizmo_row_boxes(session, "rotate")
                z_now = b2[-1][2] if b2 else ""
                print(f"{LOG} drag {cls}({cx},{cy}) fill={fill} d({ddx},0) "
                      f"-> Z={z_now!r} (before {z_before!r})")
                if z_now:
                    zs.append((cls, cx, cy, ddx, z_now))
                if z_now and z_before and z_now != z_before:
                    hit = (cls, cx, cy, ddx, z_before, z_now)
                    break
            if hit:
                break
        print(f"{LOG} HIT={hit}")
        print(f"{LOG} z-series={zs}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
