#!/usr/bin/env python3
# probe_241_picker_scan.py — 2.4.1：在**已运行**的 app 实例上扫描耗材选择框。
#
# 目标（回答"Rainbow 到底在不在选择框里"）：
#   1) 找到正在跑的 snapmaker-orca.exe（**不启动新实例、不关闭它**）；
#   2) 打开某个槽位的选择框（真实点击，2.4.1 必须）；
#   3) 把左栏（厂商/分组）与右栏（耗材）整栏枚举出来；
#   4) 右栏用真实滚轮逐步下滚，每一步 OCR 并打印——看 'PLA Rainbow' /
#      'Full Spectrum' 是否出现、顺序如何；
#   5) 全程只读：不点选中行，最后 ESC 关闭弹层。
#
# 用法（客机 INTERACTIVE 会话内）：
#   C:\Python311\python.exe C:\coil\orca-blackbox\diag\probe_241_picker_scan.py
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

LOG = "[pscan]"
ART = HERE / "artifacts"
user32 = winutil.user32


class AttachedSession:
    """只读 attach：pid/hwnd 来自正在跑的实例，close() 不关 app。"""

    def __init__(self, pid, hwnd):
        self.pid = pid
        self.hwnd = hwnd

    def alive(self):
        return winutil.user32.IsWindow(self.hwnd)

    def rect(self):
        return winutil.window_rect(self.hwnd)

    def close(self):        # 故意 no-op：本探针不允许关掉在跑的实例
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
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    ART.mkdir(parents=True, exist_ok=True)
    p = ART / f"pscan_{name}.png"
    cv2.imwrite(str(p), img)
    print(f"{LOG} shot -> {p.name} ({img.shape[1]}x{img.shape[0]})")


def esc(n=1):
    for _ in range(n):
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.6)


def tops(pid):
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(200)
        user32.GetWindowTextW(hwnd, txt, 200)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def scan_slot(session, slot, key="rainbow"):
    print(f"{LOG} ================= slot {slot} =================")
    pop, ch, how = m8._picker_open(session, slot)
    print(f"{LOG} picker open: {bool(pop)} via {how!r}  combo_before={m8.combo_text(ch) if ch else None!r}")
    if not pop:
        return False, ""
    time.sleep(0.8)
    shot(f"s{slot}_00_open")
    panes = m8._picker_panes(session)
    print(f"{LOG} panes: {[(p['rect'], p['is_vendor'], len(p['rows'])) for p in panes]}")
    for p in panes:
        tag = "VENDOR" if p["is_vendor"] else "FILAMENT"
        print(f"{LOG} [{tag}] rect={p['rect']}")
        for y, t, x in p["rows"]:
            print(f"{LOG}    y={y:5d} x={x:5d}  {t!r}")
    seen = []
    filt = m8._filament_pane(session, panes)
    if not filt:
        print(f"{LOG} no filament pane — dumping all toplevels")
        for cls, txt, r, h in tops(session.pid):
            print(f"{LOG}   TOP {cls!r} {txt!r} {r}")
        esc(2)
        return False, ""
    cx = filt["rect"][0] + 40
    cy = (filt["rect"][1] + filt["rect"][3]) // 2
    print(f"{LOG} scrolling filament pane at ({cx},{cy}) …")
    for step in range(14):
        winutil.real_wheel_screen(cx, cy, -3)
        time.sleep(0.35)
        rows = m8._screen_ocr_rows(filt["rect"])
        text = " | ".join(t for _y, t, _x in rows)
        print(f"{LOG}  step{step:02d}: {text}")
        seen.append(text)
        if key and key in text.lower():
            print(f"{LOG}  >>> '{key}' 出现在 step{step}！")
            shot(f"s{slot}_hit_step{step:02d}", filt["rect"])
    full = " ".join(seen).lower()
    found = key in full
    print(f"{LOG} slot{slot}: '{key}' present={found}")
    # 再滚回顶部，确认没漏
    for _ in range(16):
        winutil.real_wheel_screen(cx, cy, 3)
        time.sleep(0.1)
    time.sleep(0.4)
    top_rows = m8._screen_ocr_rows(filt["rect"])
    print(f"{LOG} back-to-top rows: {[t for _y, t, _x in top_rows]}")
    esc(2)
    time.sleep(0.5)
    still = [t for t in tops(session.pid) if t[0] == "wxWindowNR"]
    print(f"{LOG} after ESC: {len(still)} wxWindowNR still visible, "
          f"combo_after={m8.combo_text(ch) if ch else None!r}")
    return found, full


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
        print(f"{LOG} pid {p} hwnd=0x{h:X} rect={winutil.window_rect(h)}")
        if not hwnd:
            hwnd, pid = h, p
    if not hwnd:
        print(f"{LOG} FAIL: no main window")
        return 1
    session = AttachedSession(pid, hwnd)
    user32.ShowWindow(hwnd, 3)                     # SW_MAXIMIZE（幂等）
    time.sleep(1.2)
    from m3_common import ensure_gl_ready
    ensure_gl_ready(session)
    slots = m8.wait_slots(session)
    print(f"{LOG} slots: {[(s['slot'], (s['combo'] or [None, None])[0]) for s in slots]}")
    time.sleep(0.5)
    shot("00_slots")
    hits = {}
    for s in slots:
        if s["slot"] > 2:        # 先看 1/2 两个槽就够了
            continue
        found, full = scan_slot(session, s["slot"])
        hits[s["slot"]] = (found, full[:400])
        time.sleep(1.0)
    print(f"{LOG} ==== summary ====")
    for k, v in hits.items():
        print(f"{LOG} slot{k}: rainbow_present={v[0]}")
    print(f"{LOG} app alive: {session.alive()}")
    print(f"{LOG} (attached session left RUNNING on purpose)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
