#!/usr/bin/env python3
# probe_241_arrange.py — 全盘整理（Arrange all objects）的入口与效果
#
# 背景（10-20 测试方指出）：#158 的"模型整理"看不出真的整理了。本探针把两条
# 入口都试一遍，并用**稳定测量**（去掉 UI 杂散 blob、按位置排序）判定：
#   入口①：顶栏 Arrange 图标 → 弹出面板（Spacing/[Arrange]/[Reset]）→ Arrange 按钮
#   入口②：盘面空白右键菜单里的 'Arrange' 行
#   入口③：快捷键 'A'
# 产出：logs + 取证帧（打印触发 shot_archive 的 L 帧）
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkArr]"
M1 = HERE / "fixtures" / "Prusa.stl"
M2 = HERE / "fixtures" / "cube20.stl"


def blobs(session, min_area=400):
    import cv2
    import numpy as np
    import m7_common as m7
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    h, w = img.shape[:2]
    x0, y0 = m7.VIEWPORT_X0 + 10, 110
    band = img[y0:h - 60, x0:w - 10].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _l, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        a = int(stats[i, cv2.CC_STAT_AREA])
        bw, bh = int(stats[i, 2]), int(stats[i, 3])
        if a < min_area or not (0.3 <= bw / max(bh, 1) <= 4.0):
            continue
        if int(cents[i][0]) + x0 > 1450:
            continue
        out.append((int(cents[i][0]) + x0, int(cents[i][1]) + y0, a))
    return sorted(out)


def moved(a, b):
    m = 0
    for p, q in zip(a, b):
        m = max(m, abs(q[0] - p[0]), abs(q[1] - p[1]))
    return m


def main() -> int:
    import m7_common as m7
    import m8_common as m8
    import m8x_152 as base
    import m8x_158 as c158
    from m3_common import add_common_args
    from harness import winutil as _wu

    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    args.model = None
    session = base.m7_boot(args, model=None)
    try:
        m8.wait_arrival(session, timeout_s=60)
        m7.ensure_maximized(session)
        # 导入两个模型
        for path in (M1, M2):
            if not c158.import_model(session, path):
                print(f"{LOG} import dispatch failed {path.name}")
                return 1
            time.sleep(6.0)
        # 弄乱：把新模型拖到左下（Move 工具 → 拖本体）
        m7.click_slot(session, 1064)
        time.sleep(1.5)
        live = m7.find_centroid(session)
        print(f"{LOG} pre-drag blobs={blobs(session)} live={live}")
        if live:
            m7.real_drag_screen(session, live, (live[0] - 220, live[1] + 160))
            time.sleep(2.0)
        pre = blobs(session)
        print(f"{LOG} BEFORE (messy): {pre}")

        # 入口③ 快捷键 A
        _wu.user32.SetCursorPos(*m7.client(session, m7.VIEWPORT_X0 + 60, 700))
        time.sleep(0.2)
        _wu.real_click_screen(*m7.client(session, m7.VIEWPORT_X0 + 60, 700))
        time.sleep(0.6)
        for vk in (0x41,):
            _wu.user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.06)
            _wu.user32.keybd_event(vk, 0, 2, 0)
        time.sleep(3.5)
        after_a = blobs(session)
        print(f"{LOG} after 'A': {after_a} moved={moved(pre, after_a)}")

        # 入口① 工具栏图标 + 面板 [Arrange]
        print(f"{LOG} LABEL-PANEL-OPEN")
        m7.click_slot(session, 844)
        time.sleep(2.0)
        kids = [(t.strip(), r) for t, r, _h in
                __import__("harness").export_util._children_texts(session.hwnd)
                if t.strip() and r[1] > 100 and r[1] < 400]
        print(f"{LOG} panel children: {kids[:14]}")
        _wu.user32.SetCursorPos(*m7.client(session, 892, 300))
        time.sleep(0.25)
        _wu.real_click_screen(*m7.client(session, 892, 300))
        time.sleep(3.5)
        after_panel = blobs(session)
        print(f"{LOG} after panel Arrange: {after_panel} "
              f"moved={moved(pre, after_panel)}")

        # 入口② 盘面右键菜单的 Arrange 行
        menu = m7.open_context_menu(session, where="bed")
        rows = [l for _i, l in m7.list_menu(menu[1])] if menu else []
        print(f"{LOG} bed menu rows: {rows}")
        if menu and any("arrange" in r.lower() for r in rows):
            m7.click_menu_row(session, menu[0], menu[1], "arrange")
            time.sleep(3.5)
            after_menu = blobs(session)
            print(f"{LOG} after menu Arrange: {after_menu} "
                  f"moved={moved(pre, after_menu)}")
        else:
            if menu:
                m7.dismiss_menus(session)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
