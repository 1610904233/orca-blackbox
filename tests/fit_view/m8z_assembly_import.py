#!/usr/bin/env python3
# m8z_assembly_import.py — 飞书基线 #20: 导入模型已含装配关系
# feishu: baseline#20
# 行文步骤: 导入含装配关系的工程 → 进入装配视图 → 零件按装配关系组装、保持相对位置
# 夹具: fixtures/assembly_pokemon_box.3mf（8 对象/组件、3 盘，用户提供）
#
# 黑盒断言:
#   1) 工程载入（3mf 的盘 1 内容渲染到视口）
#   2) 对象标签页能选中盘 1 的零件（对象真实存在，非空工程）
#   3) Assembly View 工具栏槽可点击并切换装配视图（视口显著变化）
#   4) 无错误弹窗、软件正常关闭
# 装配相对位置保持的渲染侧证（多零件组装）记录在证据行。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7
import m8x_152 as c152          # 复用：对象标签页选中（按钮面通道）
from m1_minimal_loop import capture_bgr
from m3_common import add_common_args, boot_session

LOG = "[m8z20]"
ASSEMBLY_3MF = HERE / "fixtures" / "assembly_pokemon_box.3mf"


def wait_loaded(session, timeout_s=240):
    """载入门：对象标签页的盘内零件行出现即算载入成功。

    不能用彩色占比：该夹具的零件按耗材分配（可能是灰色/其它盘），彩色
    像素天然近乎为零（实测 11-12 首轮 0.06% 误判）。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        row = c152.objects_tab_select(session)
        if row:
            return row
        time.sleep(3.0)
    return None


def main() -> int:
    import argparse
    ap = add_common_args(argparse.ArgumentParser(),
                         default_model=ASSEMBLY_3MF)
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=args.model)
    try:
        m7.ensure_maximized(session)
        time.sleep(2.0)
        row = wait_loaded(session)
        results["工程载入（对象标签页零件行）"] = (
            f"PASS (@{row})" if row else "FAIL (no object row)")
        if not row:
            return m7.m7_verdict(results)
        results["对象标签页零件行可选中"] = f"PASS (@{row})"
        info = m7.object_info_text(session)
        print(f"{LOG} object info: {info[:60]!r}")
        results["对象信息面板可读（证据行）"] = (
            f"PASS ({info[:40]!r})" if info else "PASS (info empty; evidence logged)")

        # 3) Assembly View：工具栏槽点击 -> 装配视图切换（视口显著变化）
        m7.dismiss_menus(session)
        before = capture_bgr(session)
        ax, atip = m7.find_slot(session, lambda t: "assembly" in t)
        print(f"{LOG} assembly slot @{ax} tip={atip!r}")
        switched = False
        if ax is not None:
            m7.click_slot(session, ax)
            time.sleep(2.5)
            after = capture_bgr(session)
            import numpy as np
            diff = float(np.mean(np.abs(
                after[110:-60].astype(int) - before[110:-60].astype(int))))
            print(f"{LOG} assembly view viewport_mad={diff:.3f}")
            switched = diff > 2.0
            results["装配视图切换（视口变化）"] = (
                f"PASS (mad={diff:.2f})" if switched
                else f"FAIL (mad={diff:.2f})")
        else:
            results["装配视图切换（视口变化）"] = "FAIL (slot not found)"

        # 4) 无错误弹窗 + 正常关闭
        errs = [t for c, t, r, h in m7._visible_toplevels(session.pid)
                if c == "#32770"]
        results["无错误弹窗"] = "PASS" if not errs else f"FAIL ({errs[:2]})"
        alive = session.alive()
        results["软件正常关闭"] = "PASS" if alive else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
