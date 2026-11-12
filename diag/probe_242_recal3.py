#!/usr/bin/env python3
# probe_242_recal3.py — B3: m8x_152 s4 的重选中通道对照
# 复现：strict select -> scale 120 -> 真 ESC×2（面板关）后，
#   a) 标题栏授焦 + Ctrl+A     -> 信息面板出现？
#   b) 框选（空床->跨模型拖拽） -> 信息面板出现？
#   c) 裸点击 + 5s 延时再点    -> 信息面板出现？
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import cv2
import m7_common as m7
import m8_common as m8
from harness import winutil
from m1_minimal_loop import capture_bgr
from m3_common import PRUSA_STL, add_common_args, boot_session

LOG = "[p242r3]"
SHOTS = HERE / "artifacts" / "shots" / "p242rc"


def shot(session, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(SHOTS / name), capture_bgr(session))


def real_esc(n=2):
    for _ in range(n):
        winutil.user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        winutil.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.5)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=PRUSA_STL)
    args = ap.parse_args()
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, _ = m8.wait_arrival(session)
        m7.ensure_maximized(session)
        time.sleep(1.5)
        pt = m7.select_object_strict(session)
        print(f"{LOG} pre select pt={pt}")
        m7.click_slot(session, 1152)
        time.sleep(1.5)
        boxes = m7.gizmo_row_boxes(session, "scale")
        if boxes:
            m7.type_into_field(session, boxes[0][:2], "120", old_len=4,
                               recipe=0)
        real_esc(2)
        print(f"{LOG} panel open after ESC = "
              f"{bool(m7.gizmo_row_boxes(session, 'scale'))}")
        shot(session, "B3_postESC.png")
        # a) Ctrl+A
        l, t, r, b = winutil.window_rect(session.hwnd)
        winutil.user32.SetCursorPos((l + r) // 2, t + 12)
        winutil.real_click_screen((l + r) // 2, t + 12)
        time.sleep(0.5)
        winutil.user32.keybd_event(0x11, 0, 0, 0)
        winutil.user32.keybd_event(ord("A"), 0, 0, 0)
        time.sleep(0.05)
        winutil.user32.keybd_event(ord("A"), 0, 2, 0)
        winutil.user32.keybd_event(0x11, 0, 2, 0)
        time.sleep(1.5)
        info_a = m7.object_info_text(session)
        print(f"{LOG} a) Ctrl+A info={info_a[:60]!r} "
              f"selected={m7.object_selected(session)}")
        # 先取消选中（点空床左下），再做 b/c
        sx, sy = m7.client(session, 700, 900)
        winutil.user32.SetCursorPos(sx, sy)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.0)
        # b) 框选拖拽（从模型左侧空床拖到右侧）
        cands = m7.model_candidates(session)
        cx, cy = cands[0] if cands else (1171, 585)
        m7.real_drag_screen(session, (cx - 220, cy - 120),
                            (cx + 220, cy + 120), settle=1.2)
        info_b = m7.object_info_text(session)
        print(f"{LOG} b) rubber-band info={info_b[:60]!r} "
              f"selected={m7.object_selected(session)}")
        # 取消再试 c
        winutil.user32.SetCursorPos(sx, sy)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.0)
        # c) 裸点击 + 延时
        scx, scy = m7.client(session, cx, cy)
        winutil.user32.SetCursorPos(scx, scy)
        time.sleep(5.0)
        winutil.real_click_screen(scx, scy)
        time.sleep(1.5)
        info_c = m7.object_info_text(session)
        print(f"{LOG} c) plain click info={info_c[:60]!r} "
              f"selected={m7.object_selected(session)}")
        shot(session, "B3_end.png")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
