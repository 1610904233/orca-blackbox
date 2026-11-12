#!/usr/bin/env python3
# probe_242_recal2.py — 242d 重标定第二轮：
#   B2 (m8x_152): scale+ESC 后为何点不中模型——点击活性对照（rotate 槽）、
#      槽位干净重开关对照、'M' 键 gizmo 口径
#   C2 (m8x_153): 'Please choose the filament col' 新对话框结构 dump + 试选色
#   A2 (m8a): 标题栏授焦 + Ctrl+A + fit 差；随后暗块分离度复查（#16）
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
from m3_common import (MULTI_PLATE_3MF, PRUSA_STL, add_common_args,
                       boot_session)

LOG = "[p242r2]"
SHOTS = HERE / "artifacts" / "shots" / "p242rc"


def shot(session, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(SHOTS / name), capture_bgr(session))
    print(f"{LOG} shot -> {name}")


def real_esc(n=2):
    for _ in range(n):
        winutil.user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        winutil.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.5)


def try_select(session, tag, limit=3):
    for cx, cy in m7.model_candidates(session)[:limit]:
        sx, sy = m7.client(session, cx, cy)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.25)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.0)
        got = m7.object_selected(session)
        print(f"{LOG} {tag} click ({cx},{cy}) selected={got}")
        if got:
            return (cx, cy)
    return None


def part_b2(args):
    print(f"{LOG} ===== B2: scale+ESC zombie =====")
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, frac = m8.wait_arrival(session)
        m7.ensure_maximized(session)
        time.sleep(1.5)
        pt = m7.select_object_strict(session)
        print(f"{LOG} B2 pre select pt={pt}")
        m7.click_slot(session, 1152)
        time.sleep(1.5)
        boxes = m7.gizmo_row_boxes(session, "scale")
        if boxes:
            m7.type_into_field(session, boxes[0][:2], "120", old_len=4,
                               recipe=0)
            print(f"{LOG} B2 typed -> "
                  f"{m7.read_gizmo_field(session, 'scale', 0, timeout_s=4)[1]!r}")
        real_esc(2)
        print(f"{LOG} B2 panel open after real ESC = "
              f"{bool(m7.gizmo_row_boxes(session, 'scale'))}")
        # b1: 直接点模型
        try_select(session, "b1-postESC")
        # b2: 点击活性对照——点 rotate 槽，面板开不开
        m7.click_slot(session, 1100)
        time.sleep(1.5)
        rot_open = bool(m7.gizmo_row_boxes(session, "rotate"))
        print(f"{LOG} B2 rotate panel opens after ESC-zombie = {rot_open}")
        if rot_open:
            m7.click_slot(session, 1100)
            time.sleep(1.0)
        # b3: scale 槽干净重开 + 再点掉（toggle off）
        m7.click_slot(session, 1152)
        time.sleep(1.5)
        reopened = bool(m7.gizmo_row_boxes(session, "scale"))
        print(f"{LOG} B2 scale reopens = {reopened}")
        m7.click_slot(session, 1152)
        time.sleep(1.2)
        print(f"{LOG} B2 scale after clean toggle-off = "
              f"{bool(m7.gizmo_row_boxes(session, 'scale'))}")
        print(f"{LOG} B2 b3 select after toggle-off = "
              f"{bool(try_select(session, 'b3-after-toggleoff'))}")
        # b4: 'M' 键口径
        winutil.user32.keybd_event(0x4D, 0, 0, 0)
        time.sleep(0.06)
        winutil.user32.keybd_event(0x4D, 0, 2, 0)
        time.sleep(1.2)
        print(f"{LOG} B2 'M' opens move panel = "
              f"{bool(m7.gizmo_row_boxes(session, 'position'))}")
        shot(session, "B2_end.png")
    finally:
        session.close()
        print(f"{LOG} B2 closed")


