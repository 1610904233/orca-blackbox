#!/usr/bin/env python3
# m8x_217.py — 飞书基线 #217: 【流量YOLO对比】推荐版 11 块（±0.05 步进
# 0.01）与完美主义者版 16 块（步进 0.005）直接加载，切片验证
# feishu: baseline#217
# 行文: 校准 > 流量 > YOLO（推荐）→ 无弹窗加载 11 块（0、±0.01~±0.05）
#       → 对象列表 11 行 flowrate_0 / flowrate_0.01~0.05 / flowrate_m0.01~m0.05
#       → 删除该模型 → YOLO（完美主义者）→ 16 块（4×4，0、+0.005~+0.035、
#       -0.005~-0.04）→ 对象列表 16 行 → 两版块数/步进对比 → 切片
#
# 入口 = Calibration 菜单 → hover 'Flow rate' 子菜单 → 真点第 4/5 行
# （probe_242_yolo217：rec y=122，子菜单 rows=pass1/pass2/-/yolo rec/yolo perf；
# 推荐版 11 个对象名已实证）。清场 = 主窗前台下真 Ctrl+A + Del
# （probe_242_yolo217b：2.92% → 0.12%；Ctrl+N 会弹 unsaved-changes 模态框）。
# 对象名 oracle = 存盘 3mf model_settings 的 <object> name 精确集合。
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

LOG = "[m8x217]"
ART = HERE / "artifacts"

