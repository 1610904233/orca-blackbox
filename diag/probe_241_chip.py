#!/usr/bin/env python3
# probe_241_chip.py — 2.4.1：槽位"数字色块"点击重试 → 官方色卡对话框？
#
# j384 首轮里 chip 单击没弹出任何东西（可能是被吞的第一次点击，PITFALLS 18.4）。
# 本轮对 slot 2 的 chip 连续点 3 次（每次间隔 1.5s，看到 #32770 就停），每次 dump
# toplevels + 子控件文本，判定是不是 2.4.0 的"Official Filaments"官方色卡弹层。
# 顺带对 slot 1 的 chip 做同样的事（对照：Generic PETG 走传统取色器）。
# 只读：看完就 WM_CLOSE/ESC；**不关闭 app**。
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pchip]"
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


def tops(pid):
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetWindowClassNameW = None
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(200)
        user32.GetWindowTextW(hwnd, txt, 200)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"pchip_{name}.png"), img)
    print(f"{LOG} shot -> pchip_{name}.png")


def click_chip(session, slot, tries=3):
    slots = m8.wait_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit:
        print(f"{LOG} slot{slot} not found")
        return None
    x0, y0, x1, y1 = hit["swatch"]
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    print(f"{LOG} slot{slot} chip rect={hit['swatch']} click@({cx},{cy}) "
          f"combo={m8.combo_text(hit['combo'][2]) if hit['combo'] else None!r}")
    before = {t[3] for t in tops(session.pid)}
    found = None
    for i in range(tries):
        user32.SetCursorPos(cx, cy)
        time.sleep(0.3)
        winutil.real_click_screen(cx, cy)
        time.sleep(1.6)
        new = [t for t in tops(session.pid) if t[3] not in before
               and t[0] not in ("tooltips_class32", "SysShadow")]
        print(f"{LOG}   try{i + 1}: new toplevels {[(t[0], t[1], t[2]) for t in new]}")
        for cls, title, rect, hwnd in new:
            kids = [k.strip() for k, _r, _h
                    in export_util._children_texts(hwnd) if k.strip()]
            print(f"{LOG}     {cls!r} {title!r} kids({len(kids)}): {kids[:18]}")
            if cls == "#32770" and any("official" in k.lower() for k in kids):
                found = (cls, title, rect, hwnd)
        if found:
            shot(f"s{slot}_official", found[2])
            break
        if new:
            shot(f"s{slot}_other{i}", new[0][2])
            break
    return found


def main() -> int:
    pids = find_running()
    if not pids:
        print(f"{LOG} FAIL: no snapmaker-orca running")
        return 1
    hwnd, pid = 0, pids[0]
    for p in pids:
        try:
            h = winutil.find_main_window(p, timeout_s=20.0)
        except Exception:                                      # noqa: BLE001
            continue
        if not hwnd:
            hwnd, pid = h, p
    session = AttachedSession(pid, hwnd)
    print(f"{LOG} pid={pid} hwnd=0x{hwnd:X}")
    user32.ShowWindow(hwnd, 3)
    time.sleep(1.2)
    res = {}
    for slot in (2, 1):
        found = click_chip(session, slot)
        res[slot] = bool(found)
        # 关掉可能开着的对话框/弹层
        for cls, title, rect, h in tops(pid):
            if cls == "#32770" and h:
                winutil.close_window(h)
                time.sleep(0.8)
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(1.0)
        slots = m8.wait_slots(session)
        print(f"{LOG} slot{slot} after cleanup: "
              f"{[(s['slot'], m8.combo_text(s['combo'][2]) if s['combo'] else None) for s in slots]}")
    print(f"{LOG} ==== summary: official popup = {res} ====")
    print(f"{LOG} app alive: {session.alive()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
