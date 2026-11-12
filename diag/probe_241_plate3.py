#!/usr/bin/env python3
# probe_241_plate3.py — 盘条（≥2 盘时出现）与盘操作入口标定
#   #194 移除当前板 / #197 锁定当前板 / #198 编辑盘名称
#
# 关键认知：单个盘时底部**没有盘条**；点「Add plate」之后盘条出现，盘操作入口
# 在盘条右侧（或盘条右键菜单）。本探针：加盘 → 截图 → hover/右键探测 → 打印。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkPlate3]"
STL = HERE / "fixtures" / "Prusa.stl"


def toplevel_menus(session):
    from harness import topbar_util
    return topbar_util._enum_menu_windows(session.pid)


def main() -> int:
    import m7_common as m7
    import m8_common as m8
    import m8x_152 as base
    from m3_common import add_common_args
    from harness import winutil as _wu

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = base.m7_boot(args, model=STL)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        # 1) 加第二个盘 → 盘条出现
        print(f"{LOG} LABEL-ONE-PLATE")
        time.sleep(0.4)
        m7.click_slot(session, 756)
        time.sleep(4.0)
        print(f"{LOG} LABEL-TWO-PLATES")
        time.sleep(0.4)

        # 2) 盘条区域 hover 读 tooltip（y 990..1030）
        for y in (995, 1005, 1015, 1025):
            for x in range(600, 1100, 50):
                tip = m7.tooltip_text(session, x, y, dwell_s=0.8)
                if tip and len(tip) > 2:
                    print(f"{LOG} bar @({x},{y}): {tip!r}")

        # 3) 盘条右键：几个候选点
        for pt in ((680, 1015), (760, 1015), (900, 1015), (1160, 1015),
                   (1200, 1015)):
            sx, sy = m7.client(session, *pt)
            _wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.25)
            _wu.real_right_click_screen(sx, sy)
            deadline = time.monotonic() + 2.5
            got = None
            while time.monotonic() < deadline:
                menus = toplevel_menus(session)
                if menus:
                    got = menus[0]
                    break
                time.sleep(0.25)
            if got:
                from harness import topbar_util
                hmenu = topbar_util.menu_hmenu(got[4])
                print(f"{LOG} right-click @{pt}: {[l for _i, l in m7.list_menu(hmenu)]}")
                m7.dismiss_menus(session)
            else:
                print(f"{LOG} right-click @{pt}: no menu")
        # 4) 盘条右侧可能有一列操作图标：hover 一带
        for x in (1440, 1460, 1480, 1500, 1520, 1540):
            for y in (960, 980, 1000, 1020):
                tip = m7.tooltip_text(session, x, y, dwell_s=0.8)
                if tip and len(tip) > 2:
                    print(f"{LOG} right-col @({x},{y}): {tip!r}")
        print(f"{LOG} LABEL-PROBE-DONE")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
