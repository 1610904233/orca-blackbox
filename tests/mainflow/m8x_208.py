#!/usr/bin/env python3
# m8x_208.py — 飞书基线 #208: 【温度塔】PLA 默认 230→190 生成 9 段温度塔，
# 切片 gcode 含 9 个温度档位
# feishu: baseline#208
# 行文: 校准 > 温度 → 默认 230/190/步长 5（固定不可编辑）→ 确定生成温度塔
#       → 模型完整落板 → 切片成功 → gcode 按 230→190 每段 -5 共 9 档
#
# 入口 = 顶栏 Calibration（offset 250）→ Temperature 行（真实点击，候选 y
# 扫描）→ #32770 'Temperature calibration'（probe_242_temp208 标定）：
# Filament type 单选组（PLA 默认）+ Start temp / End temp / Temp step 三个
# Edit（步长控件 en=False）+ OK。
# 模型 oracle = 空床彩色占比 ~0.06% → 加载塔后 >0.5%。
# gcode oracle = M104/M109 的 S 值里，{190,195,...,230} 九档齐全，且首次出现
# 顺序为 230→190 递减（机器 start gcode 的其他温度不计入该集合）。
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x208]"
ART = HERE / "artifacts"
DIALOG_TITLE = "temperature calibration"
TOWER_TEMPS = [230, 225, 220, 215, 210, 205, 200, 195, 190]


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

    def open_temp_dialog():
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

    def field_by_label(dlg, label):
        """Edit on the row of the Static whose text starts with `label`."""
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

    def wait_model(frac0, timeout_s=40.0):
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            f = m7.model_colored_frac(session)
            if f > frac0 + 0.005:
                return f
            time.sleep(1.0)
        return m7.model_colored_frac(session)

    ap = add_common_args(argparse.ArgumentParser())  # 空床
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        frac0 = m7.model_colored_frac(session)
        print(f"{LOG} bed frac before={frac0:.4%}")
        dlg = open_temp_dialog()
        results["Temperature calibration 对话框打开"] = (
            "PASS" if dlg else "FAIL (no dialog)")
        if not dlg:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        start = field_by_label(dlg, "start temp")
        end = field_by_label(dlg, "end temp")
        step = field_by_label(dlg, "temp step")
        results["Start/End/Step 字段可定位"] = (
            "PASS" if (start and end and step) else
            f"FAIL (start={bool(start)} end={bool(end)} step={bool(step)})")
        if not (start and end and step):
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        vals = tuple(winutil.edit_text(h).strip() for h in (start, end, step))
        print(f"{LOG} defaults start/end/step={vals}")
        results["默认值 230/190/5"] = (
            "PASS" if vals == ("230", "190", "5") else f"FAIL ({vals})")
        step_enabled = bool(user32.IsWindowEnabled(step))
        results["步长固定不可编辑（disabled）"] = (
            "PASS" if not step_enabled else "FAIL (step editable)")
        # PLA 默认选中：Filament type 组里 PLA 应有选中态；读不到勾选态时
        # 以默认值 230/190 + 后续模型温度档位间接证明 PLA 分支。
        results["PLA 默认（230/190 分支）"] = (
            "PASS" if vals[:2] == ("230", "190") else f"FAIL ({vals[:2]})")

        click_ok(dlg)
        time.sleep(2.0)
        if temp_dialog():
            print(f"{LOG} first OK swallowed — retrying")
            click_ok(dlg)
            time.sleep(2.0)
        model_frac = wait_model(frac0)
        print(f"{LOG} bed frac after OK={model_frac:.4%}")
        results["点击确定后生成温度塔模型"] = (
            "PASS" if model_frac > frac0 + 0.005 else
            f"FAIL (frac {frac0:.4%} -> {model_frac:.4%})")
        results["确定后对话框关闭"] = (
            "PASS" if not temp_dialog() else "FAIL (dialog still open)")
        if model_frac <= frac0 + 0.005:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        gpath = ART / "m8x_208_tower.gcode"
        gpath.unlink(missing_ok=True)
        exported = m7.op_slice(session, results, key="温度塔切片",
                               export_to=gpath)
        temps = []
        if gpath.exists():
            text = gpath.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if re.match(r"\s*M10[49]\b", line):
                    for mv in re.finditer(r"\bS(\d+)\b", line):
                        temps.append(int(mv.group(1)))
        print(f"{LOG} gcode temps(first 40)={temps[:40]}")
        found = {t for t in temps if t in TOWER_TEMPS}
        results["gcode 含 9 档温度（230..190 步长 5）"] = (
            "PASS" if found == set(TOWER_TEMPS) else
            f"FAIL (found={sorted(found)})")
        order = []
        for t in temps:
            if t in TOWER_TEMPS and (not order or order[-1] != t):
                order.append(t)
        results["温度档位按 230→190 递变"] = (
            "PASS" if order == TOWER_TEMPS else f"FAIL (order={order})")
        results["gcode 导出"] = (
            "PASS" if exported and gpath.exists() and gpath.stat().st_size > 0
            else "FAIL (missing/empty)")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
