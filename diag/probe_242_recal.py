#!/usr/bin/env python3
# probe_242_recal.py — 242d 测试侧标定取证（m8a / m8x_152 / m8x_153 三段）
#
# A 段（m8a, snapmates_nonmixed.3mf）：
#   A1 #18 复刻：点选模型 -> fit_click -> blob 增长（Fit 按钮活性）
#   A2 #19 取证：Ctrl+A 前后 object_info/blob 对比（select-all 到底选没选），
#      fit 前后帧差；对比「先点模型再 Ctrl+A」变体
#   A3 #16 取证：dump 全部暗色连通块（宽/高/位置）——多盘床渲染几何
# B 段（m8x_152, Prusa.stl）：scale 输入 120 -> ESC×2 后：
#   dump 顶层窗口/OCR 词/候选点/信息面板，逐候选点选 + 截图
# C 段（m8x_153, Prusa.stl）：slot1 chip 真实点击后 6s 内
#   dump 所有新顶层窗口/菜单 + 截图；slot2 对照
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
from harness import topbar_util, winutil
from m1_minimal_loop import capture_bgr
from m3_common import (MULTI_PLATE_3MF, PRUSA_STL, add_common_args,
                       boot_session)

LOG = "[p242rc]"
SHOTS = HERE / "artifacts" / "shots" / "p242rc"


def shot(session, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(SHOTS / name), capture_bgr(session))
    print(f"{LOG} shot -> {name}")


def dump_windows(session, tag):
    wins = m7._visible_toplevels(session.pid)
    print(f"{LOG} {tag}: {len(wins)} toplevels")
    for cls, title, rect, hwnd in wins[:10]:
        print(f"{LOG}   {cls!r} {title[:40]!r} {rect}")


def part_a(args):
    print(f"{LOG} ===== A: m8a (multi-plate) =====")
    session = boot_session(args, model=MULTI_PLATE_3MF)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} A arrived={ok} frac={frac:.3%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        # A1: #18 复刻
        cands = m7.model_candidates(session)
        print(f"{LOG} A1 candidates={cands[:4]}")
        if cands:
            sx, sy = m7.client(session, *cands[0])
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.2)
        img0 = capture_bgr(session)
        b0 = m8.blob_stats(img0)
        m8.fit_click(session)
        b1 = m8.blob_stats(capture_bgr(session))
        grew = b0 and b1 and b1["area"] >= b0["area"] * 1.5
        print(f"{LOG} A1 #18 replica: blob {b0 and b0['area']} -> "
              f"{b1 and b1['area']} grew={bool(grew)}")
        # A2: #19 取证 — Ctrl+A 是否真的选中
        info_sel = m7.object_selected(session)
        topbar_util._focus_click(session)
        topbar_util._send_accel([0x11], ord("A"))
        time.sleep(1.5)
        info_after = m7.object_info_text(session)
        print(f"{LOG} A2 after Ctrl+A: selected_before={info_sel} "
              f"info={info_after[:50]!r}")
        img1 = capture_bgr(session)
        m8.fit_click(session)
        time.sleep(1.5)
        img2 = capture_bgr(session)
        print(f"{LOG} A2 fit diff after select-all = "
              f"{m8.viewport_diff(img1, img2):.3%}")
        # 变体：先点模型（真选）再 Ctrl+A 再 fit
        if cands:
            sx, sy = m7.client(session, *cands[0])
            winutil.user32.SetCursorPos(sx, sy)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.0)
        topbar_util._send_accel([0x11], ord("A"))
        time.sleep(1.5)
        img1b = capture_bgr(session)
        m8.fit_click(session)
        time.sleep(1.5)
        img2b = capture_bgr(session)
        print(f"{LOG} A2 variant (click-then-CtrlA) fit diff = "
              f"{m8.viewport_diff(img1b, img2b):.3%}")
        # A3: 暗块 dump（#16 检测取证）
        import numpy as np
        img = capture_bgr(session)
        h, w = img.shape[:2]
        x0, y0 = m7.VIEWPORT_X0, 110
        band = img[y0:h - 60, x0:w - 10].astype(int)
        gray = band.mean(axis=2)
        mask = (gray < 150).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        n, _l, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
        print(f"{LOG} A3 dark blobs (w>=80 or h>=60):")
        for i in range(1, n):
            bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            if bw >= 80 or bh >= 60:
                print(f"{LOG}   w={bw} h={bh} at "
                      f"({int(cents[i][0]) + x0},{int(cents[i][1]) + y0}) "
                      f"area={stats[i, cv2.CC_STAT_AREA]}")
        shot(session, "A_after.png")
    finally:
        session.close()
        print(f"{LOG} A closed")


