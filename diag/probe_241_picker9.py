#!/usr/bin/env python3
# probe_241_picker9.py — 在 2.4.1 耗材选择框里定位我们的用户预设（... - STD-TEST）
#
# 已知：左栏 = System presets 段（厂商）+ Add/Remove filament 尾部；右栏 = 该厂商的耗材
# （按 ABS/PETG/PLA… 类目分组）。datadir 里用户预设确实存在（user\default\filament\...）。
# 本轮：选 Snapmaker，然后**逐步**滚右栏（每 4 格 OCR 一次，最多 30 步），找 'STD-TEST'/'TEST'。
import argparse
import sys
import time
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

LOG = "[pk249]"
ART = HERE / "artifacts"


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xP9_{name}.png"), img)
    print(f"{LOG} shot -> m8xP9_{name}.png")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        m8.wait_slots(session)
        pop, ch, how = m8._picker_open(session, 2)
        print(f"{LOG} picker opened via {how!r}")
        time.sleep(0.8)
        panes = m8._picker_panes(session)
        vend = next((p for p in panes if p["is_vendor"]), None)
        filt = m8._filament_pane(session, panes)
        print(f"{LOG} panes: {[(p['rect'], p['is_vendor']) for p in panes]}")
        # 确保停在 Snapmaker（若左栏露出 Snapmaker 行就点它；否则说明当前就是 Snapmaker）
        for _i in range(10):
            winutil.real_wheel_screen(vend["rect"][0] + 40, (vend["rect"][1] + vend["rect"][3]) // 2, 3)
            time.sleep(0.1)
        time.sleep(0.5)
        panes = m8._picker_panes(session)
        vend = next((p for p in panes if p["is_vendor"]), None)
        print(f"{LOG} left pane: {[t[:28] for _y, t, _x in vend['rows']][:14]}")
        if m8._picker_click_text(session, vend["rows"], "Snapmaker", startswith=True):
            time.sleep(1.2)
            panes = m8._picker_panes(session)
            filt = m8._filament_pane(session, panes)
        print(f"{LOG} right pane at start: {[t[:26] for _y, t, _x in filt['rows']][:12]}")
        found = []
        x = filt["rect"][0] + 40
        y = (filt["rect"][1] + filt["rect"][3]) // 2
        for step in range(30):
            for _i in range(4):
                winutil.real_wheel_screen(x, y, -3)
                time.sleep(0.08)
            time.sleep(0.45)
            panes = m8._picker_panes(session)
            f2 = m8._filament_pane(session, panes)
            if not f2:
                print(f"{LOG} step {step}: right pane vanished")
                break
            rows = [t for _y, t, _x in f2["rows"]]
            hits = [t for t in rows if "TEST" in t.upper()]
            if step % 5 == 0 or hits:
                print(f"{LOG} step {step}: {rows[:10]}  hits={hits}")
            if hits:
                found = hits
                shot(f"found_step{step}", f2["rect"])
                break
        print(f"{LOG} RESULT hits={found}")
        if not found:
            shot("end", filt["rect"])
            print(f"{LOG} end rows: {[t for _y, t, _x in filt['rows']]}")
        winutil.user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        winutil.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.6)
        print(f"{LOG} combo after probe: {m8.combo_text(ch)!r}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
