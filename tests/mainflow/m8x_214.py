#!/usr/bin/env python3
# m8x_214.py — 飞书基线 #214: 【输入整形频率】X/Y 默认 15~110Hz + 阻尼
# 0.15，生成扫频测试件，切片成功
# feishu: baseline#214
# 行文: 校准 > 输入整形 > 输入整形频率 → 弹窗为 X/Y 独立起止 + 单一阻尼
#       系数（无步长输入），测试模型二选（振铃塔/快速塔），默认 X/Y 均
#       15~110Hz、阻尼 0.15 → 确定生成扫频测试件 → 落板可选中 → 切片成功
#
# 入口 = Calibration 菜单 → hover 'Input Shaping' 子菜单 → 真点
# 'Input Shaping Frequency'（probe_242_inputshaping214：子菜单
# rect=(437,161,740,211)，频率行 y=174；弹窗 #32770
# 'Input shaping Frequency test'：X Start/End 两个 Edit、Y Start/End 两个
# Edit、Damp Edit、Ringing Tower/Fast Tower 单选、OK）。
# 若模板是 STEP 文件，OK 后先接受 'Step file import parameters' 默认值
# （#213 同款；本模板是否 STEP 由运行日志记录）。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x214]"
DIALOG_TITLE = "input shaping frequency test"


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

    def is_dialog():
        for cls, t, r, h in m7._visible_toplevels(session.pid):
            if cls == "#32770" and DIALOG_TITLE in (t or "").lower():
                return (cls, t, r, h)
        return None

    def open_submenu(parent_substr, row_substr):
        menu = topbar_util.open_calibration_menu(session)
        if not menu:
            return None, None
        rect, mhwnd, hm = menu
        n = len(topbar_util.menu_items(hm))
        idx = topbar_util.find_item(hm, parent_substr)
        if idx is None:
            return None, None
        known = {mhwnd}
        cx = (rect[0] + rect[2]) // 2
        for y in topbar_util.submenu_row_candidates(rect, n, idx):
            user32.SetCursorPos(cx, y)
            time.sleep(0.7)
            for m in topbar_util._enum_menu_windows(session.pid):
                if m[4] in known:
                    continue
                known.add(m[4])
                shm = topbar_util.menu_hmenu(m[4])
                labels = [l.lower() for _i, l, _s in
                          topbar_util.menu_items(shm)]
                if any(row_substr.lower() in l for l in labels):
                    print(f"{LOG} submenu rect={m[:4]} rows={labels}")
                    return (m[:4], m[4], shm), labels
        return None, None

    def click_submenu_row(sub_rect, shm, want_substr):
        items = topbar_util.menu_items(shm)
        idx = next((i for i, l, _s in items
                    if want_substr.lower() in l.lower()), None)
        if idx is None:
            return False
        n = len(items)
        x = (sub_rect[0] + sub_rect[2]) // 2
        for y in topbar_util.submenu_row_candidates(sub_rect, n, idx):
            for attempt in (1, 2):
                print(f"{LOG} click {want_substr!r} y={y} attempt={attempt}")
                real_click(x, y)
                time.sleep(1.5)
                if is_dialog():
                    return True
        return False

    def row_edits(dlg, label):
        """Edits on the Static row whose text starts with `label`, sorted by x
        (X Start / End and Y Start / End each carry TWO edits)."""
        kids = export_util._children_texts(dlg[3])
        lab = next(((t, r) for t, r, h in kids
                    if t.strip().lower().startswith(label)), None)
        if not lab:
            return []
        ly = (lab[1][1] + lab[1][3]) // 2
        eds = [(r, h) for t, r, h in kids
               if winutil.window_class(h) == "Edit"
               and abs(((r[1] + r[3]) // 2) - ly) <= 14
               and user32.IsWindowVisible(h)]
        return [h for _r, h in sorted(eds)]

    def edit_by_label(dlg, label):
        eds = row_edits(dlg, label)
        return eds[0] if eds else None

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
                if not is_dialog():
                    break
                time.sleep(0.5)
            if step_ok or not is_dialog():
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
        sub, _labels = open_submenu("input shaping",
                                    "input shaping frequency")
        opened = bool(sub) and click_submenu_row(
            sub[0], sub[2], "input shaping frequency")
        dlg = is_dialog() if opened else None
        results["输入整形频率弹窗打开"] = (
            "PASS" if dlg else "FAIL (no dialog)")
        if not dlg:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        xe = row_edits(dlg, "x start")
        ye = row_edits(dlg, "y start")
        damp = edit_by_label(dlg, "damp")
        results["X/Y/Damp 字段可定位"] = (
            "PASS" if len(xe) == 2 and len(ye) == 2 and damp else
            f"FAIL (x={len(xe)} y={len(ye)} damp={bool(damp)})")
        if not (len(xe) == 2 and len(ye) == 2 and damp):
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)
        vals = [winutil.edit_text(h).strip() for h in
                (xe[0], xe[1], ye[0], ye[1], damp)]
        print(f"{LOG} X/Y/damp={vals}")
        results["默认 X/Y 15~110Hz + 阻尼 0.15"] = (
            "PASS" if vals == ["15", "110", "15", "110", "0.150"] else
            f"FAIL ({vals})")
        labels = [t.strip().lower() for t, r, h in
                  export_util._children_texts(dlg[3]) if t.strip()]
        has_ring = any("ringing tower" in l for l in labels)
        has_fast = any("fast tower" in l for l in labels)
        results["测试模型二选（Ringing/Fast Tower）"] = (
            "PASS" if has_ring and has_fast else
            f"FAIL (ringing={has_ring} fast={has_fast})")

        step_ok = click_ok_and_import(dlg)
        frac = wait_model(frac0)
        print(f"{LOG} bed frac after OK={frac:.4%} step_import={step_ok}")
        results["点击确定后生成扫频测试件"] = (
            "PASS" if frac > max(frac0 + 0.003, frac0 * 2) else
            f"FAIL (frac {frac0:.4%} -> {frac:.4%})")
        results["确定后弹窗关闭"] = (
            "PASS" if not is_dialog() else "FAIL (dialog still open)")
        if frac <= max(frac0 + 0.003, frac0 * 2):
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        deselected, selected = select_model_row() or (None, None)
        results["点击 Outside 行清除选择"] = (
            "PASS" if deselected else "FAIL (still selected)")
        results["扫频测试件对象行可单独选中"] = (
            "PASS" if selected else "FAIL (info panel empty)")
        m7.op_slice(session, results, key="输入整形频率切片")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
