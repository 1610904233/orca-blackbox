#!/usr/bin/env python3
# probe_241_plate7.py — 盘侧图标列标定 v2（plate6 的修正版）
#
# plate6 两个教训：
#   1. m8x_152.m7_boot 遇 setup wizard 抢焦点 → click_slot(756) 被吞 →
#      全程单盘（plate_w 不变、终盘数=1），图标列根本没出现。v2 改用与
#      #188/#189 相同的 m3_common.boot_session，加盘带宽度验证 + 重试。
#   2. 子菜单枚举对叶子项（Preferences/Help）误回显父菜单行。v2 只对
#      Edit/View 两行取子菜单。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPlate7]"
STL = HERE / "fixtures" / "Prusa.stl"
PROJ = HERE / "artifacts" / "probe_241_plate7.3mf"


def crop_diff(a, b, x, y, r=22):
    h, w = a.shape[:2]
    x0, x1 = max(0, x - r), min(w, x + r)
    y0, y1 = max(0, y - r), min(h, y + r)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    d = abs(a[y0:y1, x0:x1].astype(int) - b[y0:y1, x0:x1].astype(int))
    return float(d.mean())


def snap(session):
    import cv2
    from harness.anchors import capture_bgr
    return cv2.cvtColor(capture_bgr(session), cv2.COLOR_BGR2GRAY)


def plate_width(session):
    import cv2
    import numpy as np
    import m7_common as m7
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    h, w = img.shape[:2]
    x0, y0 = m7.VIEWPORT_X0 + 10, 110
    roi = img[y0:h - 60, x0:w - 10]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    dark = ((hsv[:, :, 2] < 130) & (hsv[:, :, 1] < 90)).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, _l, stats, _c = cv2.connectedComponentsWithStats(dark, 8)
    if n <= 1:
        return 0
    i = max(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA])
    return int(stats[i, cv2.CC_STAT_WIDTH])


def dialog_state(session):
    import m7_common as m7
    from harness import export_util
    out = []
    dlg = m7.wait_dialog(session.pid, timeout_s=0.4)
    if dlg:
        kids = [t.strip() for t, _r, _h in
                export_util._children_texts(dlg[3]) if t.strip()]
        out.append(f"dlg title={dlg[1]!r} kids={kids[:8]}")
    edits = [t for t, _r, _h in
             export_util._children_texts(session.hwnd) if t.strip()]
    if edits:
        out.append(f"main-kids={edits[:6]}")
    return " ".join(out)


def add_plate_verified(session):
    """加盘 + 宽度验证，最多 3 次。"""
    import m7_common as m7
    w0 = plate_width(session)
    for i in range(3):
        m7.click_slot(session, 756)
        time.sleep(4.0)
        w1 = plate_width(session)
        print(f"{LOG} add-plate try{i + 1}: {w0} -> {w1}")
        if w0 and w1 and w1 >= w0 * 1.25:
            return True
    return False


def part_a(session):
    """下拉菜单：只枚举 Edit/View 两个子菜单。"""
    import m7_common as m7
    from harness import topbar_util
    for want in ("edit", "view"):
        menu = topbar_util.open_dropdown_menu(session)
        if not menu:
            print(f"{LOG} A: dropdown did not open")
            return
        mrect, mhwnd, mhmenu = menu
        items = m7.list_menu(mhmenu)
        idx = next((i for i, l in items if want in l.lower()), None)
        if idx is None:
            print(f"{LOG} A: no {want!r} row")
            m7.dismiss_menus(session)
            continue
        topbar_util.hover_row(mrect, len(items), idx)
        sub = topbar_util.wait_submenu(session.pid, {mhwnd}, timeout_s=3.0)
        if not sub or sub[1] == mhwnd:
            print(f"{LOG} A: {want} has no submenu")
            m7.dismiss_menus(session)
            continue
        sub_items = m7.list_menu(sub[2])
        print(f"{LOG} A submenu[{want}]: {[l for _i, l in sub_items]}")
        m7.dismiss_menus(session)
        time.sleep(1.0)


