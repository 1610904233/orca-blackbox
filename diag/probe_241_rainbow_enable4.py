#!/usr/bin/env python3
# ⚠️ 结论已被推翻（10-12）：见 probe_241_rainbow_enable.py 头部与 PITFALLS §21.3 ——
#    Rainbow 无需任何人工勾选，它就在 Snapmaker 二级列表里。
# probe_241_rainbow_enable4.py — 另两处入口：Color Mixing 行右侧图标 / 顶栏 Calibration 菜单
#
# 前情：Filament Management 行第一个图标 (337,352) → `Color Mixing Match` 对话框（含 Filament Setup，
# 有 'Snapmaker PLA Full Spectrum @U1'），但没有"配置可选材料"按钮，Confirm 也不落盘。
# 本轮：① 点 Color Mixing 行 (y≈534) 右侧图标（x≈381/395）；② 打开顶栏 Calibration 菜单看有没有
#       "混色品牌/材料配置" 入口。
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

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pk255]"
ART = HERE / "artifacts"
user32 = winutil.user32


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xPF_{name}.png"), img)
    print(f"{LOG} shot -> m8xPF_{name}.png")


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
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def dump_popup(tag, hwnd):
    kids = [(t.strip(), r, winutil.window_class(h)) for t, r, h in export_util._children_texts(hwnd)
            if t.strip()]
    print(f"{LOG} [{tag}] {len(kids)} children:")
    for t, r, c in sorted(kids, key=lambda x: (x[1][1], x[1][0]))[:26]:
        print(f"{LOG}   {t[:46]!r} {r} {c}")
    blob = " ".join(t for t, _r, _c in kids).lower()
    for w in ("rainbow", "spectrum", "brand", "mixing", "色", "混"):
        if w in blob:
            print(f"{LOG} [{tag}] >>> 命中关键词 {w!r}")


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
        # 侧栏 Color Mixing / Filaments 行的图标坐标（来自 1920x1080 截图）
        for tag, x, y in (("filaments_337", 337, 381), ("filaments_361", 361, 381),
                          ("filaments_385", 385, 381), ("filaments_408", 408, 381),
                          ("fm_label_110", 110, 346)):
            before = {t[3] for t in toplevels(session.pid)}
            click_at(x, y)
            shot(f"01_{tag}")
            new = [t for t in toplevels(session.pid) if t[3] not in before
                   and t[0] not in ("tooltips_class32", "SysShadow")]
            print(f"{LOG} --- click {tag} @({x},{y}): {[(t[0], t[1], t[2]) for t in new]}")
            for t in new:
                dump_popup(tag, t[3])
            user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.8)
        # 顶栏 Calibration 菜单
        print(f"{LOG} --- 顶栏 Calibration 菜单")
        click_at(295, 15, 1.2)
        pop = export_util.wait_toplevel(session.pid, lambda c, t, r: c == "#32768", timeout_s=3.0)
        if pop:
            dump_popup("calibration_menu", pop[3])
            shot("02_calibration_menu", pop[2])
            menuitems = []
            try:
                menuitems = [l for _i, l in m7.list_menu(pop[3])]
            except Exception as exc:                              # noqa: BLE001
                menuitems = [f"<{exc!r}>"]
            print(f"{LOG} menu items: {menuitems}")
            user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x1B, 0, 2, 0)
        else:
            print(f"{LOG} Calibration menu did not open")
        time.sleep(0.6)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
