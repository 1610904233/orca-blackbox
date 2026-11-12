#!/usr/bin/env python3
# probe_241_plate2.py — 盘操作面标定（#186 添加新盘 / #194 移除当前板 /
# #197 锁定当前板 / #198 编辑盘名称）
#
# 要回答三件事：
#   1) 工具栏「Add plate」按钮点击后，画布是否变为**空白新盘**（= 新盘被选中）；
#   2) 盘角序号标签（'01'/'02'…）能否 OCR —— 作为盘数量的观测面；
#   3) 底部盘列表**右键**是否弹出盘菜单（移除/锁定/编辑名称）。
import argparse
import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPlate2]"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"


def plate_badge(session):
    """盘角序号标签的 OCR（右下角 1500..1560 x 660..710 一带）。"""
    import cv2
    import numpy as np
    from harness import mix_dialog_util as mdu
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    crop = img[650:730, 1480:1580]
    if crop.size == 0:
        return ""
    big = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    words = mdu.ocr_words_img(big, scale=4, psm=6)
    txt = " ".join(w[0] for w in words)
    return txt.strip()


def main() -> int:
    import m7_common as m7
    import m8_common as m8
    import m8x_152 as base
    from m3_common import add_common_args
    from harness import topbar_util
    import m8x_158 as c158

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = base.m7_boot(args, model=STL)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        print(f"{LOG} badge before: {plate_badge(session)!r} "
              f"frac={m7.model_colored_frac(session):.3%} "
              f"objs={c158.object_blobs(session)}")

        # 1) 工具栏「Add plate」
        x, tip = m7.find_slot(session, lambda t: "add plate" in t)
        print(f"{LOG} add-plate slot @{x} tip={tip!r}")
        if x is not None:
            m7.click_slot(session, x)
            time.sleep(3.0)
            print(f"{LOG} AFTER add plate: frac={m7.model_colored_frac(session):.3%} "
                  f"badge={plate_badge(session)!r} "
                  f"objs={c158.object_blobs(session)}")
            print(f"{LOG} LABEL-AFTER-ADDPLATE")
            time.sleep(0.4)

        # 2) 底部盘列表右键（试几个点）
        for pt in ((760, 1000), (860, 1000), (960, 1000), (700, 1000)):
            before = {t[3] for t in
                      [(c, txt, r, h) for c, txt, r, h in
                       __import__("harness").mixing_util.toplevel(session.pid)]}
            from harness import winutil as _wu
            sx, sy = m7.client(session, *pt)
            _wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            _wu.real_right_click_screen(sx, sy)
            deadline = time.monotonic() + 2.5
            found = None
            while time.monotonic() < deadline:
                for mrect in topbar_util._enum_menu_windows(session.pid):
                    found = mrect
                    break
                if found:
                    break
                time.sleep(0.25)
            if found:
                hmenu = topbar_util.menu_hmenu(found[4])
                print(f"{LOG} plate right-click @{pt}: "
                      f"{[l for _i, l in m7.list_menu(hmenu)]}")
                m7.dismiss_menus(session)
            else:
                print(f"{LOG} plate right-click @{pt}: no menu")
        # 3) 在新盘上导入一个模型，验证"可向新盘添加对象"
        c158.import_model(session, CUBE)
        time.sleep(8.0)
        print(f"{LOG} after import on new plate: "
              f"frac={m7.model_colored_frac(session):.3%} "
              f"info={m7.object_info_text(session)[:50]!r}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
