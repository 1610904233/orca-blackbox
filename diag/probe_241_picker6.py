#!/usr/bin/env python3
# probe_241_picker6.py — 2.4.1 选择框第六轮：验证"combo 左段=一级 / 中段=二级"的假设
#
# 线索：探针二里开出**一级（System presets/Generic>/…）**的那次点击在 (245,461)，
# 而 slot3 的 combo 是 (236,444,388,474) —— 即点在 **combo 左侧 ~10px**；
# 后续几轮我都点 combo 中点，开出来的都是**二级耗材列表**。
# 所以假设：这个宽控件是**两段式**（左段=供应商/分组，右段=耗材）。
#
# 本轮：对 slot2 的 combo 分别在 左+10 / 左+40 / 中点 / 右-10 四个 x 上真实点击，
# 报告每次弹层的层级（OCR 里有没有 'System presets'）与截图。
import argparse
import sys
import time
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

LOG = "[pk246]"
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
    cv2.imwrite(str(ART / f"m8xP6_{name}.png"), img)
    print(f"{LOG} shot -> m8xP6_{name}.png")


def level_and_ocr(pop):
    import cv2
    import numpy as np
    pw, ph, pbuf = winutil.capture_window(pop[3])
    img = cv2.cvtColor(np.frombuffer(pbuf, np.uint8).reshape(ph, pw, 4), cv2.COLOR_BGRA2BGR)
    words = mdu.ocr_words_img(img, scale=2, psm=6)
    blob = " ".join(w for w, *_ in words)
    lvl = "LEVEL-1(vendor)" if ("System presets" in blob or "Add/Remove filament" in blob) else "level-2"
    return lvl, blob[:110]


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        slots = m8.wait_slots(session)
        hit = next((s for s in slots if s["slot"] == 2), None)
        rect = hit["combo"][1]
        cy = (rect[1] + rect[3]) // 2
        print(f"{LOG} slot2 combo rect={rect}")
        for tag, x in (("left+10", rect[0] + 10), ("left+40", rect[0] + 40),
                       ("center", (rect[0] + rect[2]) // 2), ("right-10", rect[2] - 10)):
            user32.SetCursorPos(int(x), int(cy))
            time.sleep(0.3)
            winutil.real_click_screen(int(x), int(cy))
            time.sleep(1.5)
            pop = export_util.wait_popup(session.pid, timeout_s=4.0)
            if pop:
                lvl, blob = level_and_ocr(pop)
                print(f"{LOG} click x={x} ({tag}) -> {lvl} | {blob!r}")
                shot(f"click_{tag.replace('+', '')}", pop[2])
            else:
                print(f"{LOG} click x={x} ({tag}) -> no popup")
            user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.9)
        print(f"{LOG} combo after probe: {m8.combo_text(hit['combo'][2])!r}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
