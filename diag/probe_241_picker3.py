#!/usr/bin/env python3
# probe_241_picker3.py — 2.4.1 选择框第三轮：找"用户预设"分组（我们的 - STD-TEST 包在哪）
#
# 前两轮已确认:
#   * 槽位行的 16x25 Button 打开一级列表：'------ System presets ------' + Snapmaker(✓)/Generic >/
#     Aliz >/…/eSUN > + '------ Add/Remove filament ------'；
#   * 点了厂商行会展开二级耗材列表（Snapmaker 层 = 8 项置顶 + 其余字典序）；
#   * 真实滚轮有效、消息级无效；打开时按"回显"定位。
#
# 本轮:
#   Q1 一级列表里除了 System presets 还有没有别的分组（User presets / Project presets / 自定义）？
#   Q2 我们的用户预设（Snapmaker PLA SnapSpeed @U1 - STD-TEST 等）在哪一层/哪个分组？
#   Q3 二级列表里点一支耗材会不会真的选中（组合框文本变化）—— 用无害的一支试（选完再选回原值）。
#
# 只读为主：Q3 会做一次真实选择，随后立刻选回原耗材（原值从测试前的组合框读）。
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

from harness import export_util, mix_dialog_util as mdu, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pk243]"
ART = HERE / "artifacts"
user32 = winutil.user32


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xP3_{name}.png"), img)
    print(f"{LOG} shot -> m8xP3_{name}.png")


def click_at(x, y, pause=1.2):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def ocr_rect(rect, tag, psm=6):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    x0, y0, x1, y1 = [int(v) for v in rect]
    crop = img[max(0, y0):y1, max(0, x0):x1]
    words = mdu.ocr_words_img(crop, scale=2, psm=psm)
    lines = {}
    for t, x, y, w, h in words:
        key = next((k for k in lines if abs(k - y) <= 12), y)
        lines.setdefault(key, []).append((x + x0, y + y0, t))
    rows = [(k, " ".join(t for _x, _y, t in sorted(lines[k])),
             min(x for x, _y, _t in lines[k])) for k in sorted(lines)]
    print(f"{LOG} --- {tag}: {len(rows)} lines ---")
    for y, txt, x in rows:
        print(f"{LOG}   y={y:4d} x={x:4d} {txt[:86]}")
    return rows


def open_picker(session, row_button_rect):
    """点槽位行的 16x25 Button 打开一级列表。"""
    cx, cy = (row_button_rect[0] + row_button_rect[2]) // 2, (row_button_rect[1] + row_button_rect[3]) // 2
    click_at(cx, cy, 1.8)
    return export_util.wait_popup(session.pid, timeout_s=4.0)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        slots = m8.wait_slots(session)
        hit = next((s for s in slots if s["slot"] == 2), None)
        text, rect, ch = hit["combo"]
        orig = m8.combo_text(ch)
        picker = hit.get("picker")
        print(f"{LOG} slot2 combo={orig!r} combo_rect={rect} picker_rect={picker}")

        pop = open_picker(session, picker)
        if not pop:
            print(f"{LOG} level-1 popup did not open")
            return 1
        pr = pop[2]
        print(f"{LOG} level-1 popup rect={pr}")
        shot("01_level1", pr)
        rows = ocr_rect(pr, "level-1 (as opened)")

        # Q1: 向上滚，看有没有别的分组标题
        for i in range(10):
            winutil.real_wheel_screen(pr[0] + 40, (pr[1] + pr[3]) // 2, 3)
            time.sleep(0.12)
        time.sleep(0.6)
        shot("02_level1_top", pr)
        ocr_rect(pr, "level-1 (scrolled up)")

        # Q2/Q3: 点 Generic -> 二级，找 ABS；再试着点一支（随后恢复）
        gen = next((y for y, t, _x in rows if t.strip().lower().startswith("generic")), None)
        if gen is None:
            rows2 = ocr_rect(pr, "level-1 re-read")
            gen = next((y for y, t, _x in rows2 if t.strip().lower().startswith("generic")), None)
        if gen is None:
            print(f"{LOG} 'Generic' row not found in level-1")
        else:
            print(f"{LOG} clicking 'Generic' at y={gen}")
            click_at(pr[0] + 60, gen + 8, 1.5)
            shot("03_generic_level2", pr)
            l2 = ocr_rect(pr, "Generic level-2")
            abs_row = next((y for y, t, _x in l2 if t.strip().upper().startswith("ABS")), None)
            print(f"{LOG} ABS row in Generic level-2: y={abs_row}")
            if abs_row is not None:
                click_at(pr[0] + 60, abs_row + 8, 1.8)
                now = m8.combo_text(ch)
                print(f"{LOG} combo after clicking Generic>ABS: {now!r}")
                shot("04_selected_generic_abs")
        # Q2: 用户预设分组 —— 一级里滚到最底再看
        pop2 = open_picker(session, picker)
        if pop2:
            pr2 = pop2[2]
            for i in range(40):
                winutil.real_wheel_screen(pr2[0] + 40, (pr2[1] + pr2[3]) // 2, -3)
                time.sleep(0.10)
            time.sleep(0.8)
            shot("05_level1_bottom", pr2)
            rowsb = ocr_rect(pr2, "level-1 (bottom)")
            hits = [t for _y, t, _x in rowsb if 'test' in t.lower() or 'user' in t.lower()
                    or 'project' in t.lower() or 'custom' in t.lower() or '自定义' in t]
            print(f"{LOG} bottom-level sections/candidates: {hits}")
            # 逐个点可疑的分组/厂商行，找我们的 - STD-TEST
            for want in ("User presets", "Custom", "自定义", "Project presets"):
                row = next((y for y, t, _x in rowsb if want.lower() in t.lower()), None)
                if row is None:
                    continue
                print(f"{LOG} clicking {want!r} at y={row}")
                click_at(pr2[0] + 60, row + 8, 1.5)
                shot(f"06_{want.replace(' ', '_')}", pr2)
                rows3 = ocr_rect(pr2, f"{want} level-2")
                hit2 = [t for _y, t, _x in rows3 if 'test' in t.lower()]
                print(f"{LOG}   rows mentioning test: {hit2}")
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.6)
        print(f"{LOG} slot2 combo after probe: {m8.combo_text(ch)!r} (orig {orig!r})")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
