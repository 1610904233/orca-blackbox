#!/usr/bin/env python3
# probe_242_platedlg.py — Plate Settings 对话框全量控件 dump（找可见 OK/Cancel）
# 已知：wm_command(1) 无效、两个 Button 子控件重叠且无文本、OCR 无 OK 标签。
# 本探针打印所有子控件的 class/text/rect/可见性，重点看底部按钮带，
# 并尝试点击底部带中最右/最左的可见子控件，观察对话框是否关闭。
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
from harness import export_util, winutil
from m3_common import add_common_args, boot_session

LOG = "[p242pd]"
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
        sx, sy = m7.client(session, 1486, 303)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        winutil.real_click_screen(sx, sy)
        time.sleep(2.5)
        dlg = None
        for cls, t, r, h in m7._visible_toplevels(session.pid):
            if cls == "#32770" and "plate setting" in (t or "").lower():
                dlg = (cls, t, r, h)
                break
        print(f"{LOG} dialog={dlg and (dlg[1], dlg[2])}")
        if not dlg:
            return 1
        kids = export_util._children_texts(dlg[3])
        print(f"{LOG} children ({len(kids)}):")
        for t, r, h in kids:
            print(f"{LOG}   {winutil.window_class(h)!r:14} {t[:26]!r} {r} "
                  f"vis={bool(winutil.user32.IsWindowVisible(h))} "
                  f"en={bool(winutil.user32.IsWindowEnabled(h))}")
        # 底部按钮带（dialog 下沿 60px 内）的可见子控件，按 x 排序后逐个试点击
        dl, dt, dr, db = dlg[2]
        bottom = [(t, r, h) for t, r, h in kids
                  if r[1] >= db - 70
                  and winutil.user32.IsWindowVisible(h)
                  and (r[2] - r[0]) >= 8 and (r[3] - r[1]) >= 8]
        bottom.sort(key=lambda k: k[1][0])
        print(f"{LOG} bottom-band candidates:")
        for t, r, h in bottom:
            print(f"{LOG}   {winutil.window_class(h)!r} {t[:20]!r} {r}")
        # 从右往左点第一个（OK 一般在右，Cancel 左；wx 惯例是 OK 左/右不定，
        # 这里先点最右，失败再点最左——观察哪个关闭对话框）
        for label, pick in (("rightmost", bottom[-1] if bottom else None),
                            ("leftmost", bottom[0] if bottom else None)):
            if pick is None:
                continue
            t, r, h = pick
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            print(f"{LOG} click {label} {t[:20]!r} @({cx},{cy})")
            winutil.msg_click_screen(cx, cy, dlg[3])
            time.sleep(1.5)
            if not winutil.user32.IsWindowVisible(dlg[3]):
                print(f"{LOG} dialog CLOSED by {label}")
                return 0
        print(f"{LOG} dialog still open after both")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