def part_b(args):
    print(f"{LOG} ===== B: m8x_152 (scale+ESC then select) =====")
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} B arrived={ok} frac={frac:.3%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        pt = m7.select_object_strict(session)
        print(f"{LOG} B pre-scale select pt={pt}")
        m7.click_slot(session, 1152)
        time.sleep(1.5)
        boxes = m7.gizmo_row_boxes(session, "scale")
        print(f"{LOG} B scale grid={boxes[:3]}")
        if boxes:
            m7.type_into_field(session, boxes[0][:2], "120",
                               old_len=4, recipe=0)
            _b, txt = m7.read_gizmo_field(session, "scale", 0, expect="120",
                                          timeout_s=6.0)
            print(f"{LOG} B scale typed -> {txt!r}")
        # ESC x2 close (case flow)
        for _ in range(2):
            hwnd = winutil.deepest_child_at(
                session.hwnd, *winutil.client_to_screen(session.hwnd, 600, 400))
            winutil._send_msg(hwnd or session.hwnd, 0x0100, 0x1B, 0)
            time.sleep(0.15)
            winutil._send_msg(hwnd or session.hwnd, 0x0102, 0x1B, 0)
            time.sleep(0.8)
        print(f"{LOG} B panel open after ESC = "
              f"{bool(m7.gizmo_row_boxes(session, 'scale'))}")
        dump_windows(session, "B post-ESC")
        info = m7.object_info_text(session)
        print(f"{LOG} B info panel text={info[:60]!r}")
        cands = m7.model_candidates(session)
        print(f"{LOG} B candidates={cands}")
        shot(session, "B_postESC.png")
        for cx, cy in cands[:4]:
            sx, sy = m7.client(session, cx, cy)
            winutil.user32.SetCursorPos(sx, sy)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.0)
            print(f"{LOG} B click ({cx},{cy}) -> selected="
                  f"{m7.object_selected(session)}")
            if m7.object_selected(session):
                break
        shot(session, "B_end.png")
    finally:
        session.close()
        print(f"{LOG} B closed")


def part_c(args):
    print(f"{LOG} ===== C: m8x_153 (slot1 chip) =====")
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} C arrived={ok}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        slots = m8.wait_slots(session)
        for s in slots:
            print(f"{LOG} C slot{s['slot']} swatch={s.get('swatch')} "
                  f"combo={s.get('combo') and s['combo'][0]!r}")
        for slot in (1, 2):
            hit = next((s for s in slots if s["slot"] == slot), None)
            if not hit or not hit.get("swatch"):
                print(f"{LOG} C slot{slot} no swatch")
                continue
            x0, y0, x1, y1 = hit["swatch"]
            sx, sy = (x0 + x1) // 2, (y0 + y1) // 2
            before = {h for _c, _t, _r, h in m7._visible_toplevels(session.pid)}
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            winutil.real_click_screen(sx, sy)
            time.sleep(3.0)
            after = m7._visible_toplevels(session.pid)
            new = [w for w in after if w[3] not in before]
            print(f"{LOG} C slot{slot} chip @({sx},{sy}) new windows: "
                  f"{[(c, t[:30]) for c, t, _r, _h in new]}")
            print(f"{LOG} C slot{slot} menus: {topbar_util._enum_menu_windows(session.pid)}")
            shot(session, f"C_slot{slot}_chip.png")
            # 关掉可能的弹层，避免污染下一轮
            for cls, title, rect, hwnd in new:
                user32 = __import__("ctypes").WinDLL("user32")
                user32.SendMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            time.sleep(1.0)
    finally:
        session.close()
        print(f"{LOG} C closed")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=PRUSA_STL)
    args = ap.parse_args()
    for part in (part_a, part_b, part_c):
        try:
            part(args)
        except Exception as exc:  # noqa: BLE001
            print(f"{LOG} {part.__name__} FAILED: {exc!r}")
    print(f"{LOG} ALL PARTS DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
