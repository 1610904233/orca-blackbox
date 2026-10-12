#!/usr/bin/env python3
# probe_241_gizmo.py — 2.4.1：gizmo 数值框（m7t74 簇 C）到底吃哪种输入。
#
# 现状（2.4.1 基线复跑）：move X 读回 ''、rotate Z 读回 '445559'、scale 停在 '100.00'；
# 同一套 m7_common 在 2.4.0 上绿。本轮把"输入通道"逐条试出来：
#   a) 老通道：真实点击框 → WM_CHAR 发到 (600,400) 处的 canvas 子窗口 → Enter
#   b) WM_CHAR 直接发到**框中心**的最深子窗口
#   c) OS 级真实键盘（keybd_event 扫描码）
#   d) WM_SETTEXT（如果框本身是原生 Edit）
# 每步都读回字段 OCR 文本；同时 dump 面板区域的原生子控件（看框是不是原生 Edit）。
# 只跑 move 面板（一次会话一个 gizmo，PITFALLS：2.4.0 的教训）。
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

_LOG_NAME = "pgizmo.log"


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

from harness import export_util, winutil  # noqa: E402
from harness.anchors import capture_bgr  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pgiz]"
ART = _HERE / "artifacts"
user32 = winutil.user32


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    cv2.imwrite(str(ART / f"pgiz_{name}.png"), img)
    print(f"{LOG} shot -> pgiz_{name}.png")


def panel_children(session, boxes):
    """面板区域内的原生子控件（类名 + 文本 + rect）。"""
    if not boxes:
        return []
    xs = [b[0] for b in boxes]
    ys = [b[1] for b in boxes]
    x0, x1 = min(xs) - 40, max(xs) + 60
    y0, y1 = min(ys) - 30, max(ys) + 30
    sx0, sy0 = m7.client(session, x0, y0)
    sx1, sy1 = m7.client(session, x1, y1)
    out = []
    for t, r, ch in export_util._children_texts(session.hwnd):
        if r[0] >= sx0 - 6 and r[2] <= sx1 + 6 and r[1] >= sy0 - 6 and r[3] <= sy1 + 6:
            out.append((winutil.window_class(ch), t.strip(), r, ch))
    return out


def real_keys(seq, pause=0.12):
    for vk in seq:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.04)
        user32.keybd_event(vk, 0, 2, 0)
        time.sleep(pause)


def read_field(session, label, index):
    """当前该列字段的 OCR 文本（直接用行盒，避免 read_gizmo_field 的轮询）。"""
    boxes = m7.gizmo_row_boxes(session, label)
    if not boxes:
        return "<panel closed>"
    idx = index if index >= 0 else len(boxes) + index
    if not (0 <= idx < len(boxes)):
        return f"<no field {index} of {len(boxes)}>"
    return boxes[idx][2]


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
        if not m7.select_model(session):
            print(f"{LOG} model not selectable")
            return 1
        x, tip = m7.find_slot(session, lambda t: "move" in t)
        print(f"{LOG} move slot x={x} tip={tip!r}")
        if x is None:
            return 1
        m7.click_slot(session, x)
        time.sleep(1.2)
        boxes = m7.gizmo_row_boxes(session, "position")
        print(f"{LOG} position row boxes ({len(boxes)}): {boxes}")
        if not boxes:
            print(f"{LOG} panel not open")
            return 1
        shot("00_panel")
        kids = panel_children(session, boxes)
        print(f"{LOG} panel native children ({len(kids)}):")
        for cls, t, r, ch in kids[:20]:
            print(f"{LOG}   {cls!r} {t[:22]!r} {r} {r[2]-r[0]}x{r[3]-r[1]}")
        box = boxes[0]
        print(f"{LOG} target box (client) = {box}, text={box[2]!r}")
        fx, fy = m7.client(session, box[0], box[1])
        print(f"{LOG} target screen = ({fx},{fy}); WindowFromPoint -> "
              f"{winutil.window_class(winutil.window_from_screen_point(fx, fy))!r}")
        # 1) 聚焦：真实单击
        user32.SetCursorPos(fx, fy)
        time.sleep(0.25)
        winutil.real_click_screen(fx, fy)
        time.sleep(0.8)
        print(f"{LOG} after focus click: {read_field(session, 'position', 0)!r}")
        # a) 老通道：WM_CHAR 到 (600,400) 的 canvas 子窗口
        probe = winutil.client_to_screen(session.hwnd, 600, 400)
        canvas = winutil.deepest_child_at(session.hwnd, *probe) or session.hwnd
        print(f"{LOG} [a] canvas hwnd=0x{canvas:X} class={winutil.window_class(canvas)!r}")
        for ch in ("6", "0"):
            winutil._send_msg(canvas, m7.WM_CHAR, ord(ch), 0)
            time.sleep(0.15)
        print(f"{LOG} [a] after WM_CHAR to canvas: {read_field(session, 'position', 0)!r}")
        user32.SetCursorPos(fx, fy)
        time.sleep(0.25)
        winutil.real_click_screen(fx, fy)          # 重新聚焦 + 全选
        time.sleep(0.5)
        # b) WM_CHAR 到框中心的最深子窗口
        field = winutil.deepest_child_at(session.hwnd, fx, fy) or session.hwnd
        print(f"{LOG} [b] field hwnd=0x{field:X} class={winutil.window_class(field)!r} "
              f"text={winutil.window_title(field)!r}")
        m7.type_into_field(session, box[:2], "60", old_len=6, wake=False, recipe=0)
        print(f"{LOG} [b] after type_into_field(recipe0): {read_field(session, 'position', 0)!r}")
        # c) OS 级真实键盘（全选后输入）
        user32.SetCursorPos(fx, fy)
        time.sleep(0.25)
        winutil.real_click_screen(fx, fy)
        time.sleep(0.5)
        real_keys([0x11, 0x41])                     # Ctrl+A
        time.sleep(0.3)
        real_keys([0x36, 0x30])                     # '6','0'
        time.sleep(0.4)
        print(f"{LOG} [c] after real keyboard: {read_field(session, 'position', 0)!r}")
        real_keys([0x0D])                            # Enter
        time.sleep(1.2)
        print(f"{LOG} [c] after Enter: {read_field(session, 'position', 0)!r}")
        # d) 框本身是不是原生 Edit（决定能不能走 WM_SETTEXT 通道）
        print(f"{LOG} [d] field class = {winutil.window_class(field)!r} "
              f"(Edit => WM_SETTEXT 可用)")
        boxes2 = m7.gizmo_row_boxes(session, "position")
        print(f"{LOG} boxes now ({len(boxes2)}): {[b[2] for b in boxes2]}")
        shot("01_after")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
