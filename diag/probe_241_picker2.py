#!/usr/bin/env python3
# probe_241_picker2.py — 2.4.1 耗材选择框只读探针（第二轮：找"一级供应商"入口）
#
# 第一轮结论:
#   * 弹层要用**真实点击**才开（消息级点击不开）；应用可能不是前台（本机 fg=desktop）。
#   * 弹层是**单列窄列表**（≈200x238），打开时按"回显"停在当前耗材附近
#     （先看到 PLA Translucent/PLA Wood/PVA/TPU…；真实滚轮往上才看到 Snapmaker 的
#      8 项置顶 PLA SnapSpeed/PLA Matte/PETG HF/…/ABS/ASA）。
#   * 消息级滚轮无效、**真实滚轮有效** ✓
#   * 弹层里**没有**供应商行（Snapmaker/Generic/Polymaker/自定义/项目 都没 OCR 到）
#     → 一级入口在别处（另一个控件/另一层弹层）。
#
# 本轮:
#   Q1 槽位那一行在 2.4.1 上有哪些控件（含无文本的小按钮）——逐个真实点击并 dump 弹出的东西；
#   Q2 弹层的左边缘/顶部有没有可展开的一级（悬停/点击试一试）；
#   Q3 我们的用户预设（... - STD-TEST 等）落在哪个分组（滚到底是用户配置还是系统配置）。
#
# 只读：只开弹层/点层级，不做最终选择；结束前 Esc。
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

LOG = "[pk242]"
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
    cv2.imwrite(str(ART / f"m8xP2_{name}.png"), img)
    print(f"{LOG} shot -> m8xP2_{name}.png")


def click_at(x, y, pause=1.2):
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


def ocr_popup(pop, tag):
    import cv2
    import numpy as np
    pw, ph, pbuf = winutil.capture_window(pop[3])
    img = cv2.cvtColor(np.frombuffer(pbuf, np.uint8).reshape(ph, pw, 4), cv2.COLOR_BGRA2BGR)
    words = mdu.ocr_words_img(img, scale=2, psm=6)
    lines = {}
    for t, x, y, w, h in words:
        key = next((k for k in lines if abs(k - y) <= 12), y)
        lines.setdefault(key, []).append((x, y, t))
    rows = [(k, " ".join(t for _x, _y, t in sorted(lines[k]))) for k in sorted(lines)]
    print(f"{LOG} --- {tag}: {len(rows)} lines ---")
    for y, txt in rows:
        print(f"{LOG}   y={y:4d} {txt[:88]}")
    return rows


def toplevels(pid):
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
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        m8.wait_slots(session)
        slots = m8.wait_slots(session)
        hit = next((s for s in slots if s["slot"] == 2), None)
        text, rect, ch = hit["combo"]
        print(f"{LOG} slot2 combo={text!r} rect={rect} picker={hit.get('picker')}")
        # Q1: 槽位行里的所有控件（含无文本）
        row_band = (rect[1] - 14, rect[3] + 14)
        controls = [(t, r, h) for t, r, h in all_children(session.hwnd)
                    if row_band[0] <= r[1] <= row_band[1] and r[0] < 440]
        print(f"{LOG} slot2 row controls:")
        for t, r, h in sorted(controls, key=lambda c: c[1][0]):
            print(f"{LOG}   {t.strip()[:26]!r} rect={r} cls={winutil.window_class(h)}")

        # 依次真实点击行内每个非文本控件，看弹出什么
        for i, (t, r, h) in enumerate(sorted(controls, key=lambda c: c[1][0])):
            if t.strip() or (r[2] - r[0]) < 8:
                continue
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            print(f"{LOG} --- click control #{i} cls={winutil.window_class(h)} @({cx},{cy})")
            click_at(cx, cy, 1.5)
            shot(f"c{i}_after_click")
            tops = [x for x in toplevels(session.pid)
                    if x[0] not in ("#32768",) and x[1] != "mixed_filament_test - Snapmaker Orca"]
            print(f"{LOG}     new toplevels: {[(x[0], x[1], x[2]) for x in tops]}")
            for x in tops:
                ocr_popup(x, f"popup from control #{i} ({winutil.window_class(h)})")
                shot(f"c{i}_{x[0]}", x[2])
            # 关掉任何跑出来的弹层
            user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.8)

        # Q2: 打开弹层，试左边缘/顶部（找一级入口）
        click_at((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2, 1.5)
        pop = export_util.wait_popup(session.pid, timeout_s=4.0)
        if pop:
            pr = pop[2]
            shot("open", pr)
            ocr_popup(pop, "open")
            for dx, dy, tag in ((6, 12, "left_top"), (6, 60, "left_mid"), (pr[2] - pr[0] - 8, 12, "right_top")):
                x, y = pr[0] + dx, pr[1] + dy
                print(f"{LOG} --- hover/click popup {tag} @({x},{y})")
                user32.SetCursorPos(x, y)
                time.sleep(1.0)
                shot(f"h_{tag}")
                for t2, r2, h2 in all_children(session.hwnd):
                    if (r2[0], r2[1]) == (pr[0], pr[1]) and (r2[2], r2[3]) == (pr[2], pr[3]):
                        continue
                click_at(x, y, 1.2)
                tops = [x2 for x2 in toplevels(session.pid)
                        if x2[0] != "#32768" and x2[1] != "mixed_filament_test - Snapmaker Orca" and x2[3] != pop[3]]
                print(f"{LOG}     toplevels besides main+popup: {[(x2[0], x2[1], x2[2]) for x2 in tops]}")
                for x2 in tops:
                    ocr_popup(x2, f"{tag} popup")
                ocr_popup(pop, f"list after {tag}")
            # Q3: 滚到底看有没有用户配置/我们的测试包
            for i in range(40):
                winutil.real_wheel_screen(pr[0] + 40, (pr[1] + pr[3]) // 2, -3)
                time.sleep(0.12)
            time.sleep(0.8)
            shot("bottom", pr)
            rows = ocr_popup(pop, "scrolled to bottom")
            hit = [t for _y, t in rows if 'STD-TEST' in t or 'TEST' in t.upper() or '自定义' in t or '用户' in t]
            print(f"{LOG} bottom rows mentioning TEST/自定义/用户: {hit}")
        else:
            print(f"{LOG} popup did not open in round 2")
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.5)
        print(f"{LOG} slot2 combo after probe: {m8.combo_text(ch)!r}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
