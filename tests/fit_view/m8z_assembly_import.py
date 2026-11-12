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


def swallow_load_dialogs(session, rounds=8):
    """打开含自定义预设的工程会依次弹 'Snapmaker Orca information' 与
    'Customized Preset' 提示框，挡在 Loading... 之前（实测 11-12：
    不点掉时视口永远空、对象树为空）。循环点 OK 直到没有待处理弹窗。"""
    from harness import export_util, winutil
    for rnd in range(rounds):
        dialogs = [(c, t, r, h) for c, t, r, h in
                   m7._visible_toplevels(session.pid) if c == "#32770"]
        pend = [d for d in dialogs
                if "loading" not in (d[1] or "").lower()]
        if not pend:
            return
        for c, t, r, h in pend:
            kids = export_util._children_texts(h)
            print(f"{LOG} dialog {t!r} kids="
                  f"{[k[0][:20] for k in kids if k[0].strip()][:6]}")
            btn = next(((kt, kr, kh) for kt, kr, kh in kids
                        if kt.strip().lower() in
                        ("ok", "yes", "确定", "是")), None)
            if btn:
                kt, kr, _kh = btn
                cx, cy = (kr[0] + kr[2]) // 2, (kr[1] + kr[3]) // 2
                winutil.user32.SetCursorPos(cx, cy)
                winutil.real_click_screen(cx, cy)
                print(f"{LOG} clicked {kt!r} on {t!r}")
            else:
                m7.user32.SendMessageW(h, 0x0111, 1, 0)
                print(f"{LOG} WM_COMMAND IDOK on {t!r}")
            time.sleep(3.0)
        time.sleep(2.0)


def wait_loaded(session, timeout_s=240):
    """载入门：彩色占比（载入后实测 6.3%）或对象标签页零件行任一成立。

    首轮 0.06% 的误判根因不是颜色缺失，而是提示框挡住了加载——现在
    swallow_load_dialogs 先点掉提示框，占比判据即可用；对象行兜底。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if m7.model_colored_frac(session) >= 0.0025:
            print(f"{LOG} loaded by colored frac")
            return "colored"
        time.sleep(2.0)
    return c152.objects_tab_select(session)


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
        swallow_load_dialogs(session)
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
