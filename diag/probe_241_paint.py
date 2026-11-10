#!/usr/bin/env python3
# probe_241_paint.py — 涂色笔刷机制判别（#193）
#
# 已知：涂色 gizmo 打开、调色板 6 瓦片、点瓦片后 Selected filament 文本变化
# （选色生效），但「瓦片→悬停→拖笔」的所有组合像素差都 <2.3（未落墨）。
# 本探针依次判别三种机制：
#   A. 单击模型中心（若默认工具是填充桶 → 单击即上色）
#   B. 慢速长拖（40 步 × 0.08s，起止都在模型内）
#   C. 先点工具行第 4 个图标（疑似笔刷）再慢拖
# 每步量模型 bbox 像素差 + 存前后帧，一次看清。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPaint]"
ART = HERE / "artifacts"


def model_blob(session, x1_max=1400):
    import cv2
    import numpy as np
    import m4e_mixing_paint as m4e
    from harness.anchors import VIEWPORT_X0 as VP_X0, VIEWPORT_Y0 as VP_Y0
    img = m4e.viewport_img(session)
    h, w = img.shape[:2]
    x0, y0 = VP_X0 + 10, VP_Y0 + 30
    x1, y1 = min(x1_max, w - 10), h - 60
    band = img[y0:y1, x0:x1].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    i = max(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA])
    bx = int(stats[i, cv2.CC_STAT_LEFT]) + x0
    by = int(stats[i, cv2.CC_STAT_TOP]) + y0
    bw = int(stats[i, cv2.CC_STAT_WIDTH])
    bh = int(stats[i, cv2.CC_STAT_HEIGHT])
    print(f"{LOG} blob=({bx},{by},{bw}x{bh}) area={stats[i, cv2.CC_STAT_AREA]}")
    if stats[i, cv2.CC_STAT_AREA] < 600:
        return None
    return (int(cents[i][0]) + x0, int(cents[i][1]) + y0, bw, bh)


def diff_rect(a, b, rect):
    x0, y0, x1, y1 = rect
    sa = a[y0:y1, x0:x1].astype(int)
    sb = b[y0:y1, x0:x1].astype(int)
    if sa.size == 0:
        return -1.0
    return float(abs(sa - sb).mean())


def main() -> int:
    import cv2
    import m4e_mixing_paint as m4e
    import m7_common as m7
    import m8_common as m8
    from m3_common import MIXED_3MF, add_common_args, boot_session
    from harness import winutil as wu

    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, _frac = m8.wait_arrival(session, timeout_s=240)
        print(f"{LOG} arrived={ok}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        if not m4e.select_model(session):
            print(f"{LOG} select FAILED")
            return 1
        px, _tip = m4e.find_slot(session, lambda t: "color" in t and
                                 "paint" in t)
        sx, sy = m4e.client(session, px, m4e.BAR_Y)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(1.5)
        print(f"{LOG} palette={m4e.palette_state(session)[:2]}")
        blob = model_blob(session)
        if not blob:
            return 1
        cx, cy, bw, bh = blob
        rect = (cx - bw // 2 - 6, cy - bh // 2 - 6,
                cx + bw // 2 + 6, cy + bh // 2 + 6)
        print(f"{LOG} rect={rect}")

        tile_x = [1432 + round(33.5 * i) for i in range(6)]

        def pick_tile(i):
            tx, ty = tile_x[i], 152
            sx, sy = m4e.client(session, tx, ty)
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.25)
            wu.real_click_screen(sx, sy)
            time.sleep(0.8)
            print(f"{LOG} picked tile{i + 1} @({tx},{ty})")

        def measure(label, fn):
            img_b = m4e.viewport_img(session)
            fn()
            time.sleep(1.2)
            img_a = m4e.viewport_img(session)
            d = diff_rect(img_b, img_a, rect)
            cv2.imwrite(str(ART / f"pkpaint_{label}_before.png"), img_b)
            cv2.imwrite(str(ART / f"pkpaint_{label}_after.png"), img_a)
            print(f"{LOG} {label}: diff={d:.2f}")
            return d

        # A. 单击模型中心（填充桶假设）
        pick_tile(4)                      # 红色
        def click_center():
            s1, s2 = m4e.client(session, cx, cy)
            wu.user32.SetCursorPos(s1, s2)
            time.sleep(0.9)
            wu.real_click_screen(s1, s2)
        dA = measure("A_click", click_center)

        # B. 慢速长拖（40 步）
        pick_tile(1)                      # 黄色
        def slow_drag():
            a = (cx - bw // 3, cy)
            b = (cx + bw // 3, cy)
            s1, s2 = m4e.client(session, *a)
            wu.user32.SetCursorPos(s1, s2)
            time.sleep(0.9)
            m7.real_drag_screen(session, a, b, steps=40, settle=0.8)
        dB = measure("B_slowdrag", slow_drag)

        # C. 先点工具行（第 4 个图标，疑似笔刷）再慢拖
        def tool_and_drag():
            ttx, tty = 1528, 258
            s1, s2 = m4e.client(session, ttx, tty)
            wu.user32.SetCursorPos(s1, s2)
            time.sleep(0.3)
            wu.real_click_screen(s1, s2)
            time.sleep(0.8)
            a = (cx - bw // 3, cy)
            b = (cx + bw // 3, cy)
            s1, s2 = m4e.client(session, *a)
            wu.user32.SetCursorPos(s1, s2)
            time.sleep(0.9)
            m7.real_drag_screen(session, a, b, steps=40, settle=0.8)
        pick_tile(4)
        dC = measure("C_tool_drag", tool_and_drag)

        print(f"{LOG} RESULT A(click)={dA:.2f} B(slowdrag)={dB:.2f} "
              f"C(tool+drag)={dC:.2f}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
