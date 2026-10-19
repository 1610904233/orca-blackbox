#!/usr/bin/env python3
# probe_241_filament_row_merge.py — 物理耗材行的 Options('...') 入口 + 合并菜单原文
#
# 背景（测试方 10-16 口径）：#152 的「耗材合并」不是 Filaments 标题行的删除桶，
# 而是**耗材行右侧的 '...'**，菜单里选「合并到 x 号耗材」。本探针把入口与菜单
# 原文（含子菜单目标列表）读出来，供用例使用。
#
# 产出：diag/probe_241_row_merge.log + artifacts/m8xRM_*.png
# 安全：只点物理行上的 Button（不碰标题行的删除桶）；菜单只读、只 hover，不点菜单项。
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

from harness import export_util, mixing_util, topbar_util, winutil  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402

LOG = "[pkRM]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
user32 = winutil.user32


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xRM_{name}.png"), img)
    print(f"{LOG} shot -> m8xRM_{name}.png  rect={rect}")


def click_at(x, y, pause=1.4):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def toplevels(pid):
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(160)
        user32.GetWindowTextW(hwnd, txt, 160)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((cls.value, txt.value,
                    (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def dump_menu(tag, hwnd):
    hmenu = topbar_util.menu_hmenu(hwnd)
    items = topbar_util.menu_items(hmenu)
    print(f"{LOG} [{tag}] menu items ({len(items)}):")
    for i, lbl, st in items:
        print(f"{LOG}   [{i}] {lbl!r} state=0x{st:x}")
    return items


def esc(n=1, pause=0.8):
    for _ in range(n):
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.06)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.4)
    time.sleep(pause)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        m8.wait_slots(session)

        # --- 1) 侧栏子控件 census：耗材行上有哪些 Button ---
        band = mdu.sidebar_rows_band(session)
        print(f"{LOG} rows band (top,bottom,x0) = {band}")
        slots = m8.filament_slots(session)
        print(f"{LOG} filament_slots ({len(slots)}):")
        for s in slots:
            print(f"{LOG}   slot={s['slot']} swatch={s['swatch']} "
                  f"picker={s['picker']}")
        title = mdu._sidebar_title_row(session, "Filaments")
        print(f"{LOG} Filaments title row = {title}")
        btns = []
        for t, c, r, h in mixing_util.children(session.hwnd):
            if c != "Button" or not user32.IsWindowVisible(h):
                continue
            if r[2] > 470 or r[0] < 4:
                continue
            btns.append((r, h, t))
        btns.sort(key=lambda b: (b[0][1], b[0][0]))
        print(f"{LOG} sidebar Buttons ({len(btns)}) [rect / hwnd / text]:")
        for r, h, t in btns:
            print(f"{LOG}   {r}  0x{h:x}  {t!r}")
        # 2x2 网格：每个槽单元右缘一个 16x25 Button（= 该槽的 '...' 入口）
        entry = {}
        for s in slots:
            ch = s["swatch"]
            cy = (ch[1] + ch[3]) // 2
            same = sorted([(r, h) for r, h, _t in btns
                           if r[1] - 6 <= cy <= r[3] + 6
                           and r[0] > ch[2] + 40], key=lambda b: b[0][0])
            if same:
                entry[s["slot"]] = same[0]
            print(f"{LOG} slot {s['slot']} row-buttons {[b[0] for b in same]}")
        print(f"{LOG} per-slot '...' entries: "
              f"{ {k: v[0] for k, v in entry.items()} }")
        if slots:
            shot("01_sidebar", (4, slots[0]["swatch"][1] - 26, 470,
                                slots[-1]["swatch"][3] + 30))

        # --- 2) 逐一点各槽的 '...'，读菜单原文 ---
        for slot in sorted(entry, reverse=True):
            r, h = entry[slot]
            x = (r[0] + r[2]) // 2
            y = (r[1] + r[3]) // 2
            before = {t[3] for t in toplevels(session.pid)}
            print(f"{LOG} --- slot {slot} '...' rect={r} @({x},{y}) "
                  f"hwnd=0x{h:x}")
            click_at(x, y)
            shot(f"02_slot{slot}_click")
            new = [t for t in toplevels(session.pid)
                   if t[3] not in before
                   and t[0] not in ("tooltips_class32", "SysShadow")]
            print(f"{LOG}   new toplevels: "
                  f"{[(t[0], t[1], t[2]) for t in new]}")
            for t in new:
                if t[0] == "#32768":
                    items = dump_menu(f"slot{slot}", t[3])
                    sub_idx = topbar_util.find_item(
                        topbar_util.menu_hmenu(t[3]), "merge")
                    if sub_idx is not None:
                        topbar_util.hover_row(t[2], len(items), sub_idx)
                        sub = topbar_util.wait_submenu(session.pid, {t[3]},
                                                       timeout_s=5.0)
                        if sub:
                            sub_items = topbar_util.menu_items(sub[2])
                            print(f"{LOG}   >>> SUBMENU: "
                                  f"{[i[1] for i in sub_items]}")
                            shot(f"03_slot{slot}_submenu", sub[0])
                            for i2, lbl2, st2 in sub_items:
                                print(f"{LOG}     sub[{i2}] {lbl2!r} "
                                      f"state=0x{st2:x}")
                elif t[0] == "#32770":
                    kids = [(tt.strip(), rr, winutil.window_class(hh))
                            for tt, rr, hh in export_util._children_texts(t[3])
                            if tt.strip()]
                    print(f"{LOG}   dialog children: {kids[:14]}")
                    shot(f"03_slot{slot}_dialog", t[2])
            esc(2)
            print(f"{LOG}   after ESC: slots="
                  f"{mdu.physical_filament_count(session)}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
