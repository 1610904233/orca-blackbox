#!/usr/bin/env python3
# probe_241_rotate.py — 2.4.1：Rotate 面板 absolute Z 字段为什么提交不进去。
#
# m7t74 现状（修了空行偏移后）：move X / scale 都 PASS，只剩
#   `rotate Z commits 45: FAIL (now '445559')`（各个 recipe 读回 '4'/'44515'/'445559'）。
# 本轮把 rotate 面板单独摊开看：
#   1) 面板网格 + 原生子控件 + 截图；
#   2) 绝对行 Z 格子：单击 → 逐字发 WM_CHAR（沿用老通道 = canvas）→ 每步读**整行** + 截图；
#   3) 若读回异常，再试：双击、Ctrl+A 全选后输入、以及"清空后输入"。
import argparse
import sys
import time
from pathlib import Path

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE)); sys.path.insert(0, str(_HERE / "tests"))
for _g in sorted((_HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

_LOG_NAME = "prot.log"


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

LOG = "[prot]"
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
    cv2.imwrite(str(ART / f"prot_{name}.png"), img)
    print(f"{LOG} shot -> prot_{name}.png")


def grid(tag):
    boxes = m7.gizmo_row_boxes(session, "rotate")
    print(f"{LOG} [{tag}] rotate grid ({len(boxes)}): {boxes}")
    return boxes


def row_read(boxes):
    return [(b[2]) for b in boxes]


def click_at(box, double=False):
    fx, fy = m7.client(session, box[0], box[1])
    user32.SetCursorPos(fx, fy)
    time.sleep(0.25)
    winutil.real_click_screen(fx, fy)
    if double:
        time.sleep(0.1)
        winutil.real_click_screen(fx, fy)
    time.sleep(0.6)
    return fx, fy


def send_chars_canvas(chars):
    probe = winutil.client_to_screen(session.hwnd, 600, 400)
    hwnd = winutil.deepest_child_at(session.hwnd, *probe) or session.hwnd
    for ch in chars:
        winutil._send_msg(hwnd, m7.WM_CHAR, ord(ch), 0)
        time.sleep(0.15)
    return hwnd


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
        x, tip = m7.find_slot(session, lambda t: "rotate" in t)
        print(f"{LOG} rotate slot x={x} tip={tip!r}")
        m7.click_slot(session, x)
        time.sleep(1.2)
        boxes = grid("open")
        if not boxes:
            print(f"{LOG} rotate panel not open")
            return 1
        xs = [b[0] for b in boxes]
        ys = [b[1] for b in boxes]
        shot("00_panel", (min(xs) - 60, min(ys) - 40, max(xs) + 60, max(ys) + 40))
        kids = [(winutil.window_class(h), t.strip(), r)
                for t, r, h in export_util._children_texts(session.hwnd)
                if r[0] > min(xs) - 120 and r[2] < max(xs) + 160
                and r[1] > min(ys) - 80 and r[3] < max(ys) + 80]
        print(f"{LOG} panel native children ({len(kids)}):")
        for cls, t, r in kids[:16]:
            print(f"{LOG}   {cls!r} {t[:20]!r} {r} {r[2]-r[0]}x{r[3]-r[1]}")
        # 绝对行 = 第二行（y 更大）；取该行第 3 列（Z）
        rows_y = sorted({b[1] for b in boxes})
        print(f"{LOG} rows_y={rows_y}")
        # 逐个格子试：哪个格子吃输入？（rotate 有两行：上=relative，下=absolute）
        for i, box in enumerate(boxes):
            print(f"{LOG} === cell {i} {box} ===")
            click_at(box)
            before = row_read(grid(f"cell{i}-click"))
            send_chars_canvas("45")
            time.sleep(0.4)
            after = row_read(grid(f"cell{i}-typed"))
            print(f"{LOG} cell{i} before={before} after={after}")
            # 复位：全选 + 输入 '0' 尝试恢复（失败也无所谓，最后会关掉面板）
            click_at(box)
            send_chars_canvas("\b\b\b\b\b\b")
            send_chars_canvas("0")
            time.sleep(0.3)
        shot("05_allcells")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
