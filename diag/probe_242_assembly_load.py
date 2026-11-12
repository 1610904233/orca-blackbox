#!/usr/bin/env python3
# probe_242_assembly_load.py — assembly 夹具载入诊断：
# dump 所有顶层窗口（是否有版本/错误提示框）、主窗标题、画面 OCR 采样、
# 侧栏对象树区域 OCR。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7
import m8_common as m8
from harness import export_util, mix_dialog_util as mdu, winutil
from m1_minimal_loop import capture_bgr
from m3_common import add_common_args, boot_session

LOG = "[p242al]"
ASM = HERE / "fixtures" / "assembly_pokemon_box.3mf"


def ocr_full(session, tag):
    img = capture_bgr(session)
    words = mdu.ocr_words_img(img, scale=2)
    print(f"{LOG} {tag} OCR: {' | '.join(w[0] for w in words[:50])}")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=ASM)
    args = ap.parse_args()
    session = boot_session(args, model=ASM)
    try:
        time.sleep(15.0)
        m7.ensure_maximized(session)
        # 连点所有提示框（information / Customized Preset ...）直到只剩
        # Loading... 或全消失；每轮点 OK/Yes 类按钮
        for rnd in range(8):
            dialogs = [(c, t, r, h) for c, t, r, h in
                       m7._visible_toplevels(session.pid) if c == "#32770"]
            pend = [d for d in dialogs if "loading" not in (d[1] or "").lower()]
            if not pend:
                print(f"{LOG} round{rnd}: no pending dialogs "
                      f"(loading={'yes' if dialogs else 'no'})")
                break
            for c, t, r, h in pend:
                kids = export_util._children_texts(h)
                print(f"{LOG} round{rnd} dialog {t!r} kids="
                      f"{[k[0][:20] for k in kids if k[0].strip()][:6]}")
                btn = next(((kt, kr, kh) for kt, kr, kh in kids
                            if kt.strip().lower() in
                            ("ok", "yes", "确定", "是")), None)
                if btn:
                    kt, kr, kh = btn
                    cx, cy = (kr[0] + kr[2]) // 2, (kr[1] + kr[3]) // 2
                    winutil.user32.SetCursorPos(cx, cy)
                    winutil.real_click_screen(cx, cy)
                    print(f"{LOG} round{rnd} clicked {kt!r} @({cx},{cy})")
                else:
                    m7.user32.SendMessageW(h, 0x0111, 1, 0)
                    print(f"{LOG} round{rnd} sent WM_COMMAND IDOK")
                time.sleep(3.0)
            time.sleep(2.0)
        # 等 Loading... 消失（最多 180s）
        deadline = time.monotonic() + 180.0
        while time.monotonic() < deadline:
            titles = [t for c, t, r, h in m7._visible_toplevels(session.pid)
                      if c == "#32770"]
            if not any("loading" in (t or "").lower() for t in titles):
                break
            time.sleep(3.0)
        time.sleep(5.0)
        for cls, title, rect, hwnd in m7._visible_toplevels(session.pid):
            print(f"{LOG} final toplevel {cls!r} {title[:60]!r} {rect}")
        print(f"{LOG} final colored frac={m7.model_colored_frac(session):.3%} "
              f"blobs={m7.blob_count(session)}")
        ocr_full(session, "final")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
