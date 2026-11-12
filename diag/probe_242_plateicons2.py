#!/usr/bin/env python3
# probe_242_plateicons2.py — 盘侧图标第二批标定（用户指认：
#   «编辑盘名» = 盘名标签(未命名)旁铅笔图标；«排列零件» = 右侧竖列第3个图标）
# 用盘面暗块 bbox 自动定位右侧竖列，逐点 hover 读 tooltip；同时 OCR 盘名标签。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7
import m8_common as m8
from harness import winutil
from m3_common import PRUSA_STL, add_common_args, boot_session

LOG = "[p242pi2]"


def plate_bbox(session):
    import cv2
    import numpy as np
    img = m7.capture_bgr(session)
    h, w = img.shape[:2]
    x0, y0 = m7.VIEWPORT_X0 + 10, 110
    roi = img[y0:h - 60, x0:w - 10]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    dark = ((hsv[:, :, 2] < 130) & (hsv[:, :, 1] < 90)).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, _l, stats, _c = cv2.connectedComponentsWithStats(dark, 8)
    if n <= 1:
        return None
    i = max(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA])
    bx = int(stats[i, cv2.CC_STAT_LEFT]) + x0
    by = int(stats[i, cv2.CC_STAT_TOP]) + y0
    bw = int(stats[i, cv2.CC_STAT_WIDTH])
    bh = int(stats[i, cv2.CC_STAT_HEIGHT])
    print(f"{LOG} plate bbox=({bx},{by},{bw},{bh}) right={bx + bw} top={by}")
    return bx, by, bw, bh


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=PRUSA_STL)
    args = ap.parse_args()
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.2%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        import numpy as np
        import m8x_194 as _c194
        # 场景：加两块 primitive（中心重叠），排列效果才可见
        ok1 = m7.op_add_primitive(session, "cube")
        time.sleep(1.0)
        ok2 = m7.op_add_primitive(session, "cube")
        print(f"{LOG} primitives added: {ok1} {ok2}")
        time.sleep(2.0)
        b0 = m7.find_centroids(session, limit=4)
        img0 = m7.capture_bgr(session)
        # rail#3 候选 x 各点一次，看对象是否分离
        for x in (1470, 1490, 1510):
            for y in (470, 479, 488):
                sx, sy = m7.client(session, x, y)
                winutil.user32.SetCursorPos(sx, sy)
                time.sleep(0.3)
                winutil.real_click_screen(sx, sy)
                time.sleep(3.0)
                b1 = m7.find_centroids(session, limit=4)
                img1 = m7.capture_bgr(session)
                mad = float(np.mean(np.abs(img1[110:-400].astype(int)
                                           - img0[110:-400].astype(int))))
                print(f"{LOG} rail@({x},{y}): mad={mad:.2f} cents {b0} -> {b1}")
                if b1 and len(b1) >= 2 and mad > 1.0:
                    print(f"{LOG} ARRANGE FOUND @({x},{y})")
                    return 0
                img0 = img1
                b0 = b1
        # 锁：点第4个槽位族，截盘列表区前后差分
        crop0 = m7.capture_bgr(session)[700:1032, 0:420]
        for x in (1470, 1490, 1510):
            for y in (515, 523, 531):
                sx, sy = m7.client(session, x, y)
                winutil.user32.SetCursorPos(sx, sy)
                time.sleep(0.3)
                winutil.real_click_screen(sx, sy)
                time.sleep(2.0)
                crop1 = m7.capture_bgr(session)[700:1032, 0:420]
                mad = float(np.mean(np.abs(crop1.astype(int)
                                           - crop0.astype(int))))
                print(f"{LOG} lock?@({x},{y}): plate-list mad={mad:.2f}")
                if mad > 1.0:
                    print(f"{LOG} LOCK CANDIDATE @({x},{y})")
                    return 0
                crop0 = crop1
        return 0
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
