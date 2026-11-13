#!/usr/bin/env python3
# m8x_221.py — 飞书基线 #221: 【划线模式】近程挤出机下切换划线模式生成
# 校准件，打印数字默认勾选，切片成功
# feishu: baseline#221
# 行文: 校准 > 压力提前 → 挤出机类型保持近程（DDE）→ 方法切 PA Line
#       → 默认 0 / 0.1 / 0.002，Print numbers 勾选且可编辑 → 确定生成
#       划线形校准模型 → 完整落板、可选中 → 切片成功
#
# 入口/对话框：probe_242_pa207 标定 #32770 'PA Calibration'：Extruder type
# DDE/Bowden、Method PA Tower/PA Line/PA Pattern（圆点在标签左侧空 Static），
# Start PA/End PA/PA step 三个 Edit + Print numbers 复选框（同排 Button）+ OK。
# 判定：方法切 PA Line 的证据 = Print numbers 由未勾选变为勾选且可编辑
# （三种方法中仅 PA Line 可编辑）；字段回读 0/0.1/0.002；确定后模型落板、
# 对话框关闭；对象行选中；切片成功。PA 档位生效性核验不在本轮。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x221]"
PA_TITLE = "pa calibration"
BM_GETCHECK = 0x00F0


def main() -> int:
    import argparse
    import m7_common as m7
    from m3_common import add_common_args, boot_session
    from harness import export_util, mix_dialog_util as mdu, topbar_util, winutil
    from harness.anchors import capture_bgr as _cap

    user32 = winutil.user32

    def real_click(x, y):
        user32.SetCursorPos(x, y)
        time.sleep(0.25)
        winutil.real_click_screen(x, y, hold_ms=60)

    def pa_dialog():
        for cls, t, r, h in m7._visible_toplevels(session.pid):
            if cls == "#32770" and PA_TITLE in (t or "").lower():
                return (cls, t, r, h)
        return None

    def open_pa():
        menu = topbar_util.open_calibration_menu(session)
        if not menu:
            return None
        rect, _mhwnd, hm = menu
        idx = topbar_util.find_item(hm, "pressure advance")
        if idx is None:
            return None
        cx = (rect[0] + rect[2]) // 2
        for y in topbar_util.submenu_row_candidates(
                rect, len(topbar_util.menu_items(hm)), idx):
            real_click(cx, y)
            time.sleep(1.5)
            d = pa_dialog()
            if d:
                return d
        return None

    def field_by_label(dlg, label):
        kids = export_util._children_texts(dlg[3])
        lab = next(((t, r) for t, r, h in kids
                    if t.strip().lower().startswith(label)), None)
        if not lab:
            return None
        ly = (lab[1][1] + lab[1][3]) // 2
        for t, r, h in kids:
            if winutil.window_class(h) == "Edit" and \
                    abs(((r[1] + r[3]) // 2) - ly) <= 14 and \
                    user32.IsWindowVisible(h):
                return h
        return None

    def checkbox_by_label(dlg, label):
        kids = export_util._children_texts(dlg[3])
        lab = next(((t, r) for t, r, h in kids
                    if t.strip().lower() == label), None)
        if not lab:
            return None
        ly = (lab[1][1] + lab[1][3]) // 2
        for t, r, h in kids:
            if winutil.window_class(h) == "Button" and \
                    abs(((r[1] + r[3]) // 2) - ly) <= 14 and \
                    user32.IsWindowVisible(h):
                return h
        return None

    def radio_click(dlg, label):
        """Click the radio circle left of the label (empty Static)."""
        kids = export_util._children_texts(dlg[3])
        lab = next(((t, r) for t, r, h in kids if t.strip() == label), None)
        if not lab:
            return False
        ly = (lab[1][1] + lab[1][3]) // 2
        circles = [r for t, r, h in kids
                   if not t.strip()
                   and winutil.window_class(h) in ("Static", "Button")
                   and abs(((r[1] + r[3]) // 2) - ly) <= 12
                   and lab[1][0] - 40 < r[0] < lab[1][0]
                   and (r[2] - r[0]) <= 30]
        if circles:
            r = circles[0]
            real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
        else:
            real_click((lab[1][0] + lab[1][2]) // 2, ly)
        return True

    def ok_button(dlg):
        for t, r, h in export_util._children_texts(dlg[3]):
            if t.strip().lower() == "ok" and user32.IsWindowVisible(h):
                return h, r
        return None, None

    def click_ok(dlg):
        h, r = ok_button(dlg)
        if not h:
            return False
        real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
        return True

    def step_import_dialog():
        for cls, t, r, h in m7._visible_toplevels(session.pid):
            if cls == "#32770" and "step file import" in (t or "").lower():
                return (cls, t, r, h)
        return None

    def accept_step_import():
        d = step_import_dialog()
        if not d:
            return False
        for t, r, h in export_util._children_texts(d[3]):
            if t.strip().lower() == "ok" and user32.IsWindowVisible(h):
                real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
                print(f"{LOG} STEP import parameters accepted")
                return True
        return False

    def click_ok_and_import(dlg):
        step_ok = False
        for _attempt in (1, 2):
            click_ok(dlg)
            time.sleep(1.5)
            end = time.monotonic() + 8
            while time.monotonic() < end:
                if accept_step_import():
                    step_ok = True
                    break
                if not pa_dialog():
                    break
                time.sleep(0.5)
            if step_ok or not pa_dialog():
                break
        return step_ok

    def wait_model(frac0, timeout_s=90.0):
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            f = m7.model_colored_frac(session)
            if f > max(frac0 + 0.003, frac0 * 2):
                return f
            time.sleep(1.0)
        return m7.model_colored_frac(session)

    def ocr_band(y0, y1, x0=0, x1=430, scale=4):
        img = _cap(session)
        crop = img[max(0, y0):y1, x0:x1]
        if crop.size == 0:
            return []
        return [(w[0], w[1] + x0, w[2] + y0, w[3], w[4])
                for w in mdu.ocr_words_img(crop, scale=scale)]

    def select_model_row():
        rows = export_util._children_texts(session.hwnd)
        proc = next(((t, r) for t, r, h in rows if t.strip() == "Process"),
                    None)
        adv = next(((t, r) for t, r, h in rows if t.strip() == "Advanced"),
                   None)
        if not (proc and adv):
            return None, None
        y0, y1 = proc[1][1] - 8, proc[1][3] + 8
        band = ocr_band(y0, y1, scale=3)
        objw = next((w for w in band if "bject" in w[0].lower()), None)
        if not objw:
            return None, None
        real_click(objw[1] + objw[3] // 2, objw[2] + objw[4] // 2)
        time.sleep(1.5)
        sx, sy = m7.client(session, 200, (y1 + 780) // 2)
        user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        winutil.real_wheel_screen(sx, sy, 6)
        time.sleep(1.0)
        words = ocr_band(y1 + 2, 800, scale=4)
        lines = {}
        for t, x, y, w, h in words:
            key = next((k for k in lines if abs(k - y) <= 10), y)
            lines.setdefault(key, []).append((x, t, y, h, w))
        plate_y = outside_y = None
        for k in sorted(lines):
            text = " ".join(p[1] for p in sorted(lines[k])).lower()
            print(f"{LOG}   y={k}: {text}")
            if "plate" in text and "search" not in text \
                    and plate_y is None:
                plate_y = k
            if "outside" in text and outside_y is None:
                outside_y = k
        if plate_y is None:
            return None, None
        tower_y = (plate_y + outside_y) // 2 + 8 \
            if (outside_y and outside_y > plate_y + 10) else plate_y + 30
        cx = 200
        if outside_y:
            real_click(*m7.client(session, cx, outside_y + 8))
            time.sleep(1.0)
        cleared = not m7.object_selected(session)
        real_click(*m7.client(session, cx, tower_y))
        time.sleep(1.2)
        sel = m7.object_selected(session)
        if not sel:
            real_click(*m7.client(session, cx, tower_y))
            time.sleep(1.2)
            sel = m7.object_selected(session)
        return cleared, sel

    ap = add_common_args(argparse.ArgumentParser())  # 空床
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        frac0 = m7.model_colored_frac(session)
        print(f"{LOG} bed frac0={frac0:.4%}")
        dlg = open_pa()
        results["PA Calibration 对话框打开"] = "PASS" if dlg else "FAIL (no dialog)"
        if not dlg:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        switched = radio_click(dlg, "PA Line")
        time.sleep(1.5)
        start = field_by_label(dlg, "start pa")
        end = field_by_label(dlg, "end pa")
        step = field_by_label(dlg, "pa step")
        pn = checkbox_by_label(dlg, "print numbers")
        results["切换到 PA Line（圆点）"] = "PASS" if switched else "FAIL (label)"
        vals = tuple(winutil.edit_text(h).strip()
                     for h in (start, end, step)) if all((start, end, step)) else ()
        print(f"{LOG} start/end/step={vals} pn={pn}")
        results["默认 0 / 0.1 / 0.002"] = (
            "PASS" if vals == ("0", "0.1", "0.002") else f"FAIL ({vals})")
        pn_state = user32.SendMessageW(pn, BM_GETCHECK, 0, 0) if pn else -1
        pn_enabled = bool(user32.IsWindowEnabled(pn)) if pn else False
        print(f"{LOG} Print numbers state={pn_state} enabled={pn_enabled}")
        results["Print numbers 勾选且可编辑"] = (
            "PASS" if pn_state == 1 and pn_enabled else
            f"FAIL (state={pn_state} enabled={pn_enabled})")

        step_ok = click_ok_and_import(dlg)
        frac = wait_model(frac0)
        print(f"{LOG} bed frac after OK={frac:.4%} step_import={step_ok}")
        results["点击确定后生成划线校准模型"] = (
            "PASS" if frac > max(frac0 + 0.003, frac0 * 2) else
            f"FAIL (frac {frac0:.4%} -> {frac:.4%})")
        results["确定后对话框关闭"] = (
            "PASS" if not pa_dialog() else "FAIL (dialog still open)")
        if frac <= max(frac0 + 0.003, frac0 * 2):
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        deselected, selected = select_model_row() or (None, None)
        results["点击 Outside 行清除选择"] = (
            "PASS" if deselected else "FAIL (still selected)")
        results["划线模型对象行可单独选中"] = (
            "PASS" if selected else "FAIL (info panel empty)")
        m7.op_slice(session, results, key="PA 划线模式切片")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
