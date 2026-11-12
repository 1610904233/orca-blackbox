#!/usr/bin/env python3
# probe_241_picker5.py — 2.4.1 选择框第五轮：找"一级（供应商）"的确切入口
#
# 前几轮:
#   * combo（槽位行中间那个宽控件）→ 二级耗材列表（回显定位；真实滚轮可滚）；
#   * 行尾 16x25 Button → 前几轮里**有两次**开出了一级（System presets/Generic>/…），
#     但后续几轮又打不开 → 需要精确定位（可能是 combo 右侧的小箭头、或弹层里的另一栏）。
#
# 本轮把"弹层自身的子控件（含无文本）+ combo 周边的小控件"全 dump 出来，逐个真实点击并报告层级。
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

LOG = "[pk245]"
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
    cv2.imwrite(str(ART / f"m8xP5_{name}.png"), img)
    print(f"{LOG} shot -> m8xP5_{name}.png")


def click_at(x, y, pause=1.4):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def kids_all(parent):
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


def level_of(pop):
    import cv2
    import numpy as np
    pw, ph, pbuf = winutil.capture_window(pop[3])
    img = cv2.cvtColor(np.frombuffer(pbuf, np.uint8).reshape(ph, pw, 4), cv2.COLOR_BGRA2BGR)
    words = [w for w, *_ in mdu.ocr_words_img(img, scale=2, psm=6)]
    blob = " ".join(words).lower()
    if "system presets" in blob or "add/remove filament" in blob:
        return "LEVEL-1(vendor)", blob[:80]
    return "level-2(filament)", blob[:80]


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
        combo_rect = hit["combo"][1]
        picker = hit.get("picker")
        print(f"{LOG} combo={combo_rect} picker={picker}")

        # A) combo 周边所有控件（含无文本）：combo 右缘 ±40px 内
        near = [(t, r, h) for t, r, h in kids_all(session.hwnd)
                if abs(((r[0] + r[2]) // 2) - combo_rect[2]) <= 45
                and abs(((r[1] + r[3]) // 2) - (combo_rect[1] + combo_rect[3]) // 2) <= 20]
        print(f"{LOG} controls hugging the combo's right edge:")
        for t, r, h in sorted(near, key=lambda c: c[1][0]):
            print(f"{LOG}   {t.strip()[:20]!r} rect={r} cls={winutil.window_class(h)} "
                  f"size={r[2] - r[0]}x{r[3] - r[1]}")

        # B) 先点 combo 开二级，再 dump 弹层自身的子控件（含无文本）
        cx = (combo_rect[0] + combo_rect[2]) // 2
        cy = (combo_rect[1] + combo_rect[3]) // 2
        click_at(cx, cy, 1.5)
        pop = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not pop:
            print(f"{LOG} popup did not open from combo")
            return 1
        lvl, blob = level_of(pop)
        print(f"{LOG} popup from combo: {lvl} | {blob!r}")
        shot("01_from_combo", pop[2])
        print(f"{LOG} popup children (all):")
        for t, r, h in kids_all(pop[3]):
            print(f"{LOG}   {t.strip()[:24]!r} rect={r} cls={winutil.window_class(h)} "
                  f"size={r[2] - r[0]}x{r[3] - r[1]}")
        # B2) 弹层打开时，主窗里是否多出"一级栏"控件（比如左侧面板）
        print(f"{LOG} main-window controls overlapping the popup area (possible vendor pane):")
        for t, r, h in kids_all(session.hwnd):
            if (r[2] > pop[2][0] - 30 and r[0] < pop[2][2] + 30
                    and r[3] > pop[2][1] - 30 and r[1] < pop[2][3] + 30
                    and (r[2] - r[0]) > 3 and (r[3] - r[1]) > 3):
                print(f"{LOG}   {t.strip()[:24]!r} rect={r} cls={winutil.window_class(h)}")
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.8)

        # C) 逐个试"combo 右缘附近"的控件 + picker，看谁能开一级
        cands = [(t, r, h) for t, r, h in kids_all(session.hwnd)
                 if abs(((r[0] + r[2]) // 2) - combo_rect[2]) <= 45
                 and abs(((r[1] + r[3]) // 2) - cy) <= 20 and (r[2] - r[0]) <= 40]
        for i, (t, r, h) in enumerate(sorted(cands, key=lambda c: c[1][0])):
            if t.strip():
                continue
            px, py = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            click_at(px, py, 1.5)
            pop = export_util.wait_popup(session.pid, timeout_s=3.5)
            if pop:
                lvl, blob = level_of(pop)
                print(f"{LOG} cand#{i} cls={winutil.window_class(h)} @({px},{py}) -> {lvl} | {blob!r}")
                shot(f"cand{i}_{'L1' if 'LEVEL-1' in lvl else 'L2'}", pop[2])
            else:
                print(f"{LOG} cand#{i} cls={winutil.window_class(h)} @({px},{py}) -> no popup")
            user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.7)
        print(f"{LOG} combo after probe: {m8.combo_text(hit['combo'][2])!r}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
