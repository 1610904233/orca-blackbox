#!/usr/bin/env python3
# probe_241_picker10.py — 按测试方口径找"用户配置 → 自定义"（悬停出二级菜单）
#
# 测试方 10-10 口径：耗材栏点开后，**用户预设**在列表里的「用户配置 → 自定义」一级菜单下，
# **鼠标悬停**一级菜单才弹出二级菜单（列出用户预设耗材）。
#
# 本轮：
#   1) 打开选择框，把左栏滚到顶（多滚几屏），OCR 全部行（原样打印，中文行也要看）；
#   2) 逐行**悬停**（不点击），每次枚举弹层集合；出现新弹层就 OCR 并在其中找 'TEST'/'SnapSpeed'；
#   3) 命中后截图留证。
import argparse
import ctypes
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pk250]"
ART = HERE / "artifacts"


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xPA_{name}.png"), img)
    print(f"{LOG} shot -> m8xPA_{name}.png")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        m8.wait_slots(session)
        pop, ch, how = m8._picker_open(session, 2)
        print(f"{LOG} picker opened via {how!r}")
        time.sleep(0.8)
        panes = m8._picker_panes(session)
        vend = next((p for p in panes if p["is_vendor"]), None)
        print(f"{LOG} panes: {[(p['rect'], p['is_vendor']) for p in panes]}")
        vx = vend["rect"][0] + 40
        vy = (vend["rect"][1] + vend["rect"][3]) // 2
        for _i in range(30):        # 滚到顶（多滚几屏，别漏掉上面的分组）
            winutil.real_wheel_screen(vx, vy, 3)
            time.sleep(0.08)
        time.sleep(0.8)
        panes = m8._picker_panes(session)
        vend = next((p for p in panes if p["is_vendor"]), None)
        rows = vend["rows"]
        print(f"{LOG} left pane TOP ({len(rows)} rows):")
        for y, t, x in rows:
            print(f"{LOG}    y={y:4d} x={x:4d} {t!r}")
        shot("left_top", vend["rect"])

        # 逐行悬停，看有没有二级菜单
        seen_rects = {p["rect"] for p in panes}
        for y, t, x in rows:
            if t.strip().startswith("------"):
                continue
            hx, hy = vend["rect"][0] + 150, y
            winutil.user32.SetCursorPos(hx, hy)
            time.sleep(1.8)
            now = m8._picker_panes(session)
            new = [p for p in now if p["rect"] not in seen_rects]
            if new:
                for p in new:
                    seen_rects.add(p["rect"])
                    blob = " ".join(t2 for _y2, t2, _x2 in p["rows"])
                    hit = "TEST" in blob.upper() or "SnapSpeed" in blob
                    print(f"{LOG} hover row {t!r} -> NEW pane {p['rect']} hit={hit}")
                    print(f"{LOG}    rows: {[t2[:34] for _y2, t2, _x2 in p['rows']][:14]}")
                    if hit:
                        shot(f"hit_{t.strip()[:12].replace(' ', '_')}", p["rect"])
            else:
                print(f"{LOG} hover row {t!r}: no new pane")
            # 移开鼠标，避免残留子菜单影响下一次判断
            winutil.user32.SetCursorPos(vend["rect"][2] + 40, 200)
            time.sleep(0.4)
        winutil.user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        winutil.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.6)
        print(f"{LOG} combo after probe: {m8.combo_text(ch)!r}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
