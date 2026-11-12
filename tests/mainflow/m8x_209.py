#!/usr/bin/env python3
# m8x_209.py — 飞书基线 #209: 【流量粗调】无弹窗直接加载 9 块校准件，
# 对象命名与切片验证
# feishu: baseline#209
# 行文: 校准 > 流量 > Pass 1（粗调）→ 不出现参数弹窗，热床加载 3×3 共 9 块
#       （-20%~+20% 步进 5%）→ 对象列表 9 行 flowrate_0/5/10/15/20 +
#       flowrate_m5/m10/m15/m20 → 模型完整落板、可单独选中 → 切片成功
#
# 入口 = Calibration 菜单 → hover 'Flow rate' 展开子菜单 → 真点 'Pass 1'
# （probe_242_flow209：子菜单 rect=(437,51,698,154)，Pass 1 @y=62；点击后
# 无任何 #32770，空床彩色占比 0.06%→3.02%）。
# 对象名 oracle = 存盘 3mf 的 model_settings.config 里每个 <object> 的
# name 元数据（精确 9 个）；对象列表用 Objects 标签页 OCR 作 UI 证据，
# 并点一行验证可单独选中。
import re
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x209]"
ART = HERE / "artifacts"
EXPECTED = ["flowrate_0", "flowrate_5", "flowrate_10", "flowrate_15",
            "flowrate_20", "flowrate_m5", "flowrate_m10", "flowrate_m15",
            "flowrate_m20"]


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

    def dialogs():
        return [(c, t, r, h) for c, t, r, h in m7._visible_toplevels(session.pid)
                if c == "#32770"]

    def open_flow_submenu():
        menu = topbar_util.open_calibration_menu(session)
        if not menu:
            return None
        rect, mhwnd, hm = menu
        n = len(topbar_util.menu_items(hm))
        idx = topbar_util.find_item(hm, "flow rate")
        if idx is None:
            return None
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
                if any("pass 1" in l for l in labels):
                    print(f"{LOG} flow submenu rect={m[:4]} rows={labels}")
                    return (m[:4], m[4], shm)
        return None

    def click_pass1(sub_rect, shm, frac0):
        n = len(topbar_util.menu_items(shm))
        x = (sub_rect[0] + sub_rect[2]) // 2
        for y in topbar_util.submenu_row_candidates(sub_rect, n, 0):
            for attempt in (1, 2):
                print(f"{LOG} click Pass 1 y={y} attempt={attempt}")
                real_click(x, y)
                time.sleep(1.8)
                f = m7.model_colored_frac(session)
                print(f"{LOG}   frac={f:.4%} dialogs={len(dialogs())}")
                if f > frac0 + 0.005:
                    return True, y, f
        return False, None, m7.model_colored_frac(session)

    def ocr_band(y0, y1, x0=0, x1=430, scale=4):
        img = _cap(session)
        crop = img[max(0, y0):y1, x0:x1]
        if crop.size == 0:
            return []
        return [(w[0], w[1] + x0, w[2] + y0, w[3], w[4])
                for w in mdu.ocr_words_img(crop, scale=scale)]

    def objects_panel():
        """Click the Process panel's Objects tab; returns the list band y or
        None. Also wheels the list to the top."""
        rows = export_util._children_texts(session.hwnd)
        proc = next(((t, r) for t, r, h in rows if t.strip() == "Process"),
                    None)
        adv = next(((t, r) for t, r, h in rows if t.strip() == "Advanced"),
                   None)
        if not (proc and adv):
            print(f"{LOG} Process/Advanced labels missing: "
                  f"{[t for t, r, h in rows if t.strip()][:20]}")
            return None, None
        y0, y1 = proc[1][1] - 8, proc[1][3] + 8
        band = ocr_band(y0, y1, scale=3)
        objw = next((w for w in band if "bject" in w[0].lower()), None)
        if not objw:
            print(f"{LOG} no Objects tab: {[w[0] for w in band]}")
            return None, None
        cx = objw[1] + objw[3] // 2
        cy = objw[2] + objw[4] // 2
        real_click(cx, cy)
        time.sleep(1.5)
        # scroll the object list to the top (wheel up over the list)
        sx, sy = m7.client(session, 200, (y1 + 780) // 2)
        user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        winutil.real_wheel_screen(sx, sy, 6)
        time.sleep(1.0)
        return y1 + 2, (sx, sy)

    def object_rows(y_top):
        words = ocr_band(y_top, 800, scale=4)
        lines = {}
        for t, x, y, w, h in words:
            key = next((k for k in lines if abs(k - y) <= 10), y)
            lines.setdefault(key, []).append((x, t, w, h, y))
        out = []
        for k in sorted(lines):
            parts = sorted(lines[k])
            text = " ".join(p[1] for p in parts)
            out.append((k, text, parts))
            print(f"{LOG}   y={k}: {text}")
        return out

    def select_row(row):
        """Click a visible flowrate row; True if the info panel reports a
        selected object (m8x_152's row-click channel)."""
        y = row[0]
        x = max(p[0] + p[2] // 2 for p in row[2])
        sx, sy = m7.client(session, x, y + 8)
        real_click(sx, sy)
        time.sleep(1.2)
        return m7.object_selected(session)

    ap = add_common_args(argparse.ArgumentParser())  # 空床
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=None)
    try:
        time.sleep(2.0)
        frac0 = m7.model_colored_frac(session)
        print(f"{LOG} bed frac0={frac0:.4%}")

        loaded = False
        frac = frac0
        for attempt in range(3):
            print(f"{LOG} --- load attempt {attempt + 1}")
            sub = open_flow_submenu()
            if not sub:
                print(f"{LOG} no flow submenu")
                break
            loaded, _y, frac = click_pass1(sub[0], sub[2], frac0)
            if loaded:
                break
            m7.dismiss_menus(session)
            time.sleep(1.0)
        results["Pass 1 加载校准件（无参数弹窗）"] = (
            "PASS" if loaded and not dialogs() else
            f"FAIL (loaded={loaded} dialogs={[(c, t) for c, t, r, h in dialogs()]})")
        results["9 块模型落板（彩色占比上升）"] = (
            "PASS" if frac > frac0 + 0.005 else
            f"FAIL (frac {frac0:.4%} -> {frac:.4%})")
        if not loaded:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return m7.m7_verdict(results)

        # ---- 对象列表 UI 证据 + 单独选中 ----
        y_top, _list_pt = objects_panel()
        rows = object_rows(y_top) if y_top else []
        vis = set()
        for _k, text, _p in rows:
            for tok in re.findall(r"flowrate_?\w*", text, re.I):
                vis.add(tok.lower())
        print(f"{LOG} visible flowrate names={sorted(vis)}")
        results["对象列表可见 flowrate_* 行（UI 证据）"] = (
            "PASS" if len(vis) >= 6 else f"FAIL (visible={sorted(vis)})")
        target = next((r for r in rows
                       if "flowrate_" in r[1].lower()), None)
        results["可见对象行可单独选中"] = (
            "PASS" if target and select_row(target)
            else f"FAIL (row={target[1] if target else None})")

        # ---- 3mf 对象名精确 oracle ----
        p = ART / "m8x_209.3mf"
        p.unlink(missing_ok=True)
        saved = m7.save_project_as(session, p)
        names = []
        if saved and p.exists():
            with zipfile.ZipFile(p) as z:
                cfg = z.read("Metadata/model_settings.config").decode(
                    "utf-8", "replace")
            for obj in re.finditer(r"<object\b[^>]*>(.*?)</object>", cfg, re.S):
                mm = re.search(r'<metadata key="name" value="([^"]*)"',
                               obj.group(1))
                if mm:
                    names.append(mm.group(1))
        print(f"{LOG} 3mf object names={names}")
        results["3mf 对象名恰为 9 档（含 m 负值）"] = (
            "PASS" if sorted(names) == sorted(EXPECTED) else
            f"FAIL (names={names})")

        m7.op_slice(session, results, key="流量粗调切片")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
