#!/usr/bin/env python3
# probe_241_picker.py — 2.4.1 耗材选择框只读探针（不做任何选择/不改工程）
#
# 背景（产品文档《准备页——耗材分类管理》V0.1，9-29）: 耗材下拉框改成
#   三大分组（项目预设 / 用户配置 / 系统配置）+ 系统配置内部两级菜单（供应商 → 耗材）；
#   一级顺序 Snapmaker → Generic → 其他厂商字典序；Snapmaker 层 8 项置顶；
#   二次打开要"回显自动定位到已选材料"。
#
# 本探针要回答:
#   Q1 打开选择框后落到哪一层（是否停在一级？是否已按回显停在某个供应商的二级？）
#   Q2 一级都有哪些条目（供应商 / 分组）
#   Q3 Snapmaker 层与 Generic 层的完整名单（含我们的测试包落在哪）
#   Q4 滚轮（消息级 / 真实）在这个弹层上有没有效
#   Q5 选中态/回显在弹层里怎么表现（一级高亮？勾选标记？）
#
# 只读：只打开、滚动、点击切换层级（用层级切换本身作为读取手段，不做最终选择；结束前 Esc）。
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

LOG = "[pk241]"
ART = HERE / "artifacts"


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xP_{name}.png"), img)
    print(f"{LOG} shot -> m8xP_{name}.png")


def popup_lines(pop, tag):
    """(y, text) lines OCR'd from the popup, plus child texts if any."""
    import cv2
    import numpy as np
    pw, ph, pbuf = winutil.capture_window(pop[3])
    img = cv2.cvtColor(np.frombuffer(pbuf, np.uint8).reshape(ph, pw, 4), cv2.COLOR_BGRA2BGR)
    words = mdu.ocr_words_img(img, scale=2, psm=6)
    lines = {}
    for t, x, y, w, h in words:
        key = next((k for k in lines if abs(k - y) <= 12), y)
        lines.setdefault(key, []).append((x, y, t))
    out = []
    for k in sorted(lines):
        v = sorted(lines[k])
        out.append((k, " ".join(t for _x, _y, t in v)))
    print(f"{LOG} --- {tag}: {len(out)} OCR lines ---")
    for y, txt in out:
        print(f"{LOG}   y={y:4d} {txt[:90]}")
    kids = [(t.strip(), r) for t, r, _h in export_util._children_texts(pop[3]) if t.strip()]
    print(f"{LOG}   child texts ({len(kids)}): {[t[:40] for t, _r in kids][:12]}")
    return out


def ensure_foreground(session, tries=3):
    """App must be the foreground window: the combo popup needs activation (2.4.1
    swallows message-level clicks when it is not — same lesson as #125)."""
    for i in range(tries):
        if winutil.user32.GetForegroundWindow() == session.hwnd:
            return True
        # 标题栏点击是最省事的激活方式（对 UI 无副作用）
        click_at(960, 15, 0.8)
        if winutil.user32.GetForegroundWindow() == session.hwnd:
            print(f"{LOG} foreground acquired (attempt {i + 1})")
            return True
    print(f"{LOG} foreground NOT acquired: fg={winutil.user32.GetForegroundWindow()} "
          f"main={session.hwnd}")
    return False


def open_popup(session, cx, cy):
    """先真实点击、再消息点击，任一开出 wx popup 即返回。"""
    for tag in ("real", "msg"):
        if tag == "real":
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.25)
            winutil.real_click_screen(cx, cy)
        else:
            winutil.msg_click_screen(cx, cy, session.hwnd)
        time.sleep(1.2)
        pop = export_util.wait_popup(session.pid, timeout_s=4.0)
        if pop:
            print(f"{LOG} popup opened via {tag} click")
            return pop
        print(f"{LOG} {tag} click did not open a popup")
    return None


def click_at(x, y, pause=1.2):
    winutil.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


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
        print(f"{LOG} slots: {[(s['slot'], s['combo'][0]) for s in slots]}")
        hit = next((s for s in slots if s["slot"] == 2), None)
        if not hit:
            print(f"{LOG} slot 2 not found")
            return 1
        text, rect, ch = hit["combo"]
        cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
        print(f"{LOG} slot2 combo={text!r} rect={rect}")

        # Q1/Q2: 打开选择框，看落在哪一层（需应用在前台）
        ensure_foreground(session)
        pop = open_popup(session, cx, cy)
        if not pop:
            print(f"{LOG} popup did NOT open; fg={winutil.user32.GetForegroundWindow()} "
                  f"main={session.hwnd} — 试一次标题栏激活后重开")
            ensure_foreground(session)
            pop = open_popup(session, cx, cy)
        if not pop:
            print(f"{LOG} popup STILL not open — 放弃")
            return 1
        print(f"{LOG} popup rect={pop[2]}")
        shot("01_popup_open", pop[2])
        lines = popup_lines(pop, "open (level?)")

        # Q4: 滚轮有效性（先消息级，再真实滚轮）
        before = " | ".join(t for _y, t in lines)
        pr = pop[2]
        for i in range(6):
            winutil.msg_click_screen(cx, cy, session.hwnd)          # ensure focus
            winutil.msg_wheel_screen(pr[0] + 40, (pr[1] + pr[3]) // 2, 120 * 3, pop[3]) \
                if hasattr(winutil, "msg_wheel_screen") else None
            time.sleep(0.2)
        lines2 = popup_lines(pop, "after message-wheel")
        print(f"{LOG} message-wheel changed content: {(' | '.join(t for _y, t in lines2) != before)}")
        for i in range(6):
            winutil.real_wheel_screen(pr[0] + 40, (pr[1] + pr[3]) // 2, 3)
            time.sleep(0.2)
        lines3 = popup_lines(pop, "after real-wheel")
        print(f"{LOG} real-wheel changed content: {(' | '.join(t for _y, t in lines3) != ' | '.join(t for _y, t in lines2))}")
        shot("02_after_scroll", pop[2])

        # Q3: 逐条点一级条目（Snapmaker / Generic / 其他）读取二级
        for want in ("Snapmaker", "Generic", "Polymaker", "自定义", "项目"):
            row = next(((y, t) for y, t in lines if want.lower() in t.lower()), None)
            if not row:
                row = next(((y, t) for y, t in lines3 if want.lower() in t.lower()), None)
            if not row:
                print(f"{LOG} level-1 entry {want!r} not visible in the current OCR")
                continue
            y, t = row
            click_at(pr[0] + 60, y + 8)          # 点该行左侧（文本起点附近）
            time.sleep(1.2)
            shot(f"03_{want}", pr)
            popup_lines(pop, f"after clicking {want!r}")
        # 收尾：Esc 关掉弹层，不下任何选择
        winutil.user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        winutil.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.8)
        print(f"{LOG} slot2 combo after probe: {m8.combo_text(ch)!r}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
