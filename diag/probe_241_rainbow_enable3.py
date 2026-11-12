#!/usr/bin/env python3
# ⚠️ 结论已被推翻（10-12）：见 probe_241_rainbow_enable.py 头部与 PITFALLS §21.3 ——
#    Rainbow 无需任何人工勾选，它就在 Snapmaker 二级列表里。
# probe_241_rainbow_enable3.py — 进入 Color Mixing Match → Filament Setup，找 Rainbow 勾选
#
# 已定位：侧栏 Filament Management 行第一个图标 (337,352) → `Color Mixing Match` 对话框
# （#32770，约 (702,146,1218,885)），内含 Match Mode / Filament Setup / 各耗材行。
# 本轮：把该对话框的控件树全 dump（含勾选态按钮），找 'Rainbow'/'Full Spectrum'/品牌配置，
#       勾上后看 datadir 差异 + 返回后耗材栏是否出现 Rainbow。
import argparse
import ctypes
import os
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pk254]"
ART = HERE / "artifacts"
DATADIR = Path(r"C:\coil\orca-blackbox\artifacts\m3_profile")
user32 = winutil.user32


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xPE_{name}.png"), img)
    print(f"{LOG} shot -> m8xPE_{name}.png")


def snap():
    out = {}
    for root, _d, files in os.walk(DATADIR):
        for f in files:
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
                out[p] = (st.st_size, int(st.st_mtime))
            except OSError:
                pass
    return out


def click_at(x, y, pause=1.3):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def kids(parent):
    return [(t.strip(), r, winutil.window_class(h), h)
            for t, r, h in export_util._children_texts(parent) if t.strip()]


def main() -> int:
    global session
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        m8.wait_slots(session)
        before = snap()
        click_at(337, 352)
        dlg = export_util.wait_toplevel(session.pid, lambda c, t, r: c == "#32770"
                                        and "mixing" in (t or "").lower(), timeout_s=5.0)
        print(f"{LOG} dialog: {dlg[1] if dlg else None} {dlg[2] if dlg else ''}")
        if not dlg:
            return 1
        shot("01_dialog", dlg[2])
        rows = kids(dlg[3])
        print(f"{LOG} dialog children ({len(rows)}):")
        for t, r, c, _h in sorted(rows, key=lambda x: (x[1][1], x[1][0])):
            print(f"{LOG}   {t[:44]!r} {r} {c}")
        # 找 Rainbow / Full Spectrum / 品牌配置入口
        for want in ("Rainbow", "Full Spectrum", "Setup", "Brand", "Configure", "Material"):
            hit = next(((t, r, c) for t, r, c, _h in rows if want.lower() in t.lower()), None)
            print(f"{LOG} search {want!r}: {hit[:2] if hit else None}")
        target = next(((t, r, c) for t, r, c, _h in rows
                       if "rainbow" in t.lower() or "spectrum" in t.lower()), None)
        if target:
            t, r, c = target
            print(f"{LOG} >>> clicking {t!r} @{r} ({c})")
            click_at((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, 1.5)
            shot("02_after_click", dlg[2])
            rows2 = kids(dlg[3])
            print(f"{LOG} children after click ({len(rows2)}):")
            for t2, r2, c2, _h in sorted(rows2, key=lambda x: (x[1][1], x[1][0]))[:28]:
                print(f"{LOG}   {t2[:44]!r} {r2} {c2}")
        else:
            # 没直接看到 Rainbow：把 'Filament Setup' 区里的行都列出来（含按钮=勾选框）
            setup = next(((t, r) for t, r, _c, _h in rows if "setup" in t.lower()), None)
            print(f"{LOG} Filament Setup row: {setup}")
            boxes = [(t, r, c) for t, r, c, _h in rows if c == "Button"]
            print(f"{LOG} button-ish children (candidate checkboxes): {[(t[:18], r) for t, r, _c in boxes][:20]}")
        # 关对话框（先试 OK/确认，再 Esc）
        okb = next(((t, r) for t, r, c, _h in kids(dlg[3]) if t.lower() in ("ok", "confirm", "确定")), None)
        if okb:
            print(f"{LOG} clicking {okb[0]!r}")
            click_at((okb[1][0] + okb[1][2]) // 2, (okb[1][1] + okb[1][3]) // 2, 1.5)
        else:
            user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.8)
        after = snap()
        changed = [p for p in after if p not in before or after[p] != before[p]]
        print(f"{LOG} datadir changed: {len(changed)}")
        for p in changed[:10]:
            print(f"{LOG}   {p.replace(str(DATADIR), '')} {after[p]}")
        # 回到耗材栏确认 Rainbow 是否可选
        pop, ch, how = m8._picker_open(session, 2)
        if pop:
            time.sleep(0.8)
            panes = m8._picker_panes(session)
            vend = next((p for p in panes if p["is_vendor"]), None)
            vendrow = next(((y, t, x) for y, t, x in vend["rows"] if "snapmaker" in t.lower()), None) if vend else None
            if vendrow:
                click_at(max(20, vendrow[2]) + 55, vendrow[0], 1.2)
                time.sleep(0.8)
            found = []
            f = m8._filament_pane(session)
            for step in range(12):
                rows3 = [t for _y, t, _x in (f["rows"] if f else [])]
                hits = [t for t in rows3 if "rainbow" in t.lower() or "spectrum" in t.lower()]
                if hits:
                    found = hits
                    break
                winutil.real_wheel_screen((f["rect"][0] + 40) if f else 600,
                                          ((f["rect"][1] + f["rect"][3]) // 2) if f else 600, -3)
                time.sleep(0.3)
                f = m8._filament_pane(session)
            print(f"{LOG} picker Rainbow hits: {found}")
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.6)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
