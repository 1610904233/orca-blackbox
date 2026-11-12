#!/usr/bin/env python3
# probe_242_slot1menu.py — slot 1 picker 菜单行取证（m8x_123 C 步前置）
# open_preset_editor 几何点第一行 (menu.top+12) 对 slot 2 是 Edit，
# slot 1 打开的 #32770 没有 Edit 控件 → 菜单行内容不同。本探针：
# 打开 slot 1 的 picker 菜单 → PrintWindow+OCR 各行 → 逐行点击 →
# dump 弹出的 #32770 标题+子控件，找出哪行是 Edit/Material settings。
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
from harness import export_util, winutil
from m3_common import MIXED_3MF, add_common_args, boot_session

LOG = "[p242s1]"
SHOTS = HERE / "artifacts" / "shots" / "p242s1"


def dump_dlg(session, tag):
    dlg = export_util.wait_toplevel(session.pid, lambda c, t, r: c == "#32770",
                                    timeout_s=5.0)
    if not dlg:
        print(f"{LOG} {tag}: no #32770")
        return None
    kids = export_util._children_texts(dlg[3])
    edits = [(t, r) for t, r, h in kids if winutil.window_class(h) == "Edit"]
    print(f"{LOG} {tag}: title={dlg[1]!r} rect={dlg[2]} children={len(kids)} "
          f"edits={len(edits)}")
    for t, r, h in kids[:14]:
        print(f"{LOG}   {winutil.window_class(h)!r:12} {t[:36]!r} {r}")
    return dlg


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    SHOTS.mkdir(parents=True, exist_ok=True)
    session = boot_session(args, model=args.model)
    user32 = winutil.user32
    try:
        ok, _ = m8.wait_arrival(session)
        m7.ensure_maximized(session)
        time.sleep(1.5)
        slots = m8.wait_slots(session)
        hit = next((s for s in slots if s["slot"] == 1), None)
        if not hit or not hit.get("picker"):
            print(f"{LOG} slot1 picker missing")
            return 1
        r = hit["picker"]
        for row_i, dy in enumerate((12, 30, 48, 66)):
            # 打开菜单
            sx, sy = winutil.client_to_screen(
                session.hwnd, (r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            user32.SetCursorPos(sx, sy)
            time.sleep(0.25)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.2)
            menu = export_util.wait_toplevel(
                session.pid, lambda c, t, rr: c == "#32768", timeout_s=4.0)
            if not menu:
                print(f"{LOG} row{row_i}: menu did not open")
                continue
            mrect = menu[2]
            # PrintWindow 菜单截图 + OCR 行
            try:
                w, h, buf = winutil.capture_window(menu[3])
                import numpy as np
                img = cv2.cvtColor(
                    np.frombuffer(buf, np.uint8).reshape(h, w, 4),
                    cv2.COLOR_BGRA2BGR)
                cv2.imwrite(str(SHOTS / f"menu_row{row_i}.png"), img)
                from harness import mix_dialog_util as mdu
                words = mdu.ocr_words_img(img, scale=3)
                print(f"{LOG} row{row_i} menu {w}x{h} ocr="
                      f"{[wd[0] for wd in words]}")
            except Exception as exc:
                print(f"{LOG} row{row_i} menu capture failed: {exc!r}")
            # 点该行
            mx, my = mrect[0] + 40, mrect[1] + dy
            user32.SetCursorPos(mx, my)
            time.sleep(0.2)
            winutil.real_click_screen(mx, my)
            time.sleep(1.8)
            dlg = dump_dlg(session, f"row{row_i}(@y+{dy})")
            if dlg and any(winutil.window_class(h) == "Edit"
                           for _t, _r, h in
                           export_util._children_texts(dlg[3])):
                print(f"{LOG} row{row_i} IS the edit entry")
                break
            # 关掉弹出的对话框再试下一行
            if dlg:
                winutil.user32.SetCursorPos(dlg[2][2] - 14, dlg[2][1] + 12)
                winutil.real_click_screen(dlg[2][2] - 14, dlg[2][1] + 12)
                time.sleep(1.0)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
