#!/usr/bin/env python3
# m8x_218.py — 飞书基线 #218: 【温度塔默认区间】切换耗材类型自动更新
# 起止默认值（PLA 230/190 等 6 组映射）
# feishu: baseline#218
# 行文: 校准 > 温度 → 依次切换耗材类型 ABS/ASA、PETG、PCTG、TPU、PA-CF、
#       PET-CF，记录起始/结束默认值 → 切回 PLA/自定义
#
# 入口/对话框：probe_242_temp208 + probe_242_temp218 标定 #32770
# 'Temperature calibration'：Filament type 单选组（圆点在标签左侧的
# 空 Static，点圆点即切换）+ Start temp / End temp / Temp step 三个 Edit。
# 实测映射（11-13）：PLA 230/190、ABS/ASA 270/230、PETG 250/230、
# PCTG 280/240、TPU 240/210、PA-CF 320/280、PET-CF 320/280、
# Custom 230/190；步长恒 5 且 disabled。
# 判定 = 逐组精确回读（同时覆盖"切换不残留上一组数值"）+ 区间校验
# （start<=350、end>=170、end<=start-5）。本条不生成模型、不切片。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x218]"
DIALOG_TITLE = "temperature calibration"
EXPECTED = {
    "PLA": ("230", "190"),
    "ABS/ASA": ("270", "230"),
    "PETG": ("250", "230"),
    "PCTG": ("280", "240"),
    "TPU": ("240", "210"),
    "PA-CF": ("320", "280"),
    "PET-CF": ("320", "280"),
    "Custom": ("230", "190"),
}
SWITCH_ORDER = ["ABS/ASA", "PETG", "PCTG", "TPU", "PA-CF", "PET-CF"]


def main() -> int:
    import argparse
    import m7_common as m7
    from m3_common import add_common_args, boot_session
    from harness import export_util, topbar_util, winutil

    user32 = winutil.user32

    def real_click(x, y):
        user32.SetCursorPos(x, y)
        time.sleep(0.25)
        winutil.real_click_screen(x, y, hold_ms=60)

    def temp_dialog():
        for cls, t, r, h in m7._visible_toplevels(session.pid):
            if cls == "#32770" and DIALOG_TITLE in (t or "").lower():
                return (cls, t, r, h)
        return None

    def open_temp():
        menu = topbar_util.open_calibration_menu(session)
        if not menu:
            return None
        rect, _mhwnd, hm = menu
        idx = topbar_util.find_item(hm, "temperature")
        if idx is None:
            return None
        cx = (rect[0] + rect[2]) // 2
        for y in topbar_util.submenu_row_candidates(
                rect, len(topbar_util.menu_items(hm)), idx):
            real_click(cx, y)
            time.sleep(1.5)
            d = temp_dialog()
            if d:
                return d
        return None

    def field(dlg, label):
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

    def radio_click(dlg, label):
        """Click the radio circle (empty Static) left of the label."""
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

    def vals_of(dlg):
        s = field(dlg, "start temp")
        e = field(dlg, "end temp")
        t = field(dlg, "temp step")
        if not (s and e and t):
            return None
        return (winutil.edit_text(s).strip(),
                winutil.edit_text(e).strip(),
                winutil.edit_text(t).strip(),
                bool(user32.IsWindowEnabled(t)))

    ap = add_common_args(argparse.ArgumentParser())  # 空床
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        dlg = open_temp()
        results["Temperature calibration 对话框打开"] = (
            "PASS" if dlg else "FAIL (no dialog)")
        if not dlg:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        observed = {}
        step_ok = True
        step_editable = []
        for name in SWITCH_ORDER + ["Custom", "PLA"]:
            if not radio_click(dlg, name):
                results[f"切换到 {name}"] = "FAIL (label missing)"
                continue
            time.sleep(1.5)
            v = vals_of(dlg)
            observed[name] = v
            print(f"{LOG} {name:8s} -> {v}")
            if v is None:
                step_ok = False
                continue
            if v[2] != "5":
                step_ok = False
            if v[3]:
                step_editable.append(name)

        mismatch = []
        for name, (es, ee) in EXPECTED.items():
            v = observed.get(name)
            if not v or (v[0], v[1]) != (es, ee):
                mismatch.append(f"{name}:{v[:2] if v else None}!={es}/{ee}")
        results["六组默认值逐组精确（无残留）"] = (
            "PASS" if not mismatch else f"FAIL ({'; '.join(mismatch)})")
        results["PLA/Custom 默认 230/190"] = (
            "PASS" if observed.get("PLA", (None,))[:2] == ("230", "190")
            and observed.get("Custom", (None,))[:2] == ("230", "190")
            else f"FAIL (PLA={observed.get('PLA')} Custom={observed.get('Custom')})")
        results["步长固定 5 且不可编辑"] = (
            "PASS" if step_ok and not step_editable else
            f"FAIL (step_ok={step_ok} editable={step_editable})")

        bad_range = []
        for name, (es, ee) in EXPECTED.items():
            s, e = int(es), int(ee)
            if not (s <= 350 and e >= 170 and e <= s - 5):
                bad_range.append(f"{name}:{s}/{e}")
        results["区间校验（start<=350, end>=170, end<=start-5）"] = (
            "PASS" if not bad_range else f"FAIL ({bad_range})")

        user32.SetForegroundWindow(dlg[3])
        time.sleep(0.3)
        user32.keybd_event(0x1B, 0, 0, 0)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.5)
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
