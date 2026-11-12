#!/usr/bin/env python3
# probe_242_pencil.py — #198 真入口定位：盘名标签旁铅笔（用户截图「编辑当前盘名」）
# 1) 加盘后 OCR 盘面左上带（y 380-560, x 900-1400）找 'Untitled'/plate name 标签
# 2) 悬停标签右侧读 tooltip（期望含 'edit plate' / 'plate name'）
# 3) 点击铅笔 -> 观察是否出现就地编辑框（Edit 控件/可见变化）
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
import m8x_194 as c194
from harness import export_util, mix_dialog_util as mdu, winutil
from m3_common import add_common_args, boot_session

LOG = "[p242pen]"
STL = HERE / "fixtures" / "Prusa.stl"


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = boot_session(args, model=STL)
    try:
        m7.ensure_maximized(session)
        time.sleep(6.0)
        print(f"{LOG} add plate: {c194.add_plate_verified(session)}")
        time.sleep(2.5)
        found = []
        for (y0, y1, x0, x1, sc) in ((380, 560, 900, 1400, 4),
                                     (400, 520, 940, 1300, 5),
                                     (300, 420, 900, 1400, 4)):
            img = m7.capture_bgr(session)
            band = img[y0:y1, x0:x1]
            if band.size == 0:
                continue
            ws = mdu.ocr_words_img(band, scale=sc)
            print(f"{LOG} band {(y0, y1, x0, x1, sc)}: "
                  f"{[(w[0], w[1] + x0, w[2] + y0) for w in ws][:14]}")
            for w in ws:
                t = w[0].lower()
                if any(k in t for k in ("untitled", "plate", "name")):
                    px = x0 + w[1] + w[3] + 14
                    py = y0 + w[2] + w[4] // 2
                    tip = c194.tooltip_right(session, px, py, dwell_s=1.5)
                    print(f"{LOG} hover right of {w[0]!r} @({px},{py}) "
                          f"tip={tip!r}")
                    found.append((w[0], px, py, tip))
        # 对第一个 tip 含 plate/name 的点做点击，看是否出现编辑框
        hit = next((f for f in found if f[3] and
                    ("plate" in f[3].lower() or "name" in f[3].lower())), None)
        if hit:
            _t, px, py, tip = hit
            print(f"{LOG} click pencil candidate @({px},{py}) tip={tip!r}")
            for dx in (0, -10, 10, -18, 18):
                sx, sy = m7.client(session, px + dx, py)
                winutil.user32.SetCursorPos(sx, sy)
                time.sleep(0.25)
                winutil.real_click_screen(sx, sy)
                time.sleep(1.2)
                edits = [(r, h) for _t2, r, h in
                         export_util._children_texts(session.hwnd)
                         if winutil.window_class(h) == "Edit"
                         and winutil.user32.IsWindowVisible(h)]
                dialogs = [t for c, t, r, h in m7._visible_toplevels(session.pid)
                           if c == "#32770"]
                print(f"{LOG} click dx={dx}: visible Edits={edits[:4]} "
                      f"dialogs={dialogs}")
                if dialogs or edits:
                    break
        else:
            print(f"{LOG} no pencil candidate found")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
