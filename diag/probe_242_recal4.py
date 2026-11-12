#!/usr/bin/env python3
# probe_242_recal4.py — B4: 面板「确定关闭」后的重选中通道
# ESC 不再可靠关面板（B3 里 ESC 后面板还开着）——先 ESC 到关或槽位
# toggle-off 强制关；然后依次试：
#   c1 裸点击；c2 Ctrl+A；c3 框选；c4 +8s 延时再点击；c5 重开 rotate 面板
#   再关掉后点击。每步之间点空床取消选中。
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

LOG = "[p242r4]"
SHOTS = HERE / "artifacts" / "shots" / "p242rc"


def shot(session, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(SHOTS / name), capture_bgr(session))


def esc(n=2):
    for _ in range(n):
        winutil.user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        winutil.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.5)


def deselect(session):
    sx, sy = m7.client(session, 700, 900)
    winutil.user32.SetCursorPos(sx, sy)
    winutil.real_click_screen(sx, sy)
    time.sleep(0.8)


def force_panel_closed(session):
    """ESC 一轮；不行再槽位 toggle-off。返回 True=面板确认关闭。"""
    esc(2)
    if not m7.gizmo_row_boxes(session, "scale"):
        return True
    m7.click_slot(session, 1152)      # 现在面板开着 -> 这次点击是关
    time.sleep(1.2)
    return not m7.gizmo_row_boxes(session, "scale")


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
        closed = force_panel_closed(session)
        print(f"{LOG} panel force-closed = {closed}")
        if not closed:
            print(f"{LOG} could not close panel — abort (state != case)")
            return 1
        cands = m7.model_candidates(session)
        cx, cy = cands[0] if cands else (1171, 585)
        # c1 裸点击
        sx, sy = m7.client(session, cx, cy)
        winutil.user32.SetCursorPos(sx, sy)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.2)
        print(f"{LOG} c1 click selected={m7.object_selected(session)}")
        deselect(session)
        # c2 Ctrl+A
        l, t, r, b = winutil.window_rect(session.hwnd)
        winutil.user32.SetCursorPos((l + r) // 2, t + 12)
        winutil.real_click_screen((l + r) // 2, t + 12)
        time.sleep(0.4)
        winutil.user32.keybd_event(0x11, 0, 0, 0)
        winutil.user32.keybd_event(ord("A"), 0, 0, 0)
        time.sleep(0.05)
        winutil.user32.keybd_event(ord("A"), 0, 2, 0)
        winutil.user32.keybd_event(0x11, 0, 2, 0)
        time.sleep(1.2)
        print(f"{LOG} c2 Ctrl+A selected={m7.object_selected(session)}")
        deselect(session)
        # c3 框选
        m7.real_drag_screen(session, (cx - 220, cy - 120),
                            (cx + 220, cy + 120), settle=1.2)
        print(f"{LOG} c3 rubber-band selected={m7.object_selected(session)}")
        deselect(session)
        # c4 延时 8s 再点击
        time.sleep(8.0)
        winutil.user32.SetCursorPos(sx, sy)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.2)
        print(f"{LOG} c4 delayed click selected={m7.object_selected(session)}")
        deselect(session)
        # c5 重开 rotate 再关，然后点击
        m7.click_slot(session, 1100)
        time.sleep(1.2)
        m7.click_slot(session, 1100)
        time.sleep(1.2)
        winutil.user32.SetCursorPos(sx, sy)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.2)
        print(f"{LOG} c5 after rotate cycle selected="
              f"{m7.object_selected(session)}")
        shot(session, "B4_end.png")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
