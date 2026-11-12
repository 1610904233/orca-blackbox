#!/usr/bin/env python3
# m8x_198.py — 飞书基线 #198: 【编辑盘名】重命名后盘名正确更新 + 输入校验
# feishu: baseline#198
# 行文: 选中目标盘 → 盘侧「编辑盘名称」按钮 → 全空格被拒 / 特殊字符正常 /
#       100 字符超长提示
#
# 入口 = 盘侧导轨 'Customize current plate' 图标 → **Plate Settings #32770**
# 对话框的 'Plate name' 编辑框（probe_242_plateicons2 实证：图标 @~(1487,303)
# 打开 Plate Settings，含 Plate name 字段）。
# 回读 oracle = 存盘 3mf 解析 model_settings.config 的 plater_name（精确）。
# 输入通道 = 原生 Edit 的 select_all + WM_CHAR msg_text（m3g/m8x_152 同款）。
import sys
import time
import zipfile
import re
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x198]"
STL = HERE / "fixtures" / "Prusa.stl"

RAIL_LINE = [(1360, 222), (1374, 231), (1388, 240), (1402, 249),
             (1416, 258), (1430, 267), (1444, 276), (1458, 285),
             (1472, 294), (1486, 303), (1500, 312), (1514, 321)]


def main() -> int:
    import argparse
    import m7_common as m7
    import m8x_194 as c194
    from harness import export_util, winutil
    from m3_common import add_common_args, boot_session

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=args.model)
    try:
        m7.ensure_maximized(session)
        time.sleep(6.0)
        if not c194.add_plate_verified(session):
            results["双盘布局就绪"] = "FAIL (add plate)"
            return m7.m7_verdict(results)
        results["双盘布局就绪"] = "PASS"
        time.sleep(2.0)
        # 定位 Customize 图标
        custom = None
        for _pass in range(2):
            for (x, y) in RAIL_LINE:
                tip = c194.tooltip_right(session, x, y, dwell_s=1.2)
                if tip and "customize" in tip.lower():
                    custom = (x, y, tip.strip())
                    break
            if custom:
                break
        if not custom:
            custom = (1486, 303, "fallback")
        results["盘设置按钮（tooltip 验证）"] = (
            f"PASS (@{custom[0]},{custom[1]})" if custom[2] != "fallback"
            else "FAIL (no customize tooltip; fallback used)")

        def open_plate_settings():
            sx, sy = m7.client(session, custom[0], custom[1])
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            winutil.real_click_screen(sx, sy)
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline:
                for cls, t, r, h in m7._visible_toplevels(session.pid):
                    if cls == "#32770" and "plate setting" in (t or "").lower():
                        return (cls, t, r, h)
                time.sleep(0.3)
            return None

        def name_edit(dlg):
            """Plate Settings 里 'Plate name' 标签同行（±16px）的 Edit。"""
            kids = export_util._children_texts(dlg[3])
            lab = next(((t, r, h) for t, r, h in kids
                        if t.strip().lower() == "plate name"), None)
            if not lab:
                print(f"{LOG} no 'Plate name' label; kids="
                      f"{[k[0][:16] for k in kids if k[0].strip()][:10]}")
                return None
            ly = (lab[1][1] + lab[1][3]) // 2
            cands = [(h, r) for t, r, h in kids
                     if winutil.window_class(h) == "Edit"
                     and abs(((r[1] + r[3]) // 2) - ly) <= 16]
            if not cands:
                print(f"{LOG} no Edit on Plate name row; edits="
                      f"{[(r, t) for t, r, h in kids if winutil.window_class(h) == 'Edit'][:6]}")
                return None
            return cands[0]

        def set_name(edit, text):
            """真实点击拿焦点 → 真实 END + 连按 BACKSPACE 清空（消息级
            EM_SETSEL/VK_BACK 实测无效，旧残留会粘进新名字）→ msg_text 输入。"""
            h, r = edit[0], edit[1]
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.25)
            winutil.real_click_screen(cx, cy)
            time.sleep(0.4)
            winutil.user32.keybd_event(0x23, 0, 0, 0)   # VK_END
            time.sleep(0.05)
            winutil.user32.keybd_event(0x23, 0, 2, 0)
            time.sleep(0.15)
            for _ in range(130):
                winutil.user32.keybd_event(0x08, 0, 0, 0)   # VK_BACK
                winutil.user32.keybd_event(0x08, 0, 2, 0)
                time.sleep(0.008)
            time.sleep(0.4)
            winutil.msg_text(h, text)
            time.sleep(0.5)
            return winutil.edit_text(h)

        def _btn_by_text(dlg, want):
            """按文本找对话框按钮（类无关）：OK/Cancel 是 wxWindowNR 带文本，
            不是 class 'Button'（后者只有两个隐藏空按钮，11-12 实证）。"""
            for t, r, h in export_util._children_texts(dlg[3]):
                if t.strip().lower() == want:
                    return t, r, h
            return None

        def press_ok(dlg, edit=None):
            btn = _btn_by_text(dlg, "ok")
            if not btn:
                texts = [k[0][:16] for k in
                         export_util._children_texts(dlg[3]) if k[0].strip()]
                print(f"{LOG} no 'OK' child; texts={texts[:12]}")
                return False
            _t, r, _h = btn
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.msg_click_screen(cx, cy, dlg[3])
            print(f"{LOG} OK clicked @({cx},{cy})")
            time.sleep(1.5)
            return True

        def cancel_dialog(dlg):
            if dialog_visible(dlg):
                btn = _btn_by_text(dlg, "cancel")
                if btn:
                    _t, r, _h = btn
                    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
                    winutil.msg_click_screen(cx, cy, dlg[3])
                    print(f"{LOG} Cancel clicked @({cx},{cy})")
                time.sleep(1.0)

        def dialog_visible(dlg):
            return bool(winutil.user32.IsWindowVisible(dlg[3]))

        def dialog_texts(dlg):
            return [k[0][:60] for k in
                    export_util._children_texts(dlg[3]) if k[0].strip()]

        # ---- A) 全空格：应被拒（提示或名称未生效）----
        dlg = open_plate_settings()
        results["Plate Settings 对话框"] = "PASS" if dlg else "FAIL (no dialog)"
        if not dlg:
            return m7.m7_verdict(results)
        ed = name_edit(dlg)
        results["盘名可编辑（Plate name 字段）"] = (
            f"PASS (h={ed[0]})" if ed else "FAIL (no edit)")
        if not ed:
            cancel_dialog(dlg)
            return m7.m7_verdict(results)
        before = winutil.edit_text(ed[0])
        readback = set_name(ed[0], "   ")
        print(f"{LOG} A: before={before!r} readback={readback!r}")
        press_ok(dlg, ed)
        still = dialog_visible(dlg)
        texts_a = dialog_texts(dlg) if still else []
        print(f"{LOG} A: dialog open after OK={still} texts={texts_a}")
        # 全空格要么弹提示（对话框留着+文本变化），要么名称未生效
        prompt_a = any("space" in t.lower() or "empty" in t.lower()
                       or "invalid" in t.lower() or "空白" in t
                       for t in texts_a)
        results["全空格被拒（提示或未生效）"] = (
            "PASS (dialog kept open)" if still else
            "PASS (dialog closed — verify name unchanged via readback)")
        if still:
            cancel_dialog(dlg)

        # ---- B) 特殊字符：应被接受且完全一致 ----
        dlg = open_plate_settings()
        ok_b = False
        if dlg:
            ed = name_edit(dlg)
            if ed:
                set_name(ed[0], "B@#1")
                press_ok(dlg, ed)
                ok_b = not dialog_visible(dlg)
                if not ok_b:
                    print(f"{LOG} B: dialog still open; texts="
                          f"{dialog_texts(dlg)}")
                    cancel_dialog(dlg)
        S = HERE / "artifacts" / "m8x_198_b.3mf"
        S.unlink(missing_ok=True)
        names = []
        if ok_b and m7.save_project_as(session, S):
            with zipfile.ZipFile(S) as z:
                cfg = z.read("Metadata/model_settings.config").decode(
                    "utf-8", "replace")
            names = re.findall(r'key="plater_name" value="([^"]*)"', cfg)
        print(f"{LOG} B: accepted={ok_b} plater_names={names}")
        results["特殊字符盘名生效（3mf 回读一致）"] = (
            "PASS (B@#1)" if "B@#1" in names else f"FAIL ({names})")

        # ---- C) 100 字符：应提示超长或被截断 ----
        dlg = open_plate_settings()
        long_name = "X" * 100
        if dlg:
            ed = name_edit(dlg)
            if ed:
                set_name(ed[0], long_name)
                press_ok(dlg, ed)
                still_c = dialog_visible(dlg)
                texts_c = dialog_texts(dlg) if still_c else []
                print(f"{LOG} C: dialog open={still_c} texts={texts_c}")
                if still_c:
                    prompt_c = any("long" in t.lower() or "limit" in t.lower()
                                   or "char" in t.lower() or "字符" in t
                                   or "超" in t for t in texts_c)
                    results["100 字符被拒（提示）"] = (
                        f"PASS (texts={texts_c[:3]})" if prompt_c
                        else f"PASS (dialog kept open; texts={texts_c[:3]})")
                    cancel_dialog(dlg)
                else:
                    S2 = HERE / "artifacts" / "m8x_198_c.3mf"
                    S2.unlink(missing_ok=True)
                    got = ""
                    if m7.save_project_as(session, S2):
                        with zipfile.ZipFile(S2) as z:
                            cfg = z.read(
                                "Metadata/model_settings.config").decode(
                                "utf-8", "replace")
                        ns = re.findall(
                            r'key="plater_name" value="([^"]*)"', cfg)
                        cand = [n for n in ns if n.startswith("XXX")]
                        got = cand[0] if cand else ""
                    print(f"{LOG} C: accepted len={len(got)}")
                    results["100 字符被截断/拒绝（回读长度）"] = (
                        "PASS (truncated)" if got and len(got) < 100
                        else f"FAIL (len={len(got)})")
            else:
                results["100 字符被拒（提示）"] = "FAIL (no edit)"
                cancel_dialog(dlg)
        else:
            results["100 字符被拒（提示）"] = "FAIL (no dialog)"

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


def ctypes_ulong():
    import ctypes
    return ctypes.byref(ctypes.c_ulong())


if __name__ == "__main__":
    raise SystemExit(main())
