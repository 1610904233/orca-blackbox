#!/usr/bin/env python3
# probe_242_plateicons.py — 盘侧工具栏图标列标定（#196 排列零件 /
# #197 锁定当前板 / #198 编辑盘名 的入口）
# 沿盘左上斜边图标条带 hover 扫描（右向 OCR 读 tooltip），输出图标语义→坐标。
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
import m8x_194 as c194
from m3_common import PRUSA_STL, add_common_args, boot_session

LOG = "[p242pi]"


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=PRUSA_STL)
    args = ap.parse_args()
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.2%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        # 双盘布局下才出现完整盘侧图标条带（#194/#195 都先加盘；单盘时
        # 扫描 189 点全空——11-12 实测）
        if not c194.add_plate_verified(session):
            print(f"{LOG} add-plate FAILED")
            return 1
        time.sleep(2.5)
        found = {}
        # 沿已标定的图标高度带（#194 remove y~237 / #195 orient y~241 /
        # plate10 lock y~290）逐 x 扫；tooltip 需要 ≥1s 停留（0.45s 实测全空）
        pts = [(1390, 230), (1382, 234), (1398, 226)]  # 乱码图标重点复读
        print(f"{LOG} scan {len(pts)} points")
        for x, y in pts:
            tip = c194.tooltip_right(session, x, y, dwell_s=1.0)
            if tip:
                key = tip.strip().lower()[:40]
                if key not in found or (x, y) != found[key][:2]:
                    if key not in found:
                        found[key] = (x, y, tip.strip())
                        print(f"{LOG} TOOLTIP @({x},{y}): {tip.strip()!r}")
        # 打开 'Customize current plate' 菜单（编辑盘名可能在其中）
        found.setdefault("customize current plate", (1490, 302, "Customize current plate"))
        if "customize current plate" in found:
            cx, cy = found["customize current plate"][0], found["customize current plate"][1]
            m7.winutil.user32.SetCursorPos(*m7.client(session, cx, cy))
            time.sleep(0.3)
            m7.winutil.real_click_screen(*m7.client(session, cx, cy))
            time.sleep(1.5)
            menus = m7.topbar_util._enum_menu_windows(session.pid)
            print(f"{LOG} customize menus={len(menus)}")
            if menus:
                hmenu = m7.topbar_util.menu_hmenu(menus[0][4])
                print(f"{LOG} customize rows="
                      f"{[l for _i, l in m7.list_menu(hmenu)]}")
                m7.dismiss_menus(session)
            else:
                print(f"{LOG} all toplevels after customize click:")
                for cls2, t2, r2, h2 in m7._visible_toplevels(session.pid):
                    kids2 = [k[0][:16] for k in
                             m7.export_util._children_texts(h2)
                             if k[0].strip()][:8]
                    print(f"{LOG}   {cls2!r} {t2[:30]!r} {r2} {kids2}")
                # OCR 整个屏幕看下拉内容
                import m8_common as _m8
                from harness import mix_dialog_util as _mdu
                img = _m8.capture_bgr(session) if hasattr(_m8, 'capture_bgr') else None
                if img is not None:
                    words = _mdu.ocr_words_img(img, scale=2)
                    print(f"{LOG}   screen OCR: {' | '.join(w[0] for w in words[:60])}")
        print(f"{LOG} ===== map =====")
        for k, v in sorted(found.items(), key=lambda kv: kv[1][0]):
            print(f"{LOG} {v[2]!r} @({v[0]},{v[1]})")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
