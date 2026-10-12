#!/usr/bin/env python3
# probe_241_chip2.py — 2.4.1：定位"官方色卡对话框"的真实入口。
#
# j385 实测：slot1（Generic PETG，非官方）chip 点击 -> 原生 'Please choose the filament color'；
# slot2（Snapmaker PLA Silk，官方）chip 点击 3 次 -> **什么都没有**。
# 本轮加 WindowFromPoint 诊断（点到底落在哪个窗口上）+ 先清场再点 + 多种候选点位：
#   a) chip 中心 / b) chip 左上偏 / c) 双击 / d) 16x25 按钮 / e) combo
# 全程 dump 新 toplevels；**不关闭 app**。
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

if sys.stdout is not None:            # pythonw 下 stdout 是 None
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 用 pythonw.exe 跑（没有控制台窗口）—— 客机桌面上的控制台会**盖住 app 并吞掉真实点击**
# （实测 10-12：scheduled task 里 cmd /c 起的 Windows Terminal 窗口 WindowFromPoint
#  抢走了槽位行的每一次点击，症状酷似"控件没响应"）。pythonw 没有 stdout，所以 probe
# 自己把输出 tee 到 artifacts/<name>.log。
_LOG_NAME = "pchip2.log"


def _tee_log(name):
    import sys as _s
    from pathlib import Path as _P
    p = _P(__file__).resolve().parents[1] / "artifacts" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fh = open(p, "w", encoding="utf-8", errors="replace")

    class _T:
        def write(self, s):
            fh.write(s)
            fh.flush()
            try:
                if _s.__stdout__ is not None:
                    _s.__stdout__.write(s)
            except Exception:                                  # noqa: BLE001
                pass

        def flush(self):
            fh.flush()

    _s.stdout = _T()
    _s.stderr = _T()


_tee_log(_LOG_NAME)

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pchip2]"
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
                       cv2.COLOR_BGR2BGRA if False else cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"pchip2_{name}.png"), img)
    print(f"{LOG} shot -> pchip2_{name}.png")


def whois(x, y):
    h = winutil.window_from_screen_point(x, y)
    if not h:
        return f"<no window at ({x},{y})>", 0
    rc = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(rc))
    tid = wt.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(tid))
    return (f"{winutil.window_class(h)!r} '{winutil.window_title(h)}' "
            f"rect=({rc.left},{rc.top},{rc.right},{rc.bottom}) hwnd=0x{h:X} pid={tid.value}"), tid.value


def esc(n=1):
    for _ in range(n):
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.5)


def click_and_dump(session, tag, x, y, double=False):
    before = {t[3] for t in tops(session.pid)}
    info, hwnd_pid = whois(x, y)
    print(f"{LOG} --- {tag}: click ({x},{y}) double={double}")
    print(f"{LOG}     WindowFromPoint -> {info}")
    if hwnd_pid != session.pid:
        print(f"{LOG}     !! 该点不属于被测 app（pid={hwnd_pid} != {session.pid}）"
              f"—— 点击会被别的窗口吞掉（控制台/远控层）")
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.3)
    winutil.real_click_screen(int(x), int(y))
    if double:
        time.sleep(0.12)
        winutil.real_click_screen(int(x), int(y))
    time.sleep(1.6)
    new = [t for t in tops(session.pid) if t[3] not in before
           and t[0] not in ("tooltips_class32", "SysShadow")]
    print(f"{LOG}     new toplevels: {[(t[0], t[1], t[2]) for t in new]}")
    for cls, title, rect, hwnd in new:
        kids = [k.strip() for k, _r, _h in export_util._children_texts(hwnd) if k.strip()]
        print(f"{LOG}       {cls!r} {title!r} kids({len(kids)}): {kids[:16]}")
    return new


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
    print(f"{LOG} visible toplevels BEFORE cleanup:")
    for cls, title, rect, h in tops(pid):
        print(f"{LOG}   {cls!r} {title!r} {rect}")
    esc(3)
    time.sleep(0.8)
    print(f"{LOG} visible toplevels AFTER ESC x3:")
    for cls, title, rect, h in tops(pid):
        print(f"{LOG}   {cls!r} {title!r} {rect}")
    slots = m8.wait_slots(session)
    print(f"{LOG} slots: {[(s['slot'], m8.combo_text(s['combo'][2]) if s['combo'] else None, s['swatch'], s['picker']) for s in slots]}")
    hit = next((s for s in slots if s["slot"] == 2), None)
    if not hit:
        print(f"{LOG} slot2 missing")
        return 1
    sx0, sy0, sx1, sy1 = hit["swatch"]
    cx, cy = (sx0 + sx1) // 2, (sy0 + sy1) // 2
    shot("00_row_before", (sx0 - 12, sy0 - 12, sx1 + 230, sy1 + 12))
    click_and_dump(session, "chip-center", cx, cy)
    click_and_dump(session, "chip-left-top", sx0 + 4, sy0 + 4)
    click_and_dump(session, "chip-double", cx, cy, double=True)
    if hit.get("picker"):
        px0, py0, px1, py1 = hit["picker"]
        click_and_dump(session, "picker16x25", (px0 + px1) // 2, (py0 + py1) // 2)
    if hit.get("combo"):
        _t, r, _ch = hit["combo"]
        click_and_dump(session, "combo", (r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    esc(3)
    print(f"{LOG} final visible toplevels:")
    for cls, title, rect, h in tops(pid):
        print(f"{LOG}   {cls!r} {title!r} {rect}")
    print(f"{LOG} app alive: {session.alive()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
