#!/usr/bin/env python3
# ⚠️ 结论已被推翻（10-12）：PLA Rainbow **本来就在** Snapmaker 二级列表里，
#    不需要「耗材管理 → 混色品牌 → 配置可选择的材料」的任何勾选。真相见
#    probe_241_picker_scan2.py（弹层开在鼠标落点、光标压着 Generic 行 → 扫错了分支）
#    与 PITFALLS §21.3。本文件只作「哪些路走不通」的记录保留。
# probe_241_rainbow_enable.py — 2.4.1：找"耗材管理 → 混色品牌 → 配置可选材料"里的 PLA Rainbow 勾选
#
# 测试方 10-12 口径：`PLA Rainbow` 默认**不在**耗材栏里，需要在**耗材管理**里
# 「混色品牌」右侧的「配置可选择的材料」按钮里**勾选**才出现。
#
# 本轮：
#   1) 启动夹具 → 记录 datadir 快照（路径/大小/时间）；
#   2) 打开耗材管理（侧栏 Filament Management 行右侧的图标）→ 逐层 dump 出现的界面（OCR + 子控件）；
#   3) 找 '混色品牌'/'Color Mixing'/'配置'/'selectable' 这类入口 → 打开材料清单 → 找 Rainbow 的勾选框；
#   4) 勾上 → 关闭 → 再开槽位选择框，确认 Snapmaker 列表里出现 Rainbow / Full Spectrum；
#   5) 重新快照 datadir → 打印变化的文件（判断能否改由播种配置完成）。
#
# 只做一次勾选（可逆：再点一次即取消）；不保存工程。
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

from harness import export_util, mix_dialog_util as mdu, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pk252]"
ART = HERE / "artifacts"
DATADIR = Path(r"C:\coil\orca-blackbox\artifacts\m3_profile")
user32 = winutil.user32


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xPC_{name}.png"), img)
    print(f"{LOG} shot -> m8xPC_{name}.png")


def snap_datadir():
    out = {}
    for root, _dirs, files in os.walk(DATADIR):
        for f in files:
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
                out[p] = (st.st_size, int(st.st_mtime))
            except OSError:
                pass
    return out


def click_at(x, y, pause=1.3):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def kids_all(parent):
    out = []

    def cb(hwnd, _lp):
        buf = ctypes.create_unicode_buffer(160)
        user32.GetWindowTextW(hwnd, buf, 160)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((buf.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumChildWindows(ctypes.c_void_p(parent), export_util.WNDENUMPROC(cb), 0)
    return out


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
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def dump_ui(tag, root=None, max_lines=40):
    print(f"{LOG} === {tag} ===")
    if root is None:
        for cls, txt, r, hwnd in toplevels(session.pid):
            if cls in ("tooltips_class32", "SysShadow"):
                continue
            print(f"{LOG}  TOP {cls!r} {txt!r} {r}")
        return
    rows = [(t.strip(), r, winutil.window_class(h)) for t, r, h in kids_all(root) if t.strip()]
    for t, r, c in sorted(rows, key=lambda x: (x[1][1], x[1][0]))[:max_lines]:
        print(f"{LOG}  {t[:60]!r} {r} {c}")
    print(f"{LOG}  rows={len(rows)}")


def click_child_text(needle, root=None, contains=True, off=(0, 0)):
    w = root if root is not None else session.hwnd
    for t, r, h in kids_all(w):
        ts = t.strip()
        if not ts:
            continue
        if (needle.lower() in ts.lower()) if contains else (ts.lower() == needle.lower()):
            x, y = (r[0] + r[2]) // 2 + off[0], (r[1] + r[3]) // 2 + off[1]
            print(f"{LOG} click {ts[:32]!r} @({x},{y})")
            click_at(x, y)
            return h
    print(f"{LOG} click {needle!r}: not found in {w}")
    return None


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
        before = snap_datadir()
        print(f"{LOG} datadir snapshot: {len(before)} files")
        shot("00_before")

        # 1) 找耗材管理那一行右侧的图标（Filament Management 行）
        row = next(((t, r) for t, r, _h in kids_all(session.hwnd)
                    if t.strip().startswith("Filament Management")), None)
        print(f"{LOG} Filament Management row: {row}")
        icons = [(t, r, winutil.window_class(h)) for t, r, h in kids_all(session.hwnd)
                 if row and r[0] > row[1][1] - 5 and abs(r[1] - row[1][1]) <= 24
                 and (r[2] - r[0]) <= 30 and (r[3] - r[1]) <= 30]
        print(f"{LOG} icons on that row: {[(r, c) for _t, r, c in icons]}")
        if not icons:
            print(f"{LOG} no icons found — dumping sidebar band")
            dump_ui("sidebar band", session.hwnd)
        for i, (_t, r, c) in enumerate(sorted(icons, key=lambda x: x[1][0])):
            print(f"{LOG} --- click icon #{i} {c} {r}")
            click_at((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, 1.5)
            shot(f"01_icon{i}")
            for cls, txt, rr, hwnd in toplevels(session.pid):
                if cls in ("tooltips_class32", "SysShadow", "wxWindowNR") and txt != "panel":
                    continue
                if hwnd == session.hwnd:
                    continue
                print(f"{LOG}   popup {cls!r} {txt!r} {rr}")
                dump_ui(f"popup from icon#{i}", hwnd, max_lines=28)
                blob = " ".join(t for t, _r, _h in kids_all(hwnd))
                if "rainbow" in blob.lower() or "brand" in blob.lower() or "混色" in blob:
                    print(f"{LOG}   >>> 这个弹层可能就是要找的（含 rainbow/brand）")
            user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.8)
        after = snap_datadir()
        changed = [p for p in after if p not in before or after[p] != before[p]]
        print(f"{LOG} datadir changed files: {len(changed)}")
        for p in changed[:12]:
            print(f"{LOG}   {p.replace(str(DATADIR), '')}  {after[p]}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
