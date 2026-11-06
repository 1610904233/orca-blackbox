#!/usr/bin/env python3
# probe_241_plate8.py — 盘侧图标列标定 v3（对角条带版）
#
# plate7 教训：hover 差分在竖带零命中 → 视觉分析 two_plates.png 破局：
# **图标列沿盘面左上斜边对角排列**（盘02 条带 ≈ x1410..1555 / y225..310，
# ~5 图标；盘01 ≈ x990..1195 / y475..620）——老探针全在竖带上扫，必然空。
# v3：对角带 hover 差分（无副作用）→ 命中点/粗网格点击差分取证
# （盘宽坍缩即重加盘、弹窗即取消、记录 dialog/Edit 状态）。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPlate8]"
STL = HERE / "fixtures" / "Prusa.stl"
PROJ = HERE / "artifacts" / "probe_241_plate8.3mf"
BAND = (1400, 215, 1565, 320)      # 盘02 对角条带（client 坐标，最大化窗口）


def crop_diff(a, b, x, y, r=24):
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


def hover_scan(session):
    """对角带 hover 差分（无副作用），返回命中点列表。"""
    import m7_common as m7
    from harness import winutil as wu
    x0, y0, x1, y1 = BAND
    pts = [(x, y) for y in range(y0, y1, 12) for x in range(x0, x1, 14)]
    print(f"{LOG} hover grid={len(pts)}")
    hits = []
    for i, (x, y) in enumerate(pts):
        sx, sy = m7.client(session, x, y)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.28)
        idle1 = snap(session)
        time.sleep(0.22)
        idle2 = snap(session)
        time.sleep(0.45)
        hov = snap(session)
        noise = crop_diff(idle1, idle2, x, y)
        signal = crop_diff(idle2, hov, x, y)
        if noise < 1.0 and signal > 3.0 and signal > 3 * max(noise, 0.5):
            hits.append((x, y, round(signal, 1)))
            print(f"{LOG} HOVER-HIT @({x},{y}) signal={signal:.1f}")
        if i % 27 == 0:
            print(f"{LOG} hover {i}/{len(pts)} hits={len(hits)}")
    return hits


def click_scan(session, points):
    """点击差分取证：盘宽/彩色占比/对话框/Edit + 点位局部截图差分；
    盘宽坍缩（删盘）即重加盘后继续。"""
    import m7_common as m7
    from harness import winutil as wu
    for j, (x, y) in enumerate(points):
        if not (BAND[0] <= x <= BAND[2] and BAND[1] <= y <= BAND[3]):
            continue
        sx, sy = m7.client(session, x, y)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        before = snap(session)
        wu.real_click_screen(sx, sy)
        time.sleep(2.2)
        after = snap(session)
        d = crop_diff(before, after, x, y, r=40)
        w_after = plate_width(session)
        st = (f"pixdiff={d:.1f} plate_w={w_after} "
              f"frac={m7.model_colored_frac(session):.3%} {dialog_state(session)}")
        print(f"{LOG} CLICK{j} @({x},{y}) -> {st}")
        print(f"{LOG} LABEL-CLICK{j}-AFTER")
        dlg = m7.wait_dialog(session.pid, timeout_s=0.4)
        if dlg:
            m7.click_dialog_button(dlg[3], "cancel", fallback_first=False)
            time.sleep(1.0)
        if w_after and w_after < 500:      # 宽度坍缩 = 盘被删了 → 重加
            print(f"{LOG} plate likely deleted, re-adding")
            add_plate_verified(session)


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
        if not add_plate_verified(session):
            print(f"{LOG} add-plate FAILED — abort")
            return 1
        print(f"{LOG} LABEL-TWO-PLATES")
        hits = hover_scan(session)
        if hits:
            clusters = []
            for x, y, s in hits:
                for c in clusters:
                    if abs(c[0] - x) <= 18 and abs(c[1] - y) <= 18:
                        if s > c[2]:
                            c[0], c[1], c[2] = x, y, s
                        break
                else:
                    clusters.append([x, y, s])
            pts = [(c[0], c[1]) for c in clusters]
        else:
            # hover 无高亮 → 沿对角线粗点击（左下→右上扫过条带）
            pts = [(1420 + 11 * k, 300 - 6 * k) for k in range(13)]
        print(f"{LOG} click points={pts}")
        click_scan(session, pts)
        if m7.save_project_as(session, PROJ):
            import re
            import zipfile
            with zipfile.ZipFile(PROJ) as z:
                cfg = z.read("Metadata/model_settings.config").decode(
                    "utf-8", "replace")
            plates = re.findall(r'key="plater_id" value="(\d+)"', cfg)
            print(f"{LOG} final plate count={len(plates)} ids={plates}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
