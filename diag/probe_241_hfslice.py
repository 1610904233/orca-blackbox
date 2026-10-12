#!/usr/bin/env python3
# probe_241_hfslice.py — 2.4.1：Nozzle Flow 切到 High Flow 之后点 Slice 到底发生了什么。
#
# 簇 B（m8f/m8g）现象：HF 切换成功后点 Slice ——
#   * 消息级点击 `SendMessageTimeoutW(0x202) did not complete`（×3，每次 3s 超时）
#   * 真实点击后按钮仍 idle（score 1.000）→ "slice click rejected"
# 假设：2.4.1 把"确认切片"提示挪到了**点击切片时**（#125 日志里见过
# 'Confirm slicing' 对话框），于是点击只是弹框、不开始切片；而 m8f 只在
# **切完流量**时查过一次提示（那时还没有）。
# 本探针把它钉死：切 HF → 点 Slice → dump 所有 toplevels（找 #32770 / 文本）
# → 截图 → 若真有确认框，点它的第一个按钮看切片是否开始（为修法取证）。
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

_LOG_NAME = "phf.log"


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

LOG = "[phf]"
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
        img = img[max(0, rect[1] - 10):rect[3] + 10, max(0, rect[0] - 10):rect[2] + 10]
    cv2.imwrite(str(ART / f"phf_{name}.png"), img)
    print(f"{LOG} shot -> phf_{name}.png")


def tops(pid):
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid:
            return True
        vis = bool(user32.IsWindowVisible(hwnd))
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


def dump_all(tag):
    print(f"{LOG} --- toplevels ({tag}) ---")
    for cls, title, rect, hwnd, vis in tops(session.pid):
        mark = '' if vis else 'HIDDEN'
        print(f"{LOG}   {cls!r} {title!r} {rect} {mark}")
        if cls == "#32770" and vis:
            kids = [k.strip() for k, _r, _h in export_util._children_texts(hwnd) if k.strip()]
            print(f"{LOG}     kids({len(kids)}): {kids[:20]}")


def slice_button():
    from m2_slice_chain import RESOURCE
    img = capture_bgr(session)
    score, bx, by, bw, bh = match(img, str(RESOURCE / "slice_plate_button.png"))
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
        added = m7.op_add_primitive(session, "cube")
        print(f"{LOG} cube added: {added}")
        time.sleep(1.0)
        ok_p = pp.switch_process_preset(session, PROC_HF)
        print(f"{LOG} process preset HF-TEST: {ok_p}")
        m7.dismiss_transfer_dialog(session)
        got = m8.switch_flow_combo(session, "High Flow")
        print(f"{LOG} flow -> {got!r}")
        time.sleep(2.0)
        print(f"{LOG} nozzle reads: {m8.nozzle_reads(session)!r}")
        score, box = slice_button()
        print(f"{LOG} slice button template: score={score:.3f} box={box}")
        bx, by, bw, bh = box
        cx, cy = m7.client(session, bx + bw // 2, by + bh // 2)
        print(f"{LOG} slice button screen point ({cx},{cy}); WindowFromPoint -> "
              f"{winutil.window_class(winutil.window_from_screen_point(cx, cy))!r}")
        dump_all("before click")
        shot("00_before", (bx - 20, by - 20, bx + bw + 200, by + bh + 20))
        # 1) 消息级点击
        print(f"{LOG} -- msg click --")
        winutil.msg_click_screen(cx, cy, session.hwnd)
        time.sleep(3.5)
        score2, _ = slice_button()
        print(f"{LOG} after msg click: idle-template score={score2:.3f}")
        dump_all("after msg click")
        # 2) 真实点击
        print(f"{LOG} -- real click --")
        user32.SetCursorPos(cx, cy)
        time.sleep(0.3)
        winutil.real_click_screen(cx, cy)
        time.sleep(3.5)
        score3, _ = slice_button()
        print(f"{LOG} after real click: idle-template score={score3:.3f}")
        dump_all("after real click")
        shot("01_after_click")
        # 3) 若有确认框：读文本 + 点第一个按钮
        dlgs = [t for t in tops(session.pid) if t[0] == "#32770" and t[4]]
        for cls, title, rect, hwnd, _vis in dlgs:
            kids = [(k.strip(), r, h) for k, r, h in export_util._children_texts(hwnd) if k.strip()]
            print(f"{LOG} dialog {title!r} {rect}: {[k for k, _r, _h in kids][:20]}")
            shot("02_dialog", rect)
            btns = [(k, r, h) for k, r, h in kids
                    if k.lower() in ("ok", "yes", "confirm", "确定", "确认", "continue")
                    or "confirm" in k.lower() or "ok" == k.lower()]
            print(f"{LOG}   candidate buttons: {[(k, r) for k, r, _h in btns]}")
            if btns:
                k, r, h = btns[0]
                bx2, by2 = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
                print(f"{LOG}   clicking {k!r} @({bx2},{by2})")
                user32.SetCursorPos(bx2, by2)
                time.sleep(0.3)
                winutil.real_click_screen(bx2, by2)
                time.sleep(4.0)
                score4, _ = slice_button()
                print(f"{LOG} after dialog confirm: idle-template score={score4:.3f}")
                dump_all("after dialog confirm")
                shot("03_after_confirm")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
