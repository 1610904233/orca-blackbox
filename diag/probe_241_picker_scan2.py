#!/usr/bin/env python3
# probe_241_picker_scan2.py — 2.4.1：把选择框的**供应商分支逐个**展开扫描。
#
# 上一轮教训（pscan_s2_picker.jpg）：弹层开在鼠标落点，光标恰好压在 'Generic' 行上，
# 于是右栏显示的是 Generic 的列表——我们据此说"没有 Rainbow"是**错的**（扫错了分支）。
# 本轮：
#   1) attach 到正在跑的实例；
#   2) 打开槽位选择框；
#   3) 对每个候选供应商行（Snapmaker / Generic）先 **hover**（光标移到行上）再 **click**，
#      每步 OCR 右栏——hover 即切换右栏（两级菜单语义）；
#   4) 右栏逐档滚轮（-1 档）枚举所有不同屏，打印；（5）左栏整栏 dump（含被 OCR 漏掉的行）
#   6) 保存右栏裁剪图给人工/视觉复核。
# 只读：不点耗材行；最后 ESC 关闭。**不关闭 app**。
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pscan2]"
ART = HERE / "artifacts"
user32 = winutil.user32


class AttachedSession:
    def __init__(self, pid, hwnd):
        self.pid = pid
        self.hwnd = hwnd

    def alive(self):
        return bool(user32.IsWindow(self.hwnd))

    def close(self):
        print(f"{LOG} (attach session: close() suppressed)")


def find_running():
    raw = subprocess.run(["tasklist", "/FI", "IMAGENAME eq snapmaker-orca.exe",
                          "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    pids = []
    for ln in raw.splitlines():
        parts = [p.strip('"') for p in ln.split('","')]
        if len(parts) > 1 and parts[0].lower().startswith("snapmaker-orca"):
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1]):rect[3], max(0, rect[0]):rect[2]]
    ART.mkdir(parents=True, exist_ok=True)
    p = ART / f"pscan2_{name}.png"
    cv2.imwrite(str(p), img)
    print(f"{LOG} shot -> {p.name}")


def esc(n=1):
    for _ in range(n):
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.6)


def move_to(x, y, pause=0.9):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(pause)


def rows_text(rows):
    return " | ".join(t for _y, t, _x in rows)


def picker_state(session, tag=""):
    panes = m8._picker_panes(session)
    vend = next((p for p in panes if p["is_vendor"]), None)
    filt = next((p for p in panes if not p["is_vendor"]), None)
    print(f"{LOG} [{tag}] panes={[(p['rect'], 'V' if p['is_vendor'] else 'F', len(p['rows'])) for p in panes]}")
    if vend:
        print(f"{LOG} [{tag}] LEFT  : {rows_text(vend['rows'])}")
    if filt:
        print(f"{LOG} [{tag}] RIGHT : {rows_text(filt['rows'])}")
    return panes, vend, filt


def scan_right(session, filt, tag, notches=-1, steps=16):
    """右栏逐档滚动，打印每个**不同**屏。"""
    cx = filt["rect"][0] + 60
    cy = (filt["rect"][1] + filt["rect"][3]) // 2
    seen = [rows_text(filt["rows"])]
    print(f"{LOG} [{tag}] scan start: {seen[0]}")
    for i in range(steps):
        winutil.real_wheel_screen(cx, cy, notches)
        time.sleep(0.35)
        cur = m8._screen_ocr_rows(filt["rect"])
        t = rows_text(cur)
        if t != seen[-1]:
            seen.append(t)
            print(f"{LOG} [{tag}] wheel{notches:+d} step{i:02d}: {t}")
    return seen


def hover_vendor(session, vend, name):
    """把光标移到厂商行上（hover 即切换右栏）；返回命中的行。"""
    low = name.lower()
    cands = [(y, t, x) for y, t, x in vend["rows"]
             if t.strip().lower().startswith(low)]
    if not cands:
        print(f"{LOG} vendor row {name!r} not in OCR rows: {rows_text(vend['rows'])[:160]}")
        return None
    y, t, x = cands[0]
    print(f"{LOG} hover vendor {t!r} @({max(20, x) + 60},{y})")
    move_to(max(20, x) + 60, y, pause=1.4)
    return (y, t, x)


