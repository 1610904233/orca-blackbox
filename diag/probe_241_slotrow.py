#!/usr/bin/env python3
# probe_241_slotrow.py — 2.4.1：槽位行各控件逐个点击 -> 报告各自打开了什么。
#
# 背景：2.4.0 时代槽位行最右的 16x25 Button 开的是 Edit/Delete/Merge 菜单
# （m8b 的取色链：menu -> Edit -> Material settings -> colourpicker -> 官方色卡），
# 2.4.1 上这个按钮改开**供应商列表**了。本轮实测每个控件的新语义：
#   (a) 数字色块（chip）  (b) 16x25 按钮（picker）  (c) combo  (d) 行上右键
#   (e) 供应商列表左栏的 '------ Add/Remove filament ------' 行
# 只读探查：每次都 ESC 复原；**不关闭 app**。
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

LOG = "[pslot]"
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
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"pslot_{name}.png"), img)
    print(f"{LOG} shot -> pslot_{name}.png")


def esc(n=1):
    for _ in range(n):
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.55)


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


def describe_new(pid, before_hwnds, tag, max_kids=18):
    new = [t for t in tops(pid) if t[3] not in before_hwnds
           and t[0] not in ("tooltips_class32", "SysShadow")]
    print(f"{LOG}   [{tag}] new toplevels: {[(t[0], t[1], t[2]) for t in new]}")
    for cls, title, rect, hwnd in new:
        kids = [k.strip() for k, _r, _h in export_util._children_texts(hwnd) if k.strip()]
        print(f"{LOG}   [{tag}]   {cls!r} {title!r} kids({len(kids)}): {kids[:max_kids]}")
        if cls == "#32768":
            try:
                import m7_common as m7
                print(f"{LOG}   [{tag}]   menu items: {m7.list_menu(hwnd)}")
            except Exception as exc:                           # noqa: BLE001
                print(f"{LOG}   [{tag}]   menu items <{exc!r}>")
    return new


def real_click(x, y, pause=1.4):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def row_controls(session, slot=2):
    slots = m8.wait_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit:
        return None, []
    chip = hit["swatch"]
    cy = (chip[1] + chip[3]) // 2
    out = []
    for text, rect, ch in export_util._children_texts(session.hwnd):
        ry = (rect[1] + rect[3]) / 2
        if abs(ry - cy) <= 14 and rect[0] < 520:
            out.append((text.strip(), rect, ch, winutil.window_class(ch)))
    out.sort(key=lambda z: z[1][0])
    return hit, out


def main() -> int:
    pids = find_running()
    if not pids:
        print(f"{LOG} FAIL: no snapmaker-orca running")
        return 1
    hwnd = 0
    pid = pids[0]
    for p in pids:
        try:
            h = winutil.find_main_window(p, timeout_s=20.0)
        except Exception:                                      # noqa: BLE001
            continue
        if not hwnd:
            hwnd, pid = h, p
    session = AttachedSession(pid, hwnd)
    print(f"{LOG} pid={pid} hwnd=0x{hwnd:X} rect={winutil.window_rect(hwnd)}")
    user32.ShowWindow(hwnd, 3)
    time.sleep(1.2)
    hit, ctrls = row_controls(session, 2)
    if not hit:
        print(f"{LOG} slot2 not found")
        return 1
    print(f"{LOG} slot2 combo={m8.combo_text(hit['combo'][2])!r} chip={hit['swatch']} picker={hit['picker']}")
    print(f"{LOG} row controls ({len(ctrls)}):")
    for text, rect, ch, cls in ctrls:
        print(f"{LOG}   {text[:36]!r:40} {rect} {cls!r} {rect[2]-rect[0]}x{rect[3]-rect[1]}")
    shot("00_row", (min(c[1][0] for c in ctrls) - 10, hit['swatch'][1] - 10,
                    max(c[1][2] for c in ctrls) + 10, hit['swatch'][3] + 10))

    # 逐个点击**右半部分的非 combo 控件**（chip 本身最左、combo 最宽，跳过 combo 文本区）
    probes = []
    if hit.get("picker"):
        probes.append(("picker_16x25", hit["picker"]))
    probes.append(("chip", hit["swatch"]))
    for text, rect, ch, cls in ctrls:
        w = rect[2] - rect[0]
        if cls in ("Button", "wxWindowNR", "wxWindow") and 12 <= w <= 32 \
                and rect[0] > hit["swatch"][2]:
            if hit.get("picker") and rect == hit["picker"]:
                continue
            probes.append((f"small_{rect[0]}", rect))
    seen_rects = set()
    for tag, rect in probes:
        key = (rect[0], rect[1])
        if key in seen_rects:
            continue
        seen_rects.add(key)
        cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
        before = {t[3] for t in tops(pid)}
        print(f"{LOG} --- {tag}: real click ({cx},{cy}) rect={rect}")
        real_click(cx, cy)
        new = describe_new(pid, before, tag)
        if new:
            shot(f"01_{tag}", (min(n[2][0] for n in new) - 8, min(n[2][1] for n in new) - 8,
                               max(n[2][2] for n in new) + 8, max(n[2][3] for n in new) + 8))
        esc(2)
        print(f"{LOG}   after ESC: combo={m8.combo_text(hit['combo'][2])!r}")

    # 行上右键（msg 右键：真右键被远控层吞，PITFALLS #4）
    from harness import add_shape
    cx, cy = (hit["swatch"][0] + hit["swatch"][2]) // 2, (hit["swatch"][1] + hit["swatch"][3]) // 2
    before = {t[3] for t in tops(pid)}
    print(f"{LOG} --- msg right-click on row ({cx},{cy})")
    add_shape.msg_rclick_screen(session, cx, cy)
    time.sleep(1.2)
    describe_new(pid, before, "row_rclick")
    esc(2)

    # 供应商列表里的 Add/Remove filament 行
    print(f"{LOG} --- vendor list: 'Add/Remove filament' row")
    pop, ch, how = m8._picker_open(session, 2)
    print(f"{LOG}   picker open={bool(pop)} via {how!r}")
    if pop:
        time.sleep(0.8)
        panes = m8._picker_panes(session)
        vend = next((p for p in panes if p["is_vendor"]), None)
        if vend:
            rows = vend["rows"]
            print(f"{LOG}   left rows: {[t for _y, t, _x in rows]}")
            tgt = next(((y, t, x) for y, t, x in rows if "add/remove" in t.lower()), None)
            if tgt:
                y, t, x = tgt
                before = {tt[3] for tt in tops(pid)}
                print(f"{LOG}   click {t!r} @({max(20, x) + 60},{y})")
                real_click(max(20, x) + 60, y, 1.8)
                describe_new(pid, before, "add_remove", max_kids=24)
                shot("02_add_remove")
            else:
                print(f"{LOG}   'add/remove' row not in OCR rows")
        esc(2)
    print(f"{LOG} app alive: {session.alive()}")
    print(f"{LOG} (attached session left RUNNING)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
