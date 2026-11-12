#!/usr/bin/env python3
# probe_241_picker7.py — 2.4.1 选择框第七轮：弹层内部的"一级"入口（悬停/点击左缘等）
#
# 已知：combo（任意 x）→ 二级耗材弹层（≈200x238，回显定位）；行尾 Button/Edit 都不开弹层。
# 但探针二里确实出现过**一级弹层**（≈274x392，'------ System presets ------' +
# Snapmaker/Generic >/… + '------ Add/Remove filament ------'），说明一级入口存在、只是触发条件不同。
#
# 本轮对打开后的弹层做一组交互（悬停左缘/左上角/点击左缘/双击行/右键行），
# 每步报告"当前弹层集合"（含窗口尺寸变化）与层级，找出一级入口。
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

LOG = "[pk247]"
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
    cv2.imwrite(str(ART / f"m8xP7_{name}.png"), img)
    print(f"{LOG} shot -> m8xP7_{name}.png")


def popups(pid):
    import ctypes
    from ctypes import wintypes as wt
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(160)
        user32.GetWindowTextW(hwnd, txt, 160)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        r = (rc.left, rc.top, rc.right, rc.bottom)
        if cls.value in ("tooltips_class32", "SysShadow") or txt.value == "mixed_filament_test - Snapmaker Orca":
            return True
        out.append((cls.value, txt.value, r, hwnd))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def level_and_ocr(pop):
    import cv2
    import numpy as np
    try:
        pw, ph, pbuf = winutil.capture_window(pop[3])
        img = cv2.cvtColor(np.frombuffer(pbuf, np.uint8).reshape(ph, pw, 4), cv2.COLOR_BGRA2BGR)
        words = mdu.ocr_words_img(img, scale=2, psm=6)
    except Exception as exc:                                  # noqa: BLE001
        return f"<ocr failed {exc!r}>", ""
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
        cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
        print(f"{LOG} slot2 combo rect={rect}")

        def state(tag):
            ps = [p for p in popups(session.pid) if p[0] == "wxWindowNR"]
            print(f"{LOG} [{tag}] popups: {[(p[2], (p[2][2] - p[2][0]), (p[2][3] - p[2][1])) for p in ps]}")
            for p in ps:
                if p[2][2] - p[2][0] > 120:
                    lvl, blob = level_and_ocr(p)
                    print(f"{LOG}   -> {lvl} | {blob!r}")
            return ps

        # 1) 打开
        user32.SetCursorPos(cx, cy)
        time.sleep(0.3)
        winutil.real_click_screen(cx, cy)
        time.sleep(1.5)
        ps = state("open")
        if not ps:
            print(f"{LOG} no popup after combo click")
            return 1
        pr = [p for p in ps if p[2][2] - p[2][0] > 120][0][2]
        shot("01_open", pr)

        # 2) 悬停弹层左缘
        user32.SetCursorPos(pr[0] + 3, (pr[1] + pr[3]) // 2)
        time.sleep(1.6)
        state("hover left edge")
        shot("02_hover_left", pr)
        # 3) 点击弹层左缘
        winutil.real_click_screen(pr[0] + 3, (pr[1] + pr[3]) // 2)
        time.sleep(1.5)
        ps = state("click left edge")
        shot("03_click_left")
        # 4) 悬停左上角
        pr2 = [p for p in ps if p[2][2] - p[2][0] > 120]
        pr2 = pr2[0][2] if pr2 else pr
        user32.SetCursorPos(pr2[0] + 3, pr2[1] + 4)
        time.sleep(1.6)
        state("hover top-left")
        # 5) 双击第一行
        winutil.real_click_screen(pr2[0] + 60, pr2[1] + 20)
        time.sleep(0.15)
        winutil.real_click_screen(pr2[0] + 60, pr2[1] + 20)
        time.sleep(1.5)
        state("double click first row")
        # 6) 右键第一行
        winutil.real_right_click_screen(pr2[0] + 60, pr2[1] + 40)
        time.sleep(1.5)
        ps = state("right click a row")
        shot("06_right_click_row")
        for p in ps:
            if p[0] == "#32768":
                items = []
                try:
                    items = [lbl for _i, lbl in m7.list_menu(p[3])]
                except Exception as exc:                          # noqa: BLE001
                    items = [f"<{exc!r}>"]
                print(f"{LOG}   menu items: {items}")
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.6)
        print(f"{LOG} combo after probe: {m8.combo_text(hit['combo'][2])!r}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
