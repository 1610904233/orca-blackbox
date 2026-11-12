#!/usr/bin/env python3
# probe_242_objlist3.py — 工艺(Process) 面板「对象(Objects)」标签页：
# 对象树行点击选中 + 行右侧「耗材」下拉（用户指引：工艺→对象→盘下模型→
# 右侧下拉选耗材）。全按钮面，绕开画布。
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
from harness import export_util, mix_dialog_util as mdu, winutil
from m1_minimal_loop import capture_bgr
from m3_common import PRUSA_STL, add_common_args, boot_session

LOG = "[p242ol3]"
WM_CLOSE = 0x0010


def dismiss_strays(session):
    for _ in range(8):
        dlg = next(((c, t, r, h) for c, t, r, h in
                    m7._visible_toplevels(session.pid) if c == "#32770"), None)
        if not dlg:
            return
        print(f"{LOG} dismiss {dlg[1]!r}")
        winutil.user32.SendMessageW(dlg[3], WM_CLOSE, 0, 0)
        time.sleep(1.0)


def ocr_band(session, y0, y1, x0=0, x1=430, scale=3):
    img = capture_bgr(session)
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return []
    words = mdu.ocr_words_img(crop, scale=scale)
    return [(w[0], w[1] + x0, w[2] + y0, w[3], w[4]) for w in words]


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=PRUSA_STL)
    args = ap.parse_args()
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, _ = m8.wait_arrival(session)
        m7.ensure_maximized(session)
        time.sleep(1.5)
        dismiss_strays(session)
        # 1) 找 Process/Advanced 文字行，OCR 该行拿 'Objects'
        rows = export_util._children_texts(session.hwnd)
        proc = next(((t, r) for t, r, h in rows if t.strip() == "Process"), None)
        adv = next(((t, r) for t, r, h in rows if t.strip() == "Advanced"), None)
        print(f"{LOG} process={proc and proc[1]} adv={adv and adv[1]}")
        if not (proc and adv):
            return 1
        y0, y1 = proc[1][1] - 8, proc[1][3] + 8
        band = ocr_band(session, y0, y1)
        print(f"{LOG} tab band OCR: {[(w[0], w[1], w[2]) for w in band]}")
        objw = next((w for w in band if "bject" in w[0].lower()), None)
        if objw:
            cx = objw[1] + objw[3] // 2
            cy = objw[2] + objw[4] // 2
        else:
            cx = (proc[1][2] + adv[1][0]) // 2 + 12
            cy = (y0 + y1) // 2
        print(f"{LOG} click Objects tab @({cx},{cy})")
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.3)
        winutil.real_click_screen(cx, cy)
        time.sleep(1.5)
        # 2) 点 Plate 1 节点展开树，再 OCR 找模型行
        words = ocr_band(session, y1 + 2, 800)
        plate = next((w for w in words if w[0].lower() == "plate"), None)
        if plate:
            px, py = plate[1] + plate[3] // 2, plate[2] + plate[4] // 2
            print(f"{LOG} toggle Plate node @({px},{py})")
            winutil.user32.SetCursorPos(px, py)
            time.sleep(0.3)
            winutil.real_click_screen(px, py)
            time.sleep(1.2)
        words = ocr_band(session, y1 + 2, 800, scale=4)
        print(f"{LOG} panel OCR ({len(words)}):")
        for w in words[:36]:
            print(f"{LOG}   {w[0]!r} @({w[1]},{w[2]})")
        row = next((w for w in words if any(k in w[0].lower() for k in
                                            ("untitled", "prusa", "cube"))),
                   None)
        if not row:
            # 退路：Plate 行下方 40~90px 的任意词 = 模型行
            if plate:
                below = [w for w in words
                         if 40 < w[2] - plate[2] < 110 and w[1] > 40]
                print(f"{LOG} fallback rows: {[(w[0], w[1], w[2]) for w in below[:6]]}")
                row = below[0] if below else None
        if not row:
            print(f"{LOG} no object row in OCR")
            return 1
        rx = row[1] + row[3] // 2
        ry = row[2] + row[4] // 2
        print(f"{LOG} click object row {row[0]!r} @({rx},{ry})")
        winutil.user32.SetCursorPos(rx, ry)
        time.sleep(0.3)
        winutil.real_click_screen(rx, ry)
        time.sleep(1.2)
        print(f"{LOG} selected = {m7.object_selected(session)}")
        # 3) dump 该行右侧/附近的控件（找耗材下拉 ComboBox）
        kids = export_util._children_texts(session.hwnd)
        near = [(t, r, h) for t, r, h in kids
                if r[0] < 430 and r[1] > y1 and r[1] < 800]
        print(f"{LOG} sidebar controls near objects panel ({len(near)}):")
        for t, r, h in near[:30]:
            print(f"{LOG}   {winutil.window_class(h)!r:14} {t[:24]!r} {r}")
        # 4) 行右键 -> 是否有 Change Filament
        winutil.user32.SetCursorPos(rx, ry)
        time.sleep(0.2)
        winutil.real_right_click_screen(rx, ry)
        time.sleep(1.2)
        menus = m7.topbar_util._enum_menu_windows(session.pid)
        print(f"{LOG} row right-click menus={len(menus)}")
        if menus:
            hmenu = m7.topbar_util.menu_hmenu(menus[0][4])
            print(f"{LOG} menu rows={[l for _i, l in m7.list_menu(hmenu)]}")
        m7.dismiss_menus(session)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
