#!/usr/bin/env python3
# probe_241_plate4.py — 盘侧图标列 hover 标定（#194/#197/#198 用）
#
# 两盘布局下，每个盘右/左前方有一列图标（帧取证 artifacts/videos/m8x_186/
# two_plates.png）：当前盘 02 的那列约在 x 1372..1412、y 288..470，间距 ~26px。
# 本探针只 hover 读 tooltip（不点击），把图标语义读出来。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPlate4]"
STL = HERE / "fixtures" / "Prusa.stl"


def main() -> int:
    import m7_common as m7
    import m8_common as m8
    import m8x_152 as base
    from m3_common import add_common_args

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = base.m7_boot(args, model=STL)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        m7.click_slot(session, 756)          # 加第二个盘 → 盘列出现
        time.sleep(4.0)
        print(f"{LOG} LABEL-TWO-PLATES")
        time.sleep(0.4)
        # 当前盘（02，深色）的图标列：7 个候选点
        cands = [(1390, 292), (1394, 318), (1397, 344), (1400, 370),
                 (1403, 396), (1406, 422), (1409, 448)]
        for (x, y) in cands:
            tip = m7.tooltip_text(session, x, y, dwell_s=1.4)
            print(f"{LOG} icon @({x},{y}) tip={tip!r}")
        # 也试左盘（01，灰）那一列
        for (x, y) in ((1017, 435), (1022, 461), (1027, 487), (1032, 513),
                       (1037, 539), (1042, 565), (1047, 591)):
            tip = m7.tooltip_text(session, x, y, dwell_s=1.2)
            print(f"{LOG} left-plate icon @({x},{y}) tip={tip!r}")
        print(f"{LOG} LABEL-ICONS-DONE")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