def main() -> int:
    pids = find_running()
    print(f"{LOG} running pids: {pids}")
    if not pids:
        print(f"{LOG} FAIL: no snapmaker-orca running")
        return 1
    hwnd, pid = 0, 0
    for p in pids:
        try:
            h = winutil.find_main_window(p, timeout_s=20.0)
        except Exception as exc:                              # noqa: BLE001
            print(f"{LOG} pid {p}: no main window ({exc})")
            continue
        if not hwnd:
            hwnd, pid = h, p
            print(f"{LOG} pid {p} hwnd=0x{h:X} rect={winutil.window_rect(h)}")
    if not hwnd:
        print(f"{LOG} FAIL: no main window")
        return 1
    session = AttachedSession(pid, hwnd)
    user32.ShowWindow(hwnd, 3)
    time.sleep(1.2)
    slots = m8.wait_slots(session)
    print(f"{LOG} slots: {[(s['slot'], (s['combo'] or [None, None])[0]) for s in slots]}")
    slot = 2
    pop, ch, how = m8._picker_open(session, slot)
    print(f"{LOG} open: {bool(pop)} via {how!r} combo={m8.combo_text(ch) if ch else None!r}")
    if not pop:
        return 1
    time.sleep(0.8)
    # 先把光标挪到右栏（离开厂商行），得到"未 hover"的初始态
    panes, vend, filt = picker_state(session, "open(neutral-ish)")
    if not vend or not filt:
        print(f"{LOG} panes incomplete — abort")
        esc(2)
        return 1
    move_to(filt["rect"][0] + 60, (filt["rect"][1] + filt["rect"][3]) // 2, 1.0)
    panes, vend, filt = picker_state(session, "mouse-in-right")
    results = {}
    for name in ("Snapmaker", "Generic"):
        hit = hover_vendor(session, vend, name)
        if not hit:
            continue
        time.sleep(0.6)
        # hover 后重取 pane 的 rows（右栏内容已切换）
        panes2 = m8._picker_panes(session)
        filt2 = next((p for p in panes2 if not p["is_vendor"]), None)
        if not filt2:
            print(f"{LOG} {name}: right pane vanished after hover")
            continue
        print(f"{LOG} --- {name} (hover) RIGHT: {rows_text(filt2['rows'])}")
        shot(f"{name}_hover", filt2["rect"])
        seen = scan_right(session, filt2, f"{name}-hover", notches=-1, steps=16)
        # 再滚回顶（+1 档逐步）看有没有 hover 时没显示的顶部行
        cx = filt2["rect"][0] + 60
        cy = (filt2["rect"][1] + filt2["rect"][3]) // 2
        for _ in range(20):
            winutil.real_wheel_screen(cx, cy, 1)
            time.sleep(0.1)
        time.sleep(0.4)
        rows_top = m8._screen_ocr_rows(filt2["rect"])
        print(f"{LOG} --- {name} back-to-top RIGHT: {rows_text(rows_top)}")
        seen.append(rows_text(rows_top))
        blob = " ".join(seen).lower()
        results[name] = {
            "seen": seen,
            "rainbow": "rainbow" in blob,
            "spectrum": "spectrum" in blob,
            "snapspeed": "snapspeed" in blob,
        }
        # 点一下该厂商（真实点击）确认不会关掉弹层
        move_to(max(20, hit[2]) + 60, hit[0], 0.5)
        winutil.real_click_screen(max(20, hit[2]) + 60, hit[0])
        time.sleep(1.0)
        panes3 = m8._picker_panes(session)
        filt3 = next((p for p in panes3 if not p["is_vendor"]), None)
        print(f"{LOG} --- {name} (clicked) RIGHT: {rows_text(filt3['rows']) if filt3 else '<gone>'}")
        time.sleep(0.4)
    # 左栏整栏再 dump 一次（含 OCR 漏行）
    panes4, vend4, _f = picker_state(session, "left-dump")
    if vend4:
        shot("left_pane", vend4["rect"])
    esc(2)
    print(f"{LOG} ==== summary ====")
    for k, v in results.items():
        print(f"{LOG} {k}: rainbow={v['rainbow']} spectrum={v['spectrum']} snapspeed={v['snapspeed']}")
    print(f"{LOG} app alive: {session.alive()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
