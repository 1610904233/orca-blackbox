#!/usr/bin/env python3
# m8x_222.py — 飞书基线 #222: 【V形模式】近程挤出机下切换 V 形模式生成
# 校准件，加速度/速度可填，切片成功
# feishu: baseline#222
# 行文: 校准 > 压力提前 → 挤出机类型保持近程（DDE）→ 方法切 PA Pattern
#       （V形模式）→ 默认 0 / 0.08 / 0.005，Print numbers 勾选但禁用，
#       加速度/速度可填（留空即可继续）→ 确定生成 V 形模型 → 完整落板、
#       可选中 → 切片成功
#
# 入口/对话框：probe_242_pa207 / probe_242_pa222 标定 #32770
# 'PA Calibration'：Method PA Tower/PA Line/PA Pattern（圆点在标签左侧空
# Static），Start PA/End PA/PA step + Print numbers（owner-drawn 复选框）+
# Accelerations/Speeds + OK。
# 判态：owner-drawn 复选框 BM_GETCHECK 恒 0；实测（probe_242_pa222b）：
#   未勾选（PA Tower）teal=0 dark=0；
#   启用勾选（PA Line）teal≈130 dark≈133；
#   禁用勾选（PA Pattern）teal=0 dark=13（灰色勾，用户截图确认）。
#   故 checked = teal>=50 或 dark>=5；enabled 单独读 IsWindowEnabled。
# PA 档位生效性核验不在本轮。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x222]"
PA_TITLE = "pa calibration"


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

    def kids():
        return export_util._children_texts(dlg[3])

    def field_by_label(label):
        lab = next(((t, r) for t, r, h in kids()
                    if t.strip().lower().startswith(label)), None)
        if not lab:
            return None
        ly = (lab[1][1] + lab[1][3]) // 2
        for t, r, h in kids():
            if winutil.window_class(h) == "Edit" and \
                    abs(((r[1] + r[3]) // 2) - ly) <= 14 and \
                    user32.IsWindowVisible(h):
                return h
        return None

    def radio_click(label):
        lab = next((r for t, r, h in kids() if t.strip() == label), None)
        if not lab:
            return False
        ly = (lab[1][1] + lab[1][3]) // 2
        circles = [r for t, r, h in kids()
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

    def pn_state_visual():
        """(checked, enabled): owner-drawn box; teal for enabled-checked,
        dark gray tick for disabled-checked (probe_242_pa222b)."""
        import numpy as np
        lab = next(((t, r) for t, r, h in kids()
                    if t.strip().lower() == "print numbers"), None)
        if not lab:
            return None, False
        ly = (lab[1][1] + lab[1][3]) // 2
        btn = next(((r, h) for t, r, h in kids()
                    if winutil.window_class(h) == "Button"
                    and abs(((r[1] + r[3]) // 2) - ly) <= 14
                    and user32.IsWindowVisible(h)), None)
        if not btn:
            return None, False
        br, bh = btn
        cx0, cy0 = winutil.client_to_screen(dlg[3], 0, 0)
        w, h, bgra = winutil.capture_window(dlg[3])
        img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
        x0, y0 = max(0, br[0] - cx0), max(0, br[1] - cy0)
        x1, y1 = min(w, br[2] - cx0), min(h, br[3] - cy0)
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            return None, bool(user32.IsWindowEnabled(bh))
        inner = crop[3:-3, 3:-3]
        import cv2
        gray = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY)
        dark = int((gray < 190).sum())
        teal = int(((inner[:, :, 0] > 100) & (inner[:, :, 1] > 100)
                    & (inner[:, :, 2] < 120)).sum())
        print(f"{LOG} print numbers teal={teal} dark={dark} "
              f"enabled={bool(user32.IsWindowEnabled(bh))}")
        return (teal >= 50 or dark >= 5), bool(user32.IsWindowEnabled(bh))

    def ok_button():
        for t, r, h in kids():
            if t.strip().lower() == "ok" and user32.IsWindowVisible(h):
                return h, r
        return None, None

    def click_ok():
        h, r = ok_button()
        if not h:
            return False
        real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
        return True

    def accept_step_import():
        for cls, t, r, h in m7._visible_toplevels(session.pid):
            if cls == "#32770" and "step file import" in (t or "").lower():
                for bt, br, bh in export_util._children_texts(h):
                    if bt.strip().lower() == "ok" and user32.IsWindowVisible(bh):
                        real_click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
                        return True
        return False

    def click_ok_and_import():
        step_ok = False
        for _attempt in (1, 2):
            click_ok()
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
            if f > max(frac0 + 0.002, frac0 * 2.5):
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

        switched = radio_click("PA Pattern")
        time.sleep(1.5)
        start = field_by_label("start pa")
        end = field_by_label("end pa")
        step = field_by_label("pa step")
        accel = field_by_label("accelerations")
        speed = field_by_label("speeds")
        results["切换到 PA Pattern（V 形，圆点）"] = (
            "PASS" if switched else "FAIL (label)")
        vals = tuple(winutil.edit_text(h).strip()
                     for h in (start, end, step)) if all((start, end, step)) else ()
        print(f"{LOG} start/end/step={vals}")
        results["默认 0 / 0.08 / 0.005"] = (
            "PASS" if vals == ("0", "0.08", "0.005") else f"FAIL ({vals})")
        checked, pn_enabled = pn_state_visual()
        results["Print numbers 勾选但禁用"] = (
            "PASS" if checked is True and not pn_enabled else
            f"FAIL (checked={checked} enabled={pn_enabled})")
        acc_ok = accel and user32.IsWindowEnabled(accel) and \
            winutil.edit_text(accel).strip() == ""
        spd_ok = speed and user32.IsWindowEnabled(speed) and \
            winutil.edit_text(speed).strip() == ""
        print(f"{LOG} accel enabled={bool(accel) and bool(user32.IsWindowEnabled(accel))} "
              f"text={winutil.edit_text(accel)!r}; "
              f"speed enabled={bool(speed) and bool(user32.IsWindowEnabled(speed))} "
              f"text={winutil.edit_text(speed)!r}")
        results["加速度/速度可填且为空"] = (
            "PASS" if acc_ok and spd_ok else
            f"FAIL (acc={acc_ok} speed={spd_ok})")

        step_ok = click_ok_and_import()
        frac = wait_model(frac0)
        print(f"{LOG} bed frac after OK={frac:.4%} step_import={step_ok}")
        results["点击确定后生成 V 形校准模型"] = (
            "PASS" if frac > max(frac0 + 0.002, frac0 * 2.5) else
            f"FAIL (frac {frac0:.4%} -> {frac:.4%})")
        results["确定后对话框关闭"] = (
            "PASS" if not pa_dialog() else "FAIL (dialog still open)")
        if frac <= max(frac0 + 0.002, frac0 * 2.5):
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        deselected, selected = select_model_row() or (None, None)
        results["点击 Outside 行清除选择"] = (
            "PASS" if deselected else "FAIL (still selected)")
        results["V 形模型对象行可单独选中"] = (
            "PASS" if selected else "FAIL (info panel empty)")
        m7.op_slice(session, results, key="PA V 形模式切片")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
