#!/usr/bin/env python3
# probe_242_mix.py — 242d 混色（Add/Edit Mix）对话框控件标定（§4 第 5 项）
#
# 242c 现象（HANDOFF §3-④）：对话框能打开、能读到默认模式 Auto，但
# switch_combo 切 Manual 失败（popup 行点击无效）→ 需要重新标定 242d 的
# 控件几何。本探针：
#   1) 入口：侧栏 'Color Mixing Match' 标题栏加号 → 对话框是否打开
#   2) 对话框：全部子控件 (text/class/rect) + PrintWindow 截图 + OCR
#   3) Auto/Manual combo：当前文本；点击后弹层（wxWindowNR 'panel'）的
#      rect/子控件/截图/OCR 行位置（旧标定：行 28px、首行 top+14）
#   4) 对照：按 OCR 到的 'Manual' 词位真实点击 vs 旧行距公式位
#   5) 四个模式 tab（Ratio/Cycle/Match/Gradient）OCR 词位
# 截图存 artifacts/shots/p242mix/，结论打日志。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import cv2
import m7_common as m7
import m8_common as m8
from harness import mix_dialog_util as mdu
from harness import mixing_util as mu
from harness import winutil
from m3_common import MIXED_3MF, add_common_args, boot_session

LOG = "[p242mix]"
SHOTS = HERE / "artifacts" / "shots" / "p242mix"


def shot(hwnd, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    w, h, bgra = winutil.capture_window(hwnd)
    img = np_from(bgra, w, h)
    p = SHOTS / name
    cv2.imwrite(str(p), img)
    print(f"{LOG} shot -> {p} ({w}x{h})")
    return img


def np_from(bgra, w, h):
    import numpy as np
    arr = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
    return arr[:, :, ::-1].copy()


def dump_children(hwnd, tag):
    rows = mu.children(hwnd)
    print(f"{LOG} {tag}: {len(rows)} children")
    for t, c, r, h in rows:
        vis = "?" if not hasattr(winutil.user32, "IsWindowVisible") else \
            bool(winutil.user32.IsWindowVisible(h))
        print(f"{LOG}   {c!r:14} {t!r:40} rect={r} hwnd={h} vis={vis}")
    return rows


def ocr_rows(img, tag):
    import pytesseract
    words = pytesseract.image_to_data(
        cv2.cvtColor(img, cv2.COLOR_BGR2RGB), output_type=pytesseract.Output.DICT)
    out = []
    for i, txt in enumerate(words["text"]):
        t = (txt or "").strip()
        if not t:
            continue
        x, y, w_, h_ = (words["left"][i], words["top"][i],
                        words["width"][i], words["height"][i])
        out.append((t, x, y, w_, h_))
        print(f"{LOG} {tag} ocr: {t!r} @({x},{y},{w_},{h_})")
    return out


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.3%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)

        # 1) 入口
        dlg = mu.open_mixing_dialog(session, timeout_s=12.0)
        if not dlg:
            print(f"{LOG} mix dialog DID NOT OPEN — sidebar children:")
            for t, c, r, h in mu.children(session.hwnd):
                if "mix" in (t or "").lower() or "color" in (t or "").lower():
                    print(f"{LOG}   {c!r} {t!r} rect={r}")
            shot(session.hwnd, "sidebar_no_dialog.png")
            return 1
        rect = mdu.dialog_rect(session.pid, dlg)
        print(f"{LOG} dialog hwnd={dlg} rect={rect} "
              f"title={mdu.dialog_title(session.pid, dlg)!r}")
        img = shot(dlg, "dialog.png")

        # 2) 子控件 + OCR
        dump_children(dlg, "dialog")
        words = ocr_rows(img, "dialog")

        # 3) Auto/Manual combo
        combo = mu.child_by_text(dlg, "Auto") or mu.child_by_text(dlg, "Manual")
        if not combo:
            print(f"{LOG} no Auto/Manual combo child found")
        else:
            t, c, r, ch = combo
            print(f"{LOG} combo: text={mu.combo_text(ch)!r} class={c!r} "
                  f"rect={r}")
            from harness.mixing_util import _msg_click
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            _msg_click(cx, cy)
            pr = None
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                for cls, txt, rr, hh in mu.toplevel(session.pid):
                    if cls == "wxWindowNR" and txt == "panel":
                        pr = (rr, hh)
                        break
                if pr:
                    break
                time.sleep(0.2)
            if not pr:
                print(f"{LOG} combo popup did NOT appear (wxWindowNR panel)")
            else:
                prr, ph = pr
                print(f"{LOG} popup rect={prr} hwnd={ph}")
                dump_children(ph, "popup")
                pimg = shot(ph, "combo_popup.png")
                prow = ocr_rows(pimg, "popup")
                man = next((wd for wd in prow
                            if wd[0].lower().startswith("man")), None)
                # 4) 对照：OCR 词位真实点击 vs 旧公式位（top+14+row*28）
                if man:
                    mx = prr[0] + man[1] + man[3] // 2
                    my = prr[1] + man[2] + man[4] // 2
                    print(f"{LOG} OCR 'Manual' row screen=({mx},{my}); "
                          f"old-formula row1 would be "
                          f"({(prr[0]+prr[2])//2},{prr[1]+14+28})")
                    winutil.user32.SetCursorPos(mx, my)
                    time.sleep(0.3)
                    winutil.real_click_screen(mx, my)
                    time.sleep(1.2)
                    print(f"{LOG} after OCR-guided click combo="
                          f"{mu.combo_text(ch)!r}")
                else:
                    print(f"{LOG} 'Manual' not OCR'd in popup — trying old "
                          f"formula row1")
                    _msg_click((prr[0] + prr[2]) // 2, prr[1] + 14 + 28)
                    time.sleep(1.0)
                    print(f"{LOG} after formula click combo="
                          f"{mu.combo_text(ch)!r}")

        # 5) 模式 tab 词位（Ratio/Cycle/Match/Gradient）
        for lbl in ("Ratio", "Cycle", "Match", "Gradient"):
            hit = next((wd for wd in words if wd[0].lower().startswith(
                lbl.lower()[:4])), None)
            print(f"{LOG} tab {lbl}: "
                  + (f"dialog-local @({hit[1]},{hit[2]})" if hit else "not OCR'd"))

        # 收尾：Cancel
        for t, c, r, h in mu.children(dlg):
            if t.strip().lower() == "cancel":
                from harness.mixing_util import _msg_click
                _msg_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
                time.sleep(1.0)
                print(f"{LOG} cancel clicked")
                break
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
