#!/usr/bin/env python3
# probe_241_picker8.py — 我们的用户预设（... - STD-TEST 等）在选择框里的位置
#
# 已知：左栏 = System presets 段（Snapmaker/Generic/其他厂商 + Add/Remove filament 尾部），
# 没有 Custom/用户配置 行；右栏 = 选中供应商的二级耗材列表（Snapmaker 层 8 项置顶）。
# 本轮：选 Snapmaker，然后把**右栏滚到底**，找 'STD-TEST' / '@U1 - ' 这类用户预设行；
#       再把左栏滚到底，找有没有用户/项目分组。
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

LOG = "[pk248]"
ART = HERE / "artifacts"


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xP8_{name}.png"), img)
    print(f"{LOG} shot -> m8xP8_{name}.png")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        slots = m8.wait_slots(session)
        hit = next((s for s in slots if s["slot"] == 2), None)
        ch = hit["combo"][2]

        pop, ch2, how = m8._picker_open(session, 2)
        print(f"{LOG} picker opened via {how!r}")
        time.sleep(0.8)
        panes = m8._picker_panes(session)
        vend = next((p for p in panes if p["is_vendor"]), None)
        filt = m8._filament_pane(session, panes)
        print(f"{LOG} panes: {[(p['rect'], p['is_vendor']) for p in panes]}")
        # 选 Snapmaker（先上滚露出顶部）
        for _i in range(10):
            winutil.real_wheel_screen(vend["rect"][0] + 40, (vend["rect"][1] + vend["rect"][3]) // 2, 3)
            time.sleep(0.12)
        time.sleep(0.5)
        panes = m8._picker_panes(session)
        vend = next((p for p in panes if p["is_vendor"]), None)
        print(f"{LOG} left pane rows (top): {[t[:30] for _y, t, _x in vend['rows']][:14]}")
        m8._picker_click_text(session, vend["rows"], "Snapmaker", startswith=True)
        time.sleep(1.2)
        # 右栏滚到底
        for tag in ("after_0", "after_20", "after_50"):
            n = {"after_0": 0, "after_20": 20, "after_50": 50}[tag]
            for _i in range(n):
                winutil.real_wheel_screen(filt["rect"][0] + 40, (filt["rect"][1] + filt["rect"][3]) // 2, -3)
                time.sleep(0.08)
            if n:
                time.sleep(0.6)
            panes = m8._picker_panes(session)
            filt = m8._filament_pane(session, panes)
            rows = [t for _y, t, _x in filt["rows"]] if filt else []
            hits = [t for t in rows if "test" in t.lower() or "STD" in t or "@U1 -" in t]
            print(f"{LOG} right pane {tag}: rows={rows[:12]} hits={hits}")
            shot(f"right_{tag}", filt["rect"] if filt else None)
        # 左栏滚到底
        for _i in range(40):
            winutil.real_wheel_screen(vend["rect"][0] + 40, (vend["rect"][1] + vend["rect"][3]) // 2, -3)
            time.sleep(0.08)
        time.sleep(0.6)
        panes = m8._picker_panes(session)
        vend = next((p for p in panes if p["is_vendor"]), None)
        rows = [t for _y, t, _x in vend["rows"]] if vend else []
        print(f"{LOG} left pane (bottom): {rows[:16]}")
        shot("left_bottom", vend["rect"] if vend else None)
        user32 = winutil.user32
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.6)
        print(f"{LOG} combo after probe: {m8.combo_text(ch)!r}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
