#!/usr/bin/env python3
# ⚠️ 入口已过时（10-12）：2.4.1 上槽位行 16x25 按钮**不再开 Edit/Delete 菜单**，
#    改开供应商列表；用户预设的真正落点是双栏框左栏的
#    ------ User presets ------ → Custom »，且右栏行文本被截断、全名只在 hover
#    tooltip 里（见 probe_241_usergroup.py 与 PITFALLS §21）。
# probe_241_editor_preset.py — 2.4.1 备用路径：Material settings 对话框里的预设下拉能否选到用户预设
#
# 背景：侧边栏双栏选择框的左栏只显示 System presets 段（测试方口径：用户预设要
# 「用户配置 → 自定义」，且**仅当槽位本身就是用户预设时**才出现——鸡生蛋问题）。
# 老路径：槽位行的 16x25 Button → 菜单(Edit) → Material settings 对话框，对话框里
# 有一个**预设下拉**（2.4.0 时代就是它/侧栏 combo 用的同一控件）。本轮验证它能不能选到
# 我们的用户预设（... - STD-TEST）。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))
sys.path.insert(0, str(HERE / "tests" / "topcap"))

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
import m8x_137_flow_param_tabs as c137  # noqa: E402

LOG = "[pk251]"
ART = HERE / "artifacts"


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xPB_{name}.png"), img)
    print(f"{LOG} shot -> m8xPB_{name}.png")


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

        dlg = c137.open_editor(session, slot=2)
        print(f"{LOG} Material settings dialog: {dlg[1] if dlg else None} {dlg[2] if dlg else ''}")
        if not dlg:
            return 1
        shot("01_editor", dlg[2])
        # 对话框里的预设下拉（宽控件，文本含 'Snapmaker' 或 '@U1'）
        cands = [(t.strip(), r, winutil.window_class(h)) for t, r, h in export_util._children_texts(dlg[3])
                 if (r[2] - r[0]) > 120 and 20 <= r[1] - dlg[2][1] <= 100]
        print(f"{LOG} dialog top controls: {[(t[:34], r) for t, r, c in cands][:8]}")
        combo = next(((t, r) for t, r, c in cands if '@U1' in t or 'nozzle' in t or 'Snapmaker' in t), None)
        print(f"{LOG} preset combo: {combo}")
        if not combo:
            return 1
        t, r = combo
        cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.3)
        winutil.real_click_screen(cx, cy)
        time.sleep(1.5)
        pop = export_util.wait_popup(session.pid, timeout_s=4.0)
        print(f"{LOG} combo popup: {pop[2] if pop else None}")
        if pop:
            rows = m8._screen_ocr_rows(pop[2])
            print(f"{LOG} popup rows ({len(rows)}): {[t2[:40] for _y, t2, _x in rows][:18]}")
            hits = [t2 for _y, t2, _x in rows if 'TEST' in t2.upper()]
            print(f"{LOG} hits: {hits}")
            shot("02_combo_popup", pop[2])
            # 键盘路径：End 跳到底（User presets 段通常在末尾）、Home 回顶、首字母跳转
            import ctypes as _c
            u = _c.WinDLL("user32", use_last_error=True)
            def tap(vk, n=1):
                for _ in range(n):
                    u.keybd_event(int(vk), 0, 0, 0); time.sleep(0.04)
                    u.keybd_event(int(vk), 0, 2, 0); time.sleep(0.12)
            for tag, keys in (("End", [0x23]), ("Home", [0x24]),
                              ("type 'Snapmaker PLA S'", [0x53, 0x4E, 0x41, 0x50, 0x4D])):
                tap(keys[0]) if len(keys) == 1 else [tap(k) for k in keys]
                time.sleep(0.8)
                rows_k = m8._screen_ocr_rows(pop[2])
                hits = [t2 for _y, t2, _x in rows_k if 'TEST' in t2.upper()]
                print(f"{LOG} key {tag}: rows={[t2[:34] for _y, t2, _x in rows_k][:8]} hits={hits}")
                if hits:
                    rows = rows_k
                    shot(f"05_key_{tag.split()[0]}", pop[2])
                    break
            if not hits:      # 往下滚（真实滚轮；2.4.0 时代该列表就无视消息级滚轮）
                px = (pop[2][0] + pop[2][2]) // 2
                py = (pop[2][1] + pop[2][3]) // 2
                for step in range(40):
                    for _i in range(4):
                        winutil.real_wheel_screen(px, py, -3)
                        time.sleep(0.08)
                    time.sleep(0.4)
                    rows2 = m8._screen_ocr_rows(pop[2])
                    hits = [t2 for _y, t2, _x in rows2 if 'TEST' in t2.upper()]
                    secs = [t2 for _y, t2, _x in rows2 if t2.strip().startswith('------')]
                    if step % 6 == 0 or hits:
                        print(f"{LOG} scroll {step}: sections={secs} rows={[t2[:30] for _y, t2, _x in rows2][:6]} hits={hits}")
                    if hits:
                        rows = rows2
                        shot(f"04_found_step{step}", pop[2])
                        break
            if hits:
                got = m8._picker_click_text(session, rows, hits[0][:24], skip_echo=False)
                time.sleep(1.5)
                print(f"{LOG} clicked {got!r}; dialog combo now: "
                      f"{[(t3.strip()[:40]) for t3, r3, h3 in export_util._children_texts(dlg[3]) if (r3[2]-r3[0])>120][:4]}")
                shot("03_after_pick", dlg[2])
        c137.real_keys(0x1B)
        time.sleep(1.2)
        slots = m8.wait_slots(session)
        print(f"{LOG} sidebar slots after: {[(s['slot'], s['combo'][0]) for s in slots]}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
