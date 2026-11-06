#!/usr/bin/env python3
# probe_241_plate9.py — 盘侧图标列标定 v4：全条带点击网格取证
#
# plate8 结论：hover 差分恒 0（图标条在光标位于盘区时**持续渲染**，idle 基线
# 里也在，差分看不见）；对角猜线 13 点中仅 (1442,288)/(1453,282) 两个相邻点
# 有反应（pixdiff≈10 + frac 瞬变）= 命中 1 个图标。→ v4 改为全条带点击网格
# （12×8），反应点存全幅 PNG 供视觉复核，盘宽坍缩即重加盘、弹窗即取消。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPlate9]"
STL = HERE / "fixtures" / "Prusa.stl"
PROJ = HERE / "artifacts" / "probe_241_plate9.3mf"
OUT = HERE / "artifacts" / "shots" / "probe_plate9"
BAND = (1400, 215, 1565, 320)


def snap_gray(session):
    import cv2
    from harness.anchors import capture_bgr
    return cv2.cvtColor(capture_bgr(session), cv2.COLOR_BGR2GRAY)


def snap_bgr(session):
    from harness.anchors import capture_bgr
    return capture_bgr(session)


def crop_diff(a, b, x, y, r=26):
    h, w = a.shape[:2]
    x0, x1 = max(0, x - r), min(w, x + r)
    y0, y1 = max(0, y - r), min(h, y + r)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    d = abs(a[y0:y1, x0:x1].astype(int) - b[y0:y1, x0:x1].astype(int))
    return float(d.mean())


def plate_width(session):
    import cv2
    import numpy as np
    import m7_common as m7
    img = snap_bgr(session)
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


def main() -> int:
    import cv2
    import m7_common as m7
    import m8_common as m8
    from m3_common import add_common_args, boot_session
    from harness import winutil as wu

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4%}")
        m7.ensure_maximized(session)
        if not add_plate_verified(session):
            print(f"{LOG} add-plate FAILED — abort")
            return 1
        print(f"{LOG} LABEL-TWO-PLATES")
        base_frac = m7.model_colored_frac(session)
        base_w = plate_width(session)
        print(f"{LOG} base: frac={base_frac:.3%} w={base_w}")

        x0, y0, x1, y1 = BAND
        grid = [(x, y) for y in range(y0, y1, 15) for x in range(x0, x1, 14)]
        print(f"{LOG} click grid={len(grid)}")
        for i, (x, y) in enumerate(grid):
            sx, sy = m7.client(session, x, y)
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            before = snap_gray(session)
            wu.real_click_screen(sx, sy)
            time.sleep(2.2)
            after = snap_gray(session)
            d = crop_diff(before, after, x, y, r=34)
            f = m7.model_colored_frac(session)
            w = plate_width(session)
            frac_d = abs(f - base_frac)
            dlg = dialog_state(session)
            interesting = d > 4.0 or frac_d > 0.0005 or dlg
            print(f"{LOG} C{i} @({x},{y}) d={d:.1f} frac={f:.3%} "
                  f"w={w} {dlg}{'  <-- REACT' if interesting else ''}")
            if interesting:
                print(f"{LOG} LABEL-REACT{i}")
                img = snap_bgr(session)
                cv2.imwrite(str(OUT / f"react{i}_{x}_{y}.png"), img)
            d2 = m7.wait_dialog(session.pid, timeout_s=0.4)
            if d2:
                m7.click_dialog_button(d2[3], "cancel", fallback_first=False)
                time.sleep(1.0)
            if w and base_w and w < base_w * 0.85:   # 盘被删 → 重加
                print(f"{LOG} plate deleted at C{i}, re-adding")
                add_plate_verified(session)
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
