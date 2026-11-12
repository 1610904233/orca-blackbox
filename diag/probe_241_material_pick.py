#!/usr/bin/env python3
# ⚠️ 前提已作废（10-12）：Rainbow 不需要任何「材料勾选」就出现在耗材栏里
#    （PITFALLS §21.3）。本文件只记录「材料勾选对话框」这条路的探索过程。
# probe_241_material_pick.py — 2.4.1：耗材管理行最右图标 → 材料勾选对话框 → 勾 PLA Rainbow
#
# 测试方 10-12 截图口径：耗材管理行最右侧的小图标打开一个**材料勾选对话框**
# （中文界面：「系统材料 / 自建材料」两个 tab + 材料类型/供应商筛选 + 每支材料一个勾选框，
#  红框标出 `Snapmaker PLA Rainbow`）。勾上后该材料才会出现在耗材栏的选择框里。
#
# 本轮：
#   1) 快照 datadir → 点耗材管理行最右图标（英文界面下位置略有差异，试几个 x）
#   2) dump 对话框（含勾选按钮）→ 找 Rainbow 的勾选框并（若未勾）勾上 → 确定
#   3) 再快照 datadir → 打印变化文件（判断能否用播种替代 UI 勾选）
#   4) 回耗材栏选择框：Snapmaker 层找 'Rainbow'
import argparse
import ctypes
import os
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pk256]"
ART = HERE / "artifacts"
DATADIR = Path(r"C:\coil\orca-blackbox\artifacts\m3_profile")
user32 = winutil.user32


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGR2BGRA)
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xPG_{name}.png"), img)
    print(f"{LOG} shot -> m8xPG_{name}.png")


def snap():
    out = {}
    for root, _d, files in os.walk(DATADIR):
        for f in files:
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
                out[p] = (st.st_size, int(st.st_mtime))
            except OSError:
                pass
    return out


def click_at(x, y, pause=1.4):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def kids(hwnd):
    return [(t.strip(), r, winutil.window_class(h), h)
            for t, r, h in export_util._children_texts(hwnd) if t.strip()]


def main() -> int:
    global session
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        m8.wait_slots(session)
        before = snap()
        # 耗材管理行的最右图标（英文界面：'Filament Management' 行 y≈346；试几个 x）
        for x in (421, 415, 408, 430):
            before_tops = {t[3] for t in _tops(session.pid)}
            click_at(x, 346)
            shot(f"01_click_{x}")
            new = [t for t in _tops(session.pid) if t[3] not in before_tops
                   and t[0] not in ("tooltips_class32", "SysShadow")]
            print(f"{LOG} click ({x},346) -> {[(t[0], t[1], t[2]) for t in new]}")
            if new:
                dlg = new[0]
                shot("02_dialog", dlg[2])
                rows = kids(dlg[3])
                print(f"{LOG} dialog children ({len(rows)}):")
                for t, r, c, _h in sorted(rows, key=lambda z: (z[1][1], z[1][0]))[:40]:
                    print(f"{LOG}   {t[:44]!r} {r} {c}")
                rb = next(((t, r, c, h) for t, r, c, h in rows
                           if "rainbow" in t.lower() or "spectrum" in t.lower()), None)
                print(f"{LOG} Rainbow row: {rb[:3] if rb else None}")
                # 勾选框通常是同行左侧的 Button（20x20 左右）
                if rb:
                    _t, r, _c, _h = rb
                    boxes = [(t2, r2, c2, h2) for t2, r2, c2, h2 in rows
                             if c2 == "Button" and abs((r2[1] + r2[3]) // 2 - (r[1] + r[3]) // 2) <= 12]
                    print(f"{LOG} checkbox candidates on that row: {[(t2, r2) for t2, r2, _c, _h in boxes]}")
                    if boxes:
                        bx = boxes[0][1]
                        print(f"{LOG} >>> click checkbox {bx}")
                        click_at((bx[0] + bx[2]) // 2, (bx[1] + bx[3]) // 2, 1.2)
                        shot("03_after_tick", dlg[2])
                # 确定
                okb = next(((t, r, h) for t, r, c, h in rows
                            if t in ("OK", "确定", "Confirm", "Apply")), None)
                if okb:
                    print(f"{LOG} >>> click {okb[0]!r}")
                    click_at((okb[1][0] + okb[1][2]) // 2, (okb[1][1] + okb[1][3]) // 2, 1.6)
                else:
                    user32.keybd_event(0x1B, 0, 0, 0)
                    time.sleep(0.05)
                    user32.keybd_event(0x1B, 0, 2, 0)
                    time.sleep(0.8)
                break
        after = snap()
        changed = [p for p in after if p not in before or after[p] != before[p]]
        print(f"{LOG} datadir changed: {len(changed)}")
        for p in changed[:12]:
            print(f"{LOG}   {p.replace(str(DATADIR), '')} {after[p]}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


def _tops(pid):
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
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
