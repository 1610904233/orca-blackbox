#!/usr/bin/env python3
# probe_241_merge_target.py — 「合并到 x 号」到底叫不叫得动？
#
# 实测背景（10-16）：m8x_152 s4 里对象指到 4 号槽（红）后，点 '...' → Merge with
# → 第 2 项（徽标 '2' = 2 号槽），并完槽位 4→3，但对象主色 + gcode 都落在 **1 号槽**。
# 两种解释：(a) app 忽略所选目标、一律并到首槽；(b) 台架的 y 其实点在第 1 项上。
# 本探针用"并到第 3 项（徽标 '3' = 3 号槽）"来分辨：若对象落到 3 号槽 → 目标被
# 遵守（(b)）；若仍落到 1 号槽 → app 忽略目标（(a)）。
#
# 产出：artifacts/probe_241_merge_target.log（对象主色 / 槽位色板 / gcode 不涉及）
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
sys.path.insert(0, str(HERE / "tests" / "mainflow"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from m3_common import add_common_args  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
import m8x_152 as cx  # noqa: E402  (复用用例里的原语)

LOG = "[pkTgt]"
STL = HERE / "fixtures" / "Prusa.stl"


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = cx.m7_boot(args, model=STL)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        pt = m7.select_object_strict(session)
        print(f"{LOG} object point = {pt}")
        if not pt:
            return 1
        colors = {s["slot"]: m8.slot_swatch_rgb(session, s["slot"])
                  for s in m8.filament_slots(session)}
        print(f"{LOG} slot colours = {colors}")
        obj0 = cx.object_color(session, pt)
        print(f"{LOG} object colour before = {obj0} -> slot "
              f"{cx.nearest_slot(obj0, colors)[0]}")
        # 1) 指到 4 号槽（按索引点最后一行）
        (shwnd, shmenu), pt = cx.open_cf_submenu(session, pt)
        if shmenu is None:
            print(f"{LOG} no object menu")
            return 1
        rows = m7.list_menu(shmenu)
        cand = [(i, l) for i, l in rows
                if l.strip() and l.lower() != "default"]
        last_i = cand[-1][0]
        print(f"{LOG} CF rows = {len(cand)}, clicking last index {last_i}")
        cx.click_menu_index(session, shwnd, shmenu, last_i)
        time.sleep(2.5)
        obj1 = cx.object_color(session, pt)
        print(f"{LOG} object colour after assign to slot 4 = {obj1} -> slot "
              f"{cx.nearest_slot(obj1, colors)[0]}")
        # 2) 合并到第 3 行（徽标 '3' = 3 号槽）
        merged, tgt = cx.merge_slot_into(session, 4, want_slot=3)
        print(f"{LOG} mergeSlotInto(4, want 3) -> merged={merged} tgt={tgt}")
        if not merged:
            return 1
        time.sleep(2.5)
        colors2 = {s["slot"]: m8.slot_swatch_rgb(session, s["slot"])
                   for s in m8.filament_slots(session)}
        obj2 = cx.object_color(session, pt)
        s2, d2 = cx.nearest_slot(obj2, colors)
        print(f"{LOG} survivors={sorted(colors2)}")
        print(f"{LOG} object colour after merge = {obj2} -> slot {s2} "
              f"(d={d2:.0f})")
        print(f"{LOG} VERDICT: target honoured={s2 == 3} "
              f"(landed on slot {s2}; 3 = honoured, 1 = app ignores target)")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