def part_c2(args):
    print(f"{LOG} ===== C2: colour chooser dialog =====")
    from harness import export_util
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, _ = m8.wait_arrival(session)
        m7.ensure_maximized(session)
        time.sleep(1.5)
        slots = m8.wait_slots(session)
        hit = next((s for s in slots if s["slot"] == 1), None)
        if not hit or not hit.get("swatch"):
            print(f"{LOG} C2 no slot1 swatch")
            return
        before_rgb = m8.slot_swatch_rgb(session, 1)
        x0, y0, x1, y1 = hit["swatch"]
        sx, sy = (x0 + x1) // 2, (y0 + y1) // 2
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        winutil.real_click_screen(sx, sy)
        dlg = None
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline and not dlg:
            for cls, title, rect, hwnd in m7._visible_toplevels(session.pid):
                if cls == "#32770":
                    dlg = (title, rect, hwnd)
                    break
            time.sleep(0.3)
        if not dlg:
            print(f"{LOG} C2 dialog did not open")
            return
        title, rect, hwnd = dlg
        print(f"{LOG} C2 dlg title={title!r} rect={rect}")
        kids = export_util._children_texts(hwnd)
        print(f"{LOG} C2 {len(kids)} children:")
        for t, r, h in kids[:40]:
            print(f"{LOG}   {t[:36]!r} rect={r}")
        w, h, buf = winutil.capture_window(hwnd)
        import numpy as np
        img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(h, w, 4),
                           cv2.COLOR_BGRA2BGR)
        cv2.imwrite(str(SHOTS / "C2_dlg.png"), img)
        print(f"{LOG} shot -> C2_dlg.png ({w}x{h})")
        # 试点第一个颜色子块（非按钮、有面积的）再点 OK
        colour_kids = [k for k in kids
                       if k[0].strip() and "ok" not in k[0].strip().lower()
                       and "cancel" not in k[0].strip().lower()]
        if colour_kids:
            t, r, h_ = colour_kids[0]
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.user32.SetCursorPos(cx, cy)
            winutil.real_click_screen(cx, cy)
            time.sleep(0.8)
            print(f"{LOG} C2 clicked first colour child {t[:20]!r} @({cx},{cy})")
        for t, r, h_ in kids:
            if t.strip().lower() in ("ok", "确定"):
                cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
                winutil.real_click_screen(cx, cy)
                time.sleep(1.2)
                print(f"{LOG} C2 OK clicked")
                break
        after_rgb = m8.slot_swatch_rgb(session, 1)
        print(f"{LOG} C2 swatch rgb {before_rgb} -> {after_rgb}")
    finally:
        session.close()
        print(f"{LOG} C2 closed")


def part_a2(args):
    print(f"{LOG} ===== A2: title-bar focus + CtrlA =====")
    session = boot_session(args, model=MULTI_PLATE_3MF)
    try:
        ok, _ = m8.wait_arrival(session)
        m7.ensure_maximized(session)
        time.sleep(1.5)
        cands = m7.model_candidates(session)
        if cands:
            sx, sy = m7.client(session, *cands[0])
            winutil.user32.SetCursorPos(sx, sy)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.2)
        img1 = capture_bgr(session)
        # 标题栏授焦：点主窗标题中部（不放焦点到画布，不点任何盘）
        l, t, r, b = winutil.window_rect(session.hwnd)
        winutil.user32.SetCursorPos((l + r) // 2, t + 12)
        time.sleep(0.3)
        winutil.real_click_screen((l + r) // 2, t + 12)
        time.sleep(0.6)
        winutil.user32.keybd_event(0x11, 0, 0, 0)
        winutil.user32.keybd_event(ord("A"), 0, 0, 0)
        time.sleep(0.05)
        winutil.user32.keybd_event(ord("A"), 0, 2, 0)
        winutil.user32.keybd_event(0x11, 0, 2, 0)
        time.sleep(1.5)
        print(f"{LOG} A2 titlebar-focus Ctrl+A info="
              f"{m7.object_info_text(session)[:50]!r}")
        m8.fit_click(session)
        time.sleep(1.5)
        img2 = capture_bgr(session)
        print(f"{LOG} A2 titlebar variant fit diff = "
              f"{m8.viewport_diff(img1, img2):.3%}")
        # 暗块分离复查
        import numpy as np
        img = capture_bgr(session)
        h, w = img.shape[:2]
        x0, y0 = m7.VIEWPORT_X0, 110
        band = img[y0:h - 60, x0:w - 10].astype(int)
        gray = band.mean(axis=2)
        mask = (gray < 150).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        n, _l, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
        big = [(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT],
                int(cents[i][0]) + x0, int(cents[i][1]) + y0)
               for i in range(1, n)
               if stats[i, cv2.CC_STAT_WIDTH] >= 80
               or stats[i, cv2.CC_STAT_HEIGHT] >= 60]
        print(f"{LOG} A2 dark blobs after: {big}")
        shot(session, "A2_end.png")
    finally:
        session.close()
        print(f"{LOG} A2 closed")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=PRUSA_STL)
    args = ap.parse_args()
    for part in (part_b2, part_c2, part_a2):
        try:
            part(args)
        except Exception as exc:  # noqa: BLE001
            print(f"{LOG} {part.__name__} FAILED: {exc!r}")
    print(f"{LOG} ALL PARTS DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
