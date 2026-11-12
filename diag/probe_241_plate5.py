#!/usr/bin/env python3
# probe_241_plate5.py — 盘侧图标列**逐个点击**标定（#194/#197/#198 用）
#
# 图标没有 tooltip（GL 自绘，实测读不到），只能点一次看一次结果：
#   记录 = 盘层渲染宽度 / 彩色占比 / 是否弹出对话框或输入框 / 窗口标题
# 顺序从**下往上**（把可能的"移除当前板"留到最后），每次点击后打 LABEL 供取证。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPlate5]"
STL = HERE / "fixtures" / "Prusa.stl"


def plate_width(session):
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
        return 0, 0
    i = max(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA])
    return int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])


def state(session):
    import m7_common as m7
    from harness import export_util
    dlg = m7.wait_dialog(session.pid, timeout_s=0.4)
    dlg_info = ""
    if dlg:
        kids = [t.strip() for t, _r, _h in
                export_util._children_texts(dlg[3]) if t.strip()]
        dlg_info = f"dlg={dlg[1]!r} kids={kids[:6]}"
    edits = [t for t, _r, _h in export_util._children_texts(session.hwnd)
             if t.strip().startswith("Edit")]
    return (f"plate_w={plate_width(session)} frac={m7.model_colored_frac(session):.3%} "
            f"{dlg_info}")


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
        m7.ensure_maximized(session)
        print(f"{LOG} state0: {state(session)}")
        m7.click_slot(session, 756)
        time.sleep(4.0)
        print(f"{LOG} state1 (2 plates): {state(session)}")
        print(f"{LOG} LABEL-TWO-PLATES")
        time.sleep(0.4)
        # 当前盘（02）的图标列，自下而上
        cands = [(1409, 448), (1406, 422), (1403, 396), (1400, 370),
                 (1397, 344), (1394, 318), (1390, 292)]
        for idx, (x, y) in enumerate(cands):
            sx, sy = m7.client(session, x, y)
            _wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            print(f"{LOG} LABEL-ICON{idx}-BEFORE")
            _wu.real_click_screen(sx, sy)
            time.sleep(2.5)
            print(f"{LOG} icon{idx} @({x},{y}) -> {state(session)}")
            print(f"{LOG} LABEL-ICON{idx}-AFTER")
            # 关掉可能弹出的对话框，继续下一个图标
            dlg = m7.wait_dialog(session.pid, timeout_s=0.4)
            if dlg:
                m7.click_dialog_button(dlg[3], "cancel", fallback_first=False)
                time.sleep(1.0)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
