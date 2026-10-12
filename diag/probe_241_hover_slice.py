#!/usr/bin/env python3
# probe_241_hover_slice.py — "悬停切片按钮"这条路到底是什么行为？
#
# 测试方 10-12 口径：喷嘴高流量/标准混用时，**旧版悬停切片单盘按钮会弹
# 「标准模式 / 自定义模式」的框**；2.4.1 不再弹那个框，而是**直接弹耗材分组弹窗**。
# 本探针把三条路径分开测（都只看、不确认）：
#   A) 只悬停（SetCursorPos 停在切片按钮上 ≥3s，不点击）→ dump 所有可见 toplevels
#   B) 移到别处再移回来（看是否"每次悬停都弹"）
#   C) 再点击一次（与 A/B 对照；用户在旧版看到的是悬停框，本轮 m8f/m8g 钉的是点击框）
# 每个阶段都打印 dialog 的子控件文本（找 Standard/Custom/mode/分组 字样）+ 截图。
import argparse
import ctypes
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE)); sys.path.insert(0, str(_HERE / "tests"))
for _g in sorted((_HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

_LOG_NAME = ("phover240.log" if any("2.4.0" in a for a in sys.argv)
             else "phover241.log")      # A/B 跑两次时日志不要互相覆盖（实测踩过）


def _tee_log(name):
    import sys as _s
    p = Path(__file__).resolve().parents[1] / "artifacts" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fh = open(p, "w", encoding="utf-8", errors="replace")

    class _T:
        def write(self, s):
            fh.write(s)
            fh.flush()
            try:
                if _s.__stdout__ is not None:
                    _s.__stdout__.write(s)
            except Exception:                                  # noqa: BLE001
                pass

        def flush(self):
            fh.flush()

    _s.stdout = _T()
    _s.stderr = _T()


_tee_log(_LOG_NAME)

from harness import export_util, process_panel as pp, winutil  # noqa: E402
from harness.anchors import capture_bgr, match  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[phov]"
ART = _HERE / "artifacts"
user32 = winutil.user32
PROC_HF = "0.20mm Standard @Snapmaker U1 (0.4 nozzle) - HF-TEST"


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 12):rect[3] + 12, max(0, rect[0] - 12):rect[2] + 12]
    cv2.imwrite(str(ART / f"phover_{name}.png"), img)
    print(f"{LOG} shot -> phover_{name}.png")


def tops(visible_only=True):
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != session.pid:
            return True
        vis = bool(user32.IsWindowVisible(hwnd))
        if visible_only and not vis:
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(200)
        user32.GetWindowTextW(hwnd, txt, 200)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd, vis))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def dump(tag):
    print(f"{LOG} --- toplevels ({tag}) ---")
    for cls, title, rect, hwnd, vis in tops():
        extra = ''
        if cls in ("#32770", "wxWindowNR", "#32768"):
            kids = [k.strip() for k, _r, _h in export_util._children_texts(hwnd) if k.strip()]
            hit = [k for k in kids if any(w in k.lower() for w in
                                          ("standard", "custom", "mode", "nozzle",
                                           "group", "confirm", "cancel"))]
            extra = f'  kids={kids[:14]}'
            if hit:
                extra += f'  KEY={hit}'
        print(f"{LOG}   {cls!r} {title!r} {rect}{extra}")


def slice_button():
    from m2_slice_chain import RESOURCE
    score, bx, by, bw, bh = match(capture_bgr(session),
                                  str(RESOURCE / "slice_plate_button.png"))
    return score, (bx, by, bw, bh)


def main() -> int:
    global session
    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    args.model = None
    session = boot_session(args, model=None)
    try:
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        print(f"{LOG} cube added: {m7.op_add_primitive(session, 'cube')}")
        time.sleep(1.0)
        print(f"{LOG} process preset HF-TEST: {pp.switch_process_preset(session, PROC_HF)}")
        m7.dismiss_transfer_dialog(session)
        got = m8.switch_flow_combo(session, "High Flow")
        print(f"{LOG} flow -> {got!r}")
        time.sleep(2.0)
        print(f"{LOG} nozzle reads: {m8.nozzle_reads(session)!r}")
        score, box = slice_button()
        print(f"{LOG} slice button: score={score:.3f} box={box}")
        bx, by, bw, bh = box
        cx, cy = m7.client(session, bx + bw // 2, by + bh // 2)
        print(f"{LOG} slice button screen point ({cx},{cy})")
        dump("baseline (cursor elsewhere)")
        # A) 只悬停
        print(f"{LOG} == A: hover only (no click), 3.5s ==")
        user32.SetCursorPos(cx, cy)
        for i in range(7):
            time.sleep(0.5)
            new = [t for t in tops() if t[0] == "#32770" or t[0] == "wxWindowNR"]
            if new:
                print(f"{LOG}   t+{(i + 1) * 0.5:.1f}s: {[(t[0], t[1]) for t in new]}")
        dump("A after hover")
        shot("A_hover")
        # B) 移开再回来
        print(f"{LOG} == B: move away, then hover again ==")
        user32.SetCursorPos(cx - 400, cy + 300)
        time.sleep(1.5)
        dump("B after move-away")
        user32.SetCursorPos(cx, cy)
        time.sleep(2.5)
        dump("B after re-hover")
        # C) 点击
        print(f"{LOG} == C: click ==")
        winutil.real_click_screen(cx, cy)
        time.sleep(2.5)
        dump("C after click")
        shot("C_click")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