def part_b(session):
    """两盘确认后：全带 hover 差分扫描 + 簇点击/双击取证 + 终态盘数。"""
    import m7_common as m7
    from harness import winutil as wu

    if not add_plate_verified(session):
        print(f"{LOG} B: add-plate FAILED (stayed single-plate) — abort scan")
        return
    print(f"{LOG} B: two plates confirmed, LABEL-TWO-PLATES")

    # 两个侧翼带（plate4 证据：左盘列 ~x1017-1047、右盘列 ~x1372-1412）
    xs = list(range(980, 1081, 12)) + list(range(1340, 1441, 12))
    grid = [(x, y) for y in range(268, 481, 14) for x in xs]
    print(f"{LOG} B grid={len(grid)} points")
    hits = []
    for i, (x, y) in enumerate(grid):
        sx, sy = m7.client(session, x, y)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.30)
        idle1 = snap(session)
        time.sleep(0.25)
        idle2 = snap(session)
        time.sleep(0.45)
        hov = snap(session)
        noise = crop_diff(idle1, idle2, x, y)
        signal = crop_diff(idle2, hov, x, y)
        if noise < 1.0 and signal > 3.0 and signal > 3 * max(noise, 0.5):
            hits.append((x, y, round(signal, 1)))
            print(f"{LOG} B HIT @({x},{y}) signal={signal:.1f}")
        if i % 40 == 0:
            print(f"{LOG} B scan {i}/{len(grid)} hits={len(hits)}")
    clusters = []
    for x, y, s in hits:
        for c in clusters:
            if abs(c[0] - x) <= 15 and abs(c[1] - y) <= 15:
                if s > c[2]:
                    c[0], c[1], c[2] = x, y, s
                break
        else:
            clusters.append([x, y, s])
    clusters.sort(key=lambda c: (c[0] // 300, c[1]))
    print(f"{LOG} B clusters={clusters}")
    print(f"{LOG} LABEL-CLUSTERS-DONE")

    for j, (x, y, s) in enumerate(clusters):
        sx, sy = m7.client(session, x, y)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(2.2)
        print(f"{LOG} B CLICK{j} @({x},{y}) -> plate_w={plate_width(session)} "
              f"frac={m7.model_colored_frac(session):.3%} {dialog_state(session)}")
        print(f"{LOG} LABEL-CLICK{j}-AFTER")
        dlg = m7.wait_dialog(session.pid, timeout_s=0.4)
        if dlg:
            m7.click_dialog_button(dlg[3], "cancel", fallback_first=False)
            time.sleep(1.0)
    for j, (x, y, s) in enumerate(clusters[:5]):
        sx, sy = m7.client(session, x, y)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(0.12)
        wu.real_click_screen(sx, sy)
        time.sleep(2.0)
        print(f"{LOG} B DBLCLICK{j} @({x},{y}) -> {dialog_state(session)}")
        print(f"{LOG} LABEL-DBLCLICK{j}-AFTER")
        dlg = m7.wait_dialog(session.pid, timeout_s=0.4)
        if dlg:
            m7.click_dialog_button(dlg[3], "cancel", fallback_first=False)
            time.sleep(1.0)
    if m7.save_project_as(session, PROJ):
        import re
        import zipfile
        with zipfile.ZipFile(PROJ) as z:
            cfg = z.read("Metadata/model_settings.config").decode(
                "utf-8", "replace")
        plates = re.findall(r'key="plater_id" value="(\d+)"', cfg)
        print(f"{LOG} B final plate count={len(plates)} ids={plates}")
    else:
        print(f"{LOG} B final save FAILED")


def main() -> int:
    import m7_common as m7
    import m8_common as m8
    from m3_common import add_common_args, boot_session

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4%}")
        m7.ensure_maximized(session)
        part_a(session)
        part_b(session)
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
