#!/usr/bin/env python3
# probe_241_picker4.py — 2.4.1 选择框第四轮：精确定位"一级（供应商）入口"控件
#
# 已知:
#   * 点槽位行的 combo(wxWindowNR, 文本=耗材名) → 开**二级耗材列表**（回显定位，真实滚轮有效）；
#   * 第二轮里"某个 Button @(245,461)"开出了**一级供应商列表**（System presets/Generic>/…），
#     但那个坐标与 m8.filament_slots() 给的 picker=(393,412,409,437) 对不上 → 需要精确鉴定。
#
# 本轮: 把槽位区(y 360..600, x 0..440)内**所有子控件**（含无文本、各种 class）列出来，
#       逐个真实点击并报告"弹出了什么"（用 OCR 首行判断：'System presets' = 一级 /
#       其它 = 二级），最后把"哪个控件开哪个层"的对照表打出来。
#
# 只读：只开弹层、不选择；每步 Esc 关闭。
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

from harness import export_util, mix_dialog_util as mdu, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pk244]"
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
    cv2.imwrite(str(ART / f"m8xP4_{name}.png"), img)
    print(f"{LOG} shot -> m8xP4_{name}.png")


def click_at(x, y, pause=1.3):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def all_children(parent):
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


def popup_first_line(pop):
    import cv2
    import numpy as np
    pw, ph, pbuf = winutil.capture_window(pop[3])
    img = cv2.cvtColor(np.frombuffer(pbuf, np.uint8).reshape(ph, pw, 4), cv2.COLOR_BGRA2BGR)
    words = [w for w, *_ in mdu.ocr_words_img(img, scale=2, psm=6)]
    return " ".join(words)[:100]


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
        print(f"{LOG} slots: {[(s['slot'], s['combo'][0], s.get('picker')) for s in slots[:3]]}")
        hit = next((s for s in slots if s["slot"] == 2), None)
        combo_text, combo_rect, ch = hit["combo"]

        cands = [(t, r, h) for t, r, h in all_children(session.hwnd)
                 if 360 <= r[1] <= 600 and r[0] < 440 and (r[2] - r[0]) >= 6 and (r[3] - r[1]) >= 6]
        print(f"{LOG} controls in the slot band ({len(cands)}):")
        for t, r, h in sorted(cands, key=lambda c: (c[1][1], c[1][0])):
            print(f"{LOG}   {t.strip()[:24]!r} rect={r} cls={winutil.window_class(h)} "
                  f"size={r[2] - r[0]}x{r[3] - r[1]}")
        # 逐个点击（跳过 combo 本身，已知它开二级）
        for i, (t, r, h) in enumerate(sorted(cands, key=lambda c: (c[1][1], c[1][0]))):
            cls = winutil.window_class(h)
            w, hh = r[2] - r[0], r[3] - r[1]
            if (r[0], r[1]) == (combo_rect[0], combo_rect[1]):
                print(f"{LOG} #{i} skip combo itself {r}")
                continue
            if t.strip() and cls not in ("Button",):
                print(f"{LOG} #{i} skip text control {t.strip()[:18]!r} {r}")
                continue
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            click_at(cx, cy, 1.4)
            pop = export_util.wait_popup(session.pid, timeout_s=3.0)
            if pop:
                first = popup_first_line(pop)
                level = "LEVEL-1(vendor)" if "system presets" in first.lower() else "level-2(filament)"
                print(f"{LOG} #{i} {cls} {w}x{hh} @({cx},{cy}) -> POPUP {level}: {first!r}")
                shot(f"c{i}_{'L1' if 'LEVEL-1' in level else 'L2'}", pop[2])
            else:
                print(f"{LOG} #{i} {cls} {w}x{hh} @({cx},{cy}) -> no popup")
            user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.7)
        print(f"{LOG} combo after probe: {m8.combo_text(ch)!r} (was {combo_text!r})")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
