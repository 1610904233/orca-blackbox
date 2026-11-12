#!/usr/bin/env python3
# m8x_213.py — 飞书基线 #213: 【最大体积流量】默认 5~20 mm³/s 步长 0.5
# 生成测试件，切片成功
# feishu: baseline#213
# 行文: 校准 > 最大体积流量 → 默认 Start 5 / End 20 / Step 0.5（mm³/s）
#       → 确定加载预置模板生成测试件 → 完整落板、可选中 → 切片成功无报错
#
# 入口/对话框：probe_242_maxflow213 标定 #32770
#   'Max volumetric speed test'：Start/End volumetric speed + Step 三个 Edit
#   （mm³/s）+ OK。
# 判定：字段回读 5 / 20 / 0.5；确定后模型落板（相对 gate）、对话框关闭；
#   Objects 行可单独选中（Outside 清选 → 模型行选中）；切片成功。
# 体积流量档位生效性核验不在本轮（飞书注明，待后续 gcode 手段）。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x213]"
DIALOG_TITLE = "max volumetric speed test"


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

    def maxflow_dialog():
        for cls, t, r, h in m7._visible_toplevels(session.pid):
            if cls == "#32770" and DIALOG_TITLE in (t or "").lower():
                return (cls, t, r, h)
        return None

    def open_maxflow():
        menu = topbar_util.open_calibration_menu(session)
        if not menu:
            return None
        rect, _mhwnd, hm = menu
        idx = topbar_util.find_item(hm, "max flowrate")
        if idx is None:
            return None
        cx = (rect[0] + rect[2]) // 2
        for y in topbar_util.submenu_row_candidates(
                rect, len(topbar_util.menu_items(hm)), idx):
            real_click(cx, y)
            time.sleep(1.5)
            d = maxflow_dialog()
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
        """'Step file import parameters' #32770 raised by importing the
        STEP-based SpeedTestStructure template (probe_242_maxflow213b)."""
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
        """OK → accept the STEP import dialog that appears (defaults), retry
        once if the first OK click is swallowed."""
        step_ok = False
        for _attempt in (1, 2):
            click_ok(dlg)
            time.sleep(1.5)
            end = time.monotonic() + 8
            while time.monotonic() < end:
                if accept_step_import():
                    step_ok = True
                    break
                if not maxflow_dialog():
                    break
                time.sleep(0.5)
            if step_ok or not maxflow_dialog():
                break
        return step_ok

    def wait_model(frac0, timeout_s=45.0):
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
            print(f"{LOG} Process/Advanced labels missing")
            return None, None
        y0, y1 = proc[1][1] - 8, proc[1][3] + 8
        band = ocr_band(y0, y1, scale=3)
        objw = next((w for w in band if "bject" in w[0].lower()), None)
        if not objw:
            print(f"{LOG} no Objects tab")
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
            parts = sorted(lines[k])
            text = " ".join(p[1] for p in parts).lower()
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
        pre = m7.object_selected(session)
        print(f"{LOG} selected before row click={pre} tower_y={tower_y}")
        if outside_y:
            real_click(*m7.client(session, cx, outside_y + 8))
            time.sleep(1.0)
        cleared = not m7.object_selected(session)
        print(f"{LOG} cleared by Outside row={cleared}")
        real_click(*m7.client(session, cx, tower_y))
        time.sleep(1.2)
        sel = m7.object_selected(session)
        if not sel:
            print(f"{LOG} first row click missed — retrying")
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
        dlg = open_maxflow()
        results["Max volumetric speed test 对话框打开"] = (
            "PASS" if dlg else "FAIL (no dialog)")
        if not dlg:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        start = field_by_label(dlg, "start volumetric speed")
        end = field_by_label(dlg, "end volumetric speed")
        step = field_by_label(dlg, "step")
        results["Start/End/Step 字段可定位"] = (
            "PASS" if all((start, end, step)) else
            f"FAIL (start={bool(start)} end={bool(end)} step={bool(step)})")
        if not all((start, end, step)):
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)
        vals = tuple(winutil.edit_text(h).strip()
                     for h in (start, end, step))
        print(f"{LOG} start/end/step={vals}")
        results["默认 5 / 20 / 0.5"] = (
            "PASS" if vals == ("5", "20", "0.5") else f"FAIL ({vals})")

        step_ok = click_ok_and_import(dlg)
        results["STEP 导入参数对话框（接受默认）"] = (
            "PASS" if step_ok else "PASS (no STEP dialog)")
        frac = wait_model(frac0, timeout_s=90)
        print(f"{LOG} bed frac after OK={frac:.4%}")
        results["点击确定后生成最大体积流量测试件"] = (
            "PASS" if frac > max(frac0 + 0.003, frac0 * 2) else
            f"FAIL (frac {frac0:.4%} -> {frac:.4%})")
        results["确定后对话框关闭"] = (
            "PASS" if not maxflow_dialog() else "FAIL (dialog still open)")
        if frac <= max(frac0 + 0.003, frac0 * 2):
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        deselected, selected = select_model_row() or (None, None)
        results["点击 Outside 行清除选择"] = (
            "PASS" if deselected else "FAIL (still selected)")
        results["测试件对象行可单独选中"] = (
            "PASS" if selected else "FAIL (info panel empty)")
        m7.op_slice(session, results, key="最大体积流量切片")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
