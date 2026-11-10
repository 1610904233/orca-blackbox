#!/usr/bin/env python3
# probe_241_paint2.py — 涂色在普通 U1 项目 + cube20 上是否可涂（夹具对照）
#
# probe_241_paint 结论：在 mixed_filament_test 夹具上，单击/慢拖/选笔刷工具
# 三种机制像素差全 <1.2 = 完全没反应。本探针换最简夹具（Prusa 默认 U1 4 丝
# 项目 + 导入 cube20）复测：若这里能涂 → 问题在混色夹具的对象（多体积/
# 已涂色）；若也不能涂 → 涂色交互本身不可黑盒驱动。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPaint2]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"


def diff_rect(a, b, rect):
    x0, y0, x1, y1 = rect
    sa = a[y0:y1, x0:x1].astype(int)
    sb = b[y0:y1, x0:x1].astype(int)
    return float(abs(sa - sb).mean()) if sa.size else -1.0


def main() -> int:
    import cv2
    import numpy as np
    import m4e_mixing_paint as m4e
    import m7_common as m7
    import m8_common as m8
    import m8x_158 as c158
    from m3_common import add_common_args, boot_session
    from harness import winutil as wu
    from harness.anchors import VIEWPORT_X0 as VP_X0, VIEWPORT_Y0 as VP_Y0

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, _ = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok}")
        m7.ensure_maximized(session)
        c158.import_model(session, CUBE)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if "8000" in (m7.object_info_text(session) or ""):
                break
            time.sleep(1.5)
        print(f"{LOG} cube info={m7.object_info_text(session)[:60]!r}")
        if not m4e.select_model(session):
            print(f"{LOG} select FAILED")
            return 1
        px, tip = m4e.find_slot(session, lambda t: "color" in t and
                                 "paint" in t)
        print(f"{LOG} paint slot={px} tip={tip!r}")
        if px is None:
            return 1
        sx, sy = m4e.client(session, px, m4e.BAR_Y)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(1.5)
        print(f"{LOG} palette={m4e.palette_state(session)[:2]}")

        # 模型 bbox（排除调色板）
        img = m4e.viewport_img(session)
        h, w = img.shape[:2]
        x0, y0 = VP_X0 + 10, VP_Y0 + 30
        band = img[y0:h - 60, x0:1400].astype(int)
        spread = band.max(axis=2) - band.min(axis=2)
        mask = (spread > 45).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                                np.ones((7, 7), np.uint8))
        n, _l, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
        i = max(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA])
        cx = int(cents[i][0]) + x0
        cy = int(cents[i][1]) + y0
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        print(f"{LOG} blob center=({cx},{cy}) {bw}x{bh}")
        rect = (cx - bw // 2 - 6, cy - bh // 2 - 6,
                cx + bw // 2 + 6, cy + bh // 2 + 6)

        # 瓦片起点按 palette_state 实测位置扫描：直接用已知 6 格起点
        tile_x = [1432 + round(33.5 * k) for k in range(6)]
        tx, ty = tile_x[1], 152
        sx, sy = m4e.client(session, tx, ty)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.25)
        wu.real_click_screen(sx, sy)
        time.sleep(0.8)
        print(f"{LOG} picked tile2 @({tx},{ty})")

        def measure(label, fn):
            b = m4e.viewport_img(session)
            fn()
            time.sleep(1.2)
            a = m4e.viewport_img(session)
            d = diff_rect(a, b, rect)
            cv2.imwrite(str(ART / f"pkpaint2_{label}_after.png"), a)
            print(f"{LOG} {label}: diff={d:.2f}")
            return d

        s1, s2 = m4e.client(session, cx, cy)
        dA = measure("A_click", lambda: (
            wu.user32.SetCursorPos(s1, s2), time.sleep(0.9),
            wu.real_click_screen(s1, s2)))
        a = (cx - bw // 3, cy)
        b = (cx + bw // 3, cy)
        def _drag():
            s1, s2 = m4e.client(session, *a)
            wu.user32.SetCursorPos(s1, s2)
            time.sleep(0.9)
            m7.real_drag_screen(session, a, b, steps=40, settle=0.8)
        dB = measure("B_drag", _drag)
        print(f"{LOG} RESULT A={dA:.2f} B={dB:.2f}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
