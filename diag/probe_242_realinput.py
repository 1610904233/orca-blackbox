#!/usr/bin/env python3
# probe_242_realinput.py — 方案可行性验证：僵尸态下「授前台 + 真实输入」
# 能否恢复选中（档一/档二方案的关键不确定点，m8x_152 恢复的前提）
#
# 复现 F-10 僵尸态：选中 -> Scale 输入 120 -> 槽位 toggle 关面板。
# 然后逐层验证：
#   L0 当前前台是谁
#   L1 裸真实点击模型（既有 real_click_screen）
#   L2 force_set_foreground + 真实点击
#   L3 前台下真键盘 'M'（Move 面板开=键盘通道活）
#   L4 前台下真实框选拖拽
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

LOG = "[p242ri]"


def selected(session):
    return m7.object_selected(session)


def deselect(session):
    sx, sy = m7.client(session, 700, 900)
    winutil.user32.SetCursorPos(sx, sy)
    winutil.real_click_screen(sx, sy)
    time.sleep(0.8)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=PRUSA_STL)
    args = ap.parse_args()
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, _ = m8.wait_arrival(session)
        m7.ensure_maximized(session)
        time.sleep(1.5)
        pt = m7.select_object_strict(session)
        print(f"{LOG} fresh-state select pt={pt} (sanity)")

        # --- 造僵尸态：scale 120 + 槽位关 ---
        m7.click_slot(session, 1152)
        time.sleep(1.5)
        boxes = m7.gizmo_row_boxes(session, "scale")
        if boxes:
            m7.type_into_field(session, boxes[0][:2], "120", old_len=4,
                               recipe=5)
            print(f"{LOG} typed -> "
                  f"{m7.read_gizmo_field(session, 'scale', 0, timeout_s=4)[1]!r}")
        m7.click_slot(session, 1152)
        time.sleep(1.2)
        closed = not m7.gizmo_row_boxes(session, "scale")
        print(f"{LOG} zombie state ready (panel closed={closed})")

        cands = m7.model_candidates(session)
        cx, cy = cands[0] if cands else (1171, 585)
        sx, sy = m7.client(session, cx, cy)

        # L0: 前台是谁
        fg = winutil.user32.GetForegroundWindow()
        print(f"{LOG} L0 foreground={hex(fg)} app={hex(session.hwnd)} "
              f"match={fg == session.hwnd}")

        # L1: 裸真实点击
        winutil.user32.SetCursorPos(sx, sy)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.2)
        l1 = selected(session)
        print(f"{LOG} L1 bare real click selected={l1}")
        deselect(session)

        # L2: 强制前台 + 真实点击
        got_fg = winutil.force_set_foreground(session.hwnd)
        fg2 = winutil.user32.GetForegroundWindow()
        print(f"{LOG} L2 force_set_foreground ok={got_fg} "
              f"fg_now_match={fg2 == session.hwnd}")
        winutil.user32.SetCursorPos(sx, sy)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.2)
        l2 = selected(session)
        print(f"{LOG} L2 fg+real click selected={l2}")
        deselect(session)

        # L3: 前台下真键盘 'M'
        winutil.force_set_foreground(session.hwnd)
        winutil.user32.keybd_event(0x4D, 0, 0, 0)
        time.sleep(0.06)
        winutil.user32.keybd_event(0x4D, 0, 2, 0)
        time.sleep(1.5)
        l3 = bool(m7.gizmo_row_boxes(session, "position"))
        print(f"{LOG} L3 fg+real 'M' opens move panel={l3}")
        # 关掉 move 面板
        m7.click_slot(session, 1064)
        time.sleep(1.0)

        # L4: 前台下真实框选
        winutil.force_set_foreground(session.hwnd)
        m7.real_drag_screen(session, (cx - 220, cy - 120),
                            (cx + 220, cy + 120), settle=1.2)
        l4 = selected(session)
        print(f"{LOG} L4 fg+real rubber-band selected={l4}")

        verdict = l2 or l4
        print(f"{LOG} VERDICT: real-input route works in zombie state = "
              f"{verdict}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
