#!/usr/bin/env python3
# probe_241_merge_rows.py — 把 Merge with 子菜单的行位标定出来
#
# 目的：2.4.1 的 '...' → Merge with 子菜单行是自绘的，几何外推会偏一行
# （想点第 2 项落到第 1 项）。本探针把光标依次停在若干 y 上，逐一截图子菜单
# 区域并纵向拼一张图 —— 看图上"高亮/光标落在哪一行"，即可标定行位。
#
# 产出：artifacts/m8xMR_rows.png（一张图）
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

from harness import mixing_util, topbar_util, winutil  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pkRows]"
ART = HERE / "artifacts"
user32 = winutil.user32


def screen_bgr():
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    return cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                        cv2.COLOR_BGRA2BGR)


def slot_menu_button(session, slot):
    hit = next((s for s in m8.filament_slots(session) if s["slot"] == slot),
               None)
    if not hit:
        return None
    ch = hit["swatch"]
    cy = (ch[1] + ch[3]) // 2
    best = None
    for _t, c, r, h in mixing_util.children(session.hwnd):
        if c != "Button" or not user32.IsWindowVisible(h):
            continue
        if r[2] > 470 or r[0] < 4:
            continue
        if r[1] - 6 <= cy <= r[3] + 6 and r[0] > ch[2] + 40:
            if best is None or r[0] < best[0][0]:
                best = (r, h)
    return best


def main() -> int:
    import cv2
    import numpy as np
    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    session = boot_session(args, model=None)
    try:
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        m8.wait_slots(session)
        print(f"{LOG} slots={[s['slot'] for s in m8.filament_slots(session)]}")
        btn = slot_menu_button(session, 4)
        print(f"{LOG} slot4 '...' = {btn[0] if btn else None}")
        if not btn:
            return 1
        r, _h = btn
        x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
        user32.SetCursorPos(x, y)
        time.sleep(0.3)
        winutil.real_click_screen(x, y)
        time.sleep(1.2)
        menus = topbar_util.wait_menu_popup(session.pid, timeout_s=4.0)
        print(f"{LOG} menus: {[m[:4] for m in menus]}")
        if not menus:
            return 1
        mrect, mhwnd = menus[0][:4], menus[0][4]
        hmenu = topbar_util.menu_hmenu(mhwnd)
        items = topbar_util.menu_items(hmenu)
        print(f"{LOG} items: {[(i, l) for i, l, _s in items]}")
        idx = next((i for i, l, _s in items if "merge with" in l.lower()), None)
        if idx is None:
            return 1
        topbar_util.hover_row(mrect, len(items), idx)
        sub = topbar_util.wait_submenu(session.pid, {mhwnd}, timeout_s=5.0)
        if not sub:
            print(f"{LOG} no submenu")
            return 1
        srect, shwnd = sub[0], sub[1]
        sub_items = topbar_util.menu_items(sub[2])
        print(f"{LOG} submenu rect={srect} hwnd=0x{shwnd:x} "
              f"items={len(sub_items)}")
        for i, lbl, st in sub_items:
            print(f"{LOG}   [{i}] {lbl!r} state=0x{st:x}")
        l, t, rr, b = srect
        cx = (l + rr) // 2
        rest = (mrect[0] + 20, mrect[1] + 2 + int((idx + 0.5) *
                                                 ((mrect[3] - mrect[1] - 4)
                                                  / max(len(items), 1))))
        shots = []
        # 基线：光标停在父菜单的 'Merge with' 行（子菜单保持打开）
        user32.SetCursorPos(*rest)
        time.sleep(0.6)
        base = screen_bgr()[max(0, t):b, max(0, l):rr]
        shots.append((f"rest@{rest[1]}", base.copy()))
        for dy in range(4, (b - t) - 2, 6):
            user32.SetCursorPos(cx, t + dy)
            time.sleep(0.45)
            shots.append((f"y={t + dy}", screen_bgr()[max(0, t):b,
                                                       max(0, l):rr].copy()))
            print(f"{LOG} shot y={t+dy}")
        user32.SetCursorPos(*rest)
        time.sleep(0.4)
        topbar_util.close_menu_windows(session.pid)
        cells = []
        for label, img in shots:
            big = cv2.resize(img, None, fx=1.7, fy=1.7,
                             interpolation=cv2.INTER_CUBIC)
            lab = np.zeros((26, big.shape[1], 3), np.uint8)
            cv2.putText(lab, label, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 255), 2)
            cells.append(np.vstack([lab, big]))
        grid = np.vstack(cells)
        out = ART / "m8xMR_rows.png"
        cv2.imwrite(str(out), grid)
        print(f"{LOG} wrote {out} {grid.shape}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
