#!/usr/bin/env python3
# probe_241_slottable.py — 在 2.4.1 上导出土著「工具条槽位表」
#
# 2.4.2 上工具条 tooltip 完全取不到（jump/nudge/slide-in 三种挂法都没有
# tooltip 窗口、OCR 也为空）→ 2.4.2 不能靠 tooltip 找槽位。
# 方案：在 2.4.1（tooltip 可用）把整条工具条 x→tooltip 抄下来存成表，
# 作为 2.4.2 的固定几何回退表（两版视觉布局一致，需在 2.4.2 上用效果验证）。
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7
import m8_common as m8
from harness import winutil as wu
from m3_common import add_common_args, boot_session

LOG = "[p241t]"


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(),
                         default_model=HERE / "fixtures" / "Prusa.stl")
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.3%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        sx, sy = m7.client(session, m7.VIEWPORT_X0 + 60, 700)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(1.0)
        img = m7.capture_bgr(session)
        w = img.shape[1]
        table = []
        for cy in (76, 84, 92):
            for cx in range(m7.VIEWPORT_X0 + 40, w - 120, 18):
                tip = m7.tooltip_text(session, cx, cy, dwell_s=1.0)
                if tip:
                    table.append({"x": cx, "y": cy, "tip": tip})
        print(f"{LOG} raw hits={len(table)}")
        # 去重：同一条 tip 取最小 x
        best = {}
        for h in table:
            key = h["tip"].strip().lower()
            if key not in best or h["x"] < best[key]["x"]:
                best[key] = h
        rows = sorted(best.values(), key=lambda r: r["x"])
        out = HERE / "artifacts" / "slot_table_241.json"
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        for r in rows:
            print(f"{LOG} x={r['x']:4d} y={r['y']} tip={r['tip']!r}")
        print(f"{LOG} saved {out} ({len(rows)} unique)")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
