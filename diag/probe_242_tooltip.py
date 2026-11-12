#!/usr/bin/env python3
# probe_242_tooltip.py — 2.4.2 工具条 tooltip 方位取证
# 悬停到 2.4.1 已知槽位（Add plate 756 / Arrange 844 / Rotate 1108），
# 各拍一张全图 + 打印光标四周 6 个裁剪区的 OCR，定位 tooltip 实际渲染位置。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import cv2
import m7_common as m7
import m8_common as m8
from harness import mix_dialog_util as mdu
from harness import winutil as wu
from m3_common import add_common_args, boot_session

LOG = "[p242t]"


def ocr_crop(img, x0, y0, x1, y1, scale=3):
    h, w = img.shape[:2]
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return ""
    words = mdu.ocr_words_img(crop, scale=scale)
    return " ".join(wd for wd, *_ in words)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(),
                         default_model=HERE / "fixtures" / "Prusa.stl")
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.3%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        # 画布聚焦
        sx, sy = m7.client(session, m7.VIEWPORT_X0 + 60, 700)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(1.0)

        for tag, cx, cy in (("add756", 756, 84), ("arrange844", 844, 84),
                            ("rotate1108", 1108, 84)):
            sx, sy = m7.client(session, cx, cy)
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(2.0)                     # 等 tooltip
            img = m7.capture_bgr(session)
            p = HERE / "artifacts" / f"p242tip_{tag}.png"
            cv2.imwrite(str(p), img)
            zones = {
                "below": (cx - 120, cy + 10, cx + 200, cy + 100),
                "right": (cx + 8, cy - 30, cx + 260, cy + 40),
                "left": (cx - 260, cy - 30, cx - 8, cy + 40),
                "above": (cx - 120, cy - 90, cx + 200, cy - 10),
                "belowR": (cx + 8, cy + 10, cx + 260, cy + 80),
            }
            out = []
            for zn, (a, b, c, d) in zones.items():
                t = ocr_crop(img, a, b, c, d)
                out.append(f"{zn}={t!r}")
            print(f"{LOG} hover ({cx},{cy}) shot={p.name} " + " ".join(out))
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
