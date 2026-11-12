#!/usr/bin/env python3
# probe_242_f5_frames.py — F-5 复核：242d 上混色夹具切片+预览两帧取证
# m2_slice_chain 的红是「预览彩色占比/切片前占比 = 1.87x < 2x 门」，
# 但 m2 是老用例、无归档器，没有帧证据。本探针补拍：
#   A 帧 = 模型到达后（未切片）；B 帧 = 切片完成 + 切到 Preview 后。
# 另打印两帧的彩色占比，复算比值。截图存 artifacts/shots/p242f5/。
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
from harness import winutil
from harness.anchors import has_colored_content
from m1_minimal_loop import capture_bgr
from m2_slice_chain import click_slice_start, wait_slicing_done
from m3_common import MIXED_3MF, add_common_args, boot_session

LOG = "[p242f5]"
OUT = HERE / "artifacts" / "shots" / "p242f5"


def click_preview_tab(session):
    from harness.anchors import match
    img = capture_bgr(session)
    for name in ("tab_preview_inactive.png", "tab_preview_active.png"):
        score, x, y, w, h = match(img, name)
        if score >= 0.85:
            sx, sy = m7.client(session, x + w // 2, y + h // 2)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            winutil.real_click_screen(sx, sy)
            time.sleep(2.0)
            return True
    print(f"{LOG} preview tab not found")
    return False


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.3%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        imgA = capture_bgr(session)
        cv2.imwrite(str(OUT / "A_model.png"), imgA)
        fracA = has_colored_content(imgA)
        print(f"{LOG} A model frac={fracA:.3%}")

        if not click_slice_start(session):
            print(f"{LOG} slice click failed")
            return 1
        done, _ = wait_slicing_done(session, timeout_s=300)
        print(f"{LOG} sliced={done}")
        click_preview_tab(session)
        time.sleep(1.5)
        imgB = capture_bgr(session)
        cv2.imwrite(str(OUT / "B_preview.png"), imgB)
        fracB = has_colored_content(imgB)
        print(f"{LOG} B preview frac={fracB:.3%} ratio={fracB / max(fracA, 1e-6):.2f}x")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