REC_EXPECTED = (
    ["flowrate_0"]
    + [f"flowrate_0.{i:02d}" for i in range(1, 6)]
    + [f"flowrate_m0.{i:02d}" for i in range(1, 6)]
)
PERF_EXPECTED = (
    ["flowrate_0"]
    + [f"flowrate_0.{i:03d}" for i in range(5, 40, 5)]
    + [f"flowrate_m0.{i:03d}" for i in range(5, 45, 5)]
)


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

    def key_combo(*vks):
        for v in vks[:-1]:
            user32.keybd_event(v, 0, 0, 0)
        user32.keybd_event(vks[-1], 0, 0, 0)
        time.sleep(0.08)
        user32.keybd_event(vks[-1], 0, 2, 0)
        for v in reversed(vks[:-1]):
            user32.keybd_event(v, 0, 2, 0)
        time.sleep(0.5)

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

    def click_submenu_row(sub_rect, shm, want):
        items = topbar_util.menu_items(shm)
        idx = next((i for i, l, _s in items
                    if want.lower() in l.lower()), None)
        if idx is None:
            return False
        x = (sub_rect[0] + sub_rect[2]) // 2
        for y in topbar_util.submenu_row_candidates(sub_rect, len(items), idx):
            for attempt in (1, 2):
                print(f"{LOG} click {want!r} y={y} attempt={attempt}")
                real_click(x, y)
                time.sleep(1.8)
                f = m7.model_colored_frac(session)
                print(f"{LOG}   frac={f:.4%} dialogs={[(c, t) for c, t, r, h in dialogs()]}")
                if f > 0.003:
                    return True
        return False

    def accept_step_import():
        for c, t, r, h in dialogs():
            if "step file import" in (t or "").lower():
                for bt, br, bh in export_util._children_texts(h):
                    if bt.strip().lower() == "ok" and user32.IsWindowVisible(bh):
                        real_click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
                        print(f"{LOG} STEP import accepted")
                        return True
        return False

    def wait_model(base, timeout_s=90.0):
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            accept_step_import()
            f = m7.model_colored_frac(session)
            if f > max(base + 0.003, base * 2):
                return f
            time.sleep(1.0)
        return m7.model_colored_frac(session)

    def names_from_3mf(path):
        names = []
        if not path.exists():
            return names
        with zipfile.ZipFile(path) as z:
            cfg = z.read("Metadata/model_settings.config").decode(
                "utf-8", "replace")
        for obj in re.finditer(r"<object\b[^>]*>(.*?)</object>", cfg, re.S):
            mm = re.search(r'<metadata key="name" value="([^"]*)"',
                           obj.group(1))
            if mm:
                names.append(mm.group(1))
        return names

    def load_and_check(tag, row_want, expected, artifact):
        sub = open_flow_submenu()
        loaded = bool(sub) and click_submenu_row(sub[0], sub[2], row_want)
        frac = wait_model(base) if loaded else m7.model_colored_frac(session)
        unexpected = [t for c, t, r, h in dialogs()
                      if "step file import" not in (t or "").lower()]
        results[f"{tag} 加载（无参数弹窗）"] = (
            "PASS" if loaded and not unexpected else
            f"FAIL (loaded={loaded} dialogs={unexpected})")
        results[f"{tag} 模型落板（frac）"] = (
            "PASS" if frac > max(base + 0.003, base * 2) else
            f"FAIL (frac {base:.4%} -> {frac:.4%})")
        artifact.unlink(missing_ok=True)
        saved = m7.save_project_as(session, artifact) if loaded else False
        names = names_from_3mf(artifact) if saved else []
        print(f"{LOG} {tag} saved={saved} count={len(names)} names={names}")
        ok = sorted(names) == sorted(expected)
        results[f"{tag} 对象名精确一致（{len(expected)} 块）"] = (
            "PASS" if ok else
            f"FAIL (got {len(names)}: {sorted(names)[:6]}...)")
        return names

    def clear_bed():
        user32.SetForegroundWindow(session.hwnd)
        time.sleep(0.4)
        key_combo(0x11, 0x41)   # Ctrl+A
        key_combo(0x2E)         # Del
        end = time.monotonic() + 8
        while time.monotonic() < end:
            f = m7.model_colored_frac(session)
            if f <= base + 0.003:
                return f
            time.sleep(0.5)
        return m7.model_colored_frac(session)

    def ocr_band(y0, y1, x0=0, x1=430, scale=4):
        from harness import mix_dialog_util as mdu
        from harness.anchors import capture_bgr as _cap
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
        base = m7.model_colored_frac(session)
        print(f"{LOG} bed frac0={base:.4%}")

        load_and_check("YOLO 推荐版", "yolo (recommended)", REC_EXPECTED,
                       ART / "m8x_217_rec.3mf")
        frac_after_clear = clear_bed()
        print(f"{LOG} after clear frac={frac_after_clear:.4%}")
        results["Ctrl+A+Del 清场"] = (
            "PASS" if frac_after_clear <= base + 0.003 else
            f"FAIL (frac {frac_after_clear:.4%})")

        if frac_after_clear <= base + 0.003:
            load_and_check("YOLO 完美主义者版", "yolo (perfectionist",
                           PERF_EXPECTED, ART / "m8x_217_perf.3mf")
        else:
            results["YOLO 完美主义者版 加载（无参数弹窗）"] = "FAIL (bed not cleared)"
            results["YOLO 完美主义者版 模型落板（frac）"] = "FAIL (bed not cleared)"
            results["YOLO 完美主义者版 对象名精确一致（16 块）"] = "FAIL (bed not cleared)"

        # 两版对比：16 > 11 块；细档步进 0.005 < 推荐版 0.01
        perf_names = names_from_3mf(ART / "m8x_217_perf.3mf")
        rec_names = names_from_3mf(ART / "m8x_217_rec.3mf")
        step_ok = (any("0.005" in n for n in perf_names)
                   and all("0.01" not in n for n in perf_names))
        results["两版对比（16>11，完美版步进 0.005）"] = (
            "PASS" if len(perf_names) == 16 and len(rec_names) == 11
            and step_ok else
            f"FAIL (rec={len(rec_names)} perf={len(perf_names)} step={step_ok})")

        deselected, selected = select_model_row() or (None, None)
        results["完美版对象行可单独选中"] = (
            "PASS" if selected else "FAIL (info panel empty)")
        m7.op_slice(session, results, key="YOLO 完美版切片")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
