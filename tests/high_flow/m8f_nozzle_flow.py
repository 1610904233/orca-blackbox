#!/usr/bin/env python3
# m8f_nozzle_flow.py — 飞书基线用例 #133/#135/#136 (高流量热端, P0)。
# feishu: baseline#133 baseline#135 baseline#136
#
# 判定口径与操作流程来自飞书文档「gcode测试方案」
# (wiki RZQuwbdFzi3E2YkES5acOcB3nIf，2026-09-23 拉取 + 与测试者确认):
#   * 三个手造包（resources/user/default，播种到 <datadir>/user/default；
#     仓库副本改为 ASCII 名以便 UI 里可靠识别）:
#       STD-TEST  工艺/耗材包 = [标准, 高流量] 两档值，如 inner_wall_speed
#                               ['550','600']
#       HF-TEST   同键 = ['300','550'] —— 构造上 (STD-TEST+标准流量) 与
#                 (HF-TEST+高流量) 取到的值完全相等
#       FLOW-TEST 两档值相同（单变量对比用）
#   * 包必须在 UI 里选中（工艺预设下拉 + 耗材预设下拉 + Nozzle Flow 下拉）—
#     这才验证到"两档值按序号取用"；夹具只负责加载同一个立方体工程。
#   * 对比用官方 compare_gcode.py（本仓 tools/ vendored）：只比 gcode 的
#     CONFIG_BLOCK 最终配置，分「高流量模式字段变化」「数值配置变化」两类，
#     rc=0 表示完全一致。
#   * 文档注意事项：单耗材 + 简单正方体（多耗材/多岛/带孔/旋转对称模型会因
#     岛序互换与起笔漂移产生与产品无关的 gcode 差异）。
#
#   #133 喷嘴界面默认值: diameter '0.4mm' + flow 'Standard'
#   #135 标准/高流量全量模拟: (STD-TEST+标准流量) vs (HF-TEST+高流量)
#        两份 gcode 的最终配置应完全一致（官方脚本 rc=0）
#   #136 单一变量(FLOW-TEST, 两档值相同): 标准 vs 高流量切片，
#        数值配置差异应为 0（只允许高流量模式字段不同）
#   (#134 喷嘴信息同步 = 设备链, MANUAL)

import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import argparse  # noqa: E402

from harness import process_panel as pp  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8f]"
ART = HERE / "artifacts"
FIXTURES = HERE / "fixtures"
GCODE_FLOW_STD = FIXTURES / "gcode_flow_std.3mf"
GCODE_FLOW_HF = FIXTURES / "gcode_flow_hf.3mf"
GCODE_FLOW_SINGLE = FIXTURES / "gcode_flow_single.3mf"
COMPARE = HERE / "tools" / "compare_gcode.py"

PROC_STD = "0.20mm Standard @Snapmaker U1 (0.4 nozzle) - STD-TEST"
PROC_HF = "0.20mm Standard @Snapmaker U1 (0.4 nozzle) - HF-TEST"
PROC_FLOW = "0.24mm Standard @Snapmaker U1 (0.4 nozzle) - FLOW-TEST"
FIL_STD = "Snapmaker PLA SnapSpeed @U1 - STD-TEST"
FIL_HF = "Snapmaker PLA SnapSpeed @U1 - HF-TEST"
FIL_FLOW = "Snapmaker PLA SnapSpeed @U1 - FLOW-TEST"


# --- official comparison ------------------------------------------------------

def compare_gcodes(a: Path, b: Path):
    """官方 compare_gcode.py：rc 0=无差异, 1=有差异, 2=解析失败。"""
    r = subprocess.run([sys.executable, str(COMPARE), str(a), str(b)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    report = (r.stdout or "") + (r.stderr or "")
    print(f"{LOG} compare rc={r.returncode}")
    for line in report.splitlines()[:14]:
        print(f"{LOG}   {line}")
    return r.returncode, report


def report_counts(report: str):
    def grab(pat):
        m = re.search(pat, report)
        return int(m.group(1)) if m else -1
    return (grab(r"高流量模式字段变化：(\d+) 项"),
            grab(r"数值配置变化：(\d+) 项"))


# --- session helpers ----------------------------------------------------------

def sweep_dialogs(session, tag):
    """Flow/package switches can raise a #32770 (customized preset / nozzle
    assignment) — confirm the first button whenever one appears."""
    for _ in range(2):
        dlg = m7.wait_dialog(session.pid, timeout_s=2.5)
        if not dlg:
            return
        print(f"{LOG} [{tag}] dialog {dlg[1]!r} — confirming")
        m7.click_dialog_button(dlg[3], "ok")
        time.sleep(1.0)


def select_packages(session, proc_name, fil_name, tag):
    """Select the process + filament package in the UI (the step that proves
    the two-index values are read)."""
    ok_p = pp.switch_process_preset(session, proc_name)
    print(f"{LOG} [{tag}] process preset -> {proc_name[-9:]!r}: {ok_p}")
    sweep_dialogs(session, tag + "_proc")
    slots = m8.filament_slots(session)
    slot = slots[0]["slot"] if slots else 1
    fin = m8.switch_filament_preset(session, slot=slot,
                                    target_substr=fil_name.split(" - ")[-1])
    print(f"{LOG} [{tag}] filament preset (slot {slot}) -> {fin!r}")
    sweep_dialogs(session, tag + "_fil")
    return ok_p, fin


def set_flow(session, target, tag, tries=3):
    """Switch the Nozzle Flow combo and VERIFY it took (the switch can be
    swallowed: measured 09-23 the combo read back 'Standard' right after a
    High-Flow switch)."""
    for i in range(tries):
        got = m8.switch_flow_combo(session, target)
        print(f"{LOG} [{tag}] flow try{i + 1} -> {got!r}")
        if target in (got or ""):
            return got
        sweep_dialogs(session, tag + "_flow")
        time.sleep(1.5)
    # diagnostics for the failure path: what the sidebar reports, which
    # dialogs are up, and the flow popup's rows when it opens
    print(f"{LOG} [{tag}] flow switch FAILED: reads="
          f"{m8.nozzle_reads(session)!r}")
    dlg = m7.wait_dialog(session.pid, timeout_s=1.0)
    print(f"{LOG} [{tag}] open dialog: {dlg}")
    try:
        m8.switch_flow_combo(session, "High Flow", tries=1)
    except Exception as exc:  # noqa: BLE001
        print(f"{LOG} [{tag}] popup probe error: {exc}")
    return m8.nozzle_reads(session).get("flow") or ""


def slice_export(session, results, key, name):
    out = ART / name
    out.unlink(missing_ok=True)
    ok = m7.op_slice(session, results, key=key, export_to=out)
    if not (ok and out.exists()):
        # the export once failed right after a successful slice (measured
        # 09-23: stdA) — one retry of the export path is cheap
        print(f"{LOG} {key}: export missing — retrying the export")
        from harness import export_util
        time.sleep(2.0)
        ok = export_util.export_gcode(session, out, timeout_s=60.0) or ok
    return bool(ok and out.exists()), out


def boot(args, model, tag):
    args.model = model
    session = boot_session(args, model=model)
    ok, frac = m8.wait_arrival(session)
    m7.ensure_maximized(session)
    ensure_gl_ready(session)
    time.sleep(1.0)
    print(f"{LOG} [{tag}] arrival {ok} ({frac:.2%})")
    return session, ok


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=GCODE_FLOW_STD)
    args = ap.parse_args()
    results = {}

    # ---- A: STD-TEST packages + standard flow -----------------------------
    ok_a = False
    session, ok = boot(args, GCODE_FLOW_STD, "A_std")
    try:
        results["U1 0.4 project loads"] = "PASS" if ok else "FAIL"
        reads = m8.nozzle_reads(session)
        print(f"{LOG} [A] nozzle reads: {reads}")
        results["#133 diameter default 0.4mm"] = (
            "PASS" if reads["diameter"] == "0.4mm"
            else f"FAIL ({reads['diameter']!r})")
        results["#133 flow default Standard"] = (
            "PASS" if reads["flow"] == "Standard"
            else f"FAIL ({reads['flow']!r})")
        # 操作顺序（测试者 2026-09-23 确认）：先切流量，再选包 —— 否则
        # 某些包/工程状态下 Flow 下拉只提供 Standard（会话 B 实测）
        set_flow(session, "Standard", "A")
        select_packages(session, PROC_STD, FIL_STD, "A")
        set_flow(session, "Standard", "A2")
        ok_a, g_a = slice_export(session, results,
                                 "#135 A: std packages+std flow",
                                 "m8f_stdA.gcode")
    finally:
        session.close()
        print(f"{LOG} session A closed")
        time.sleep(3.0)
    if not ok_a:
        return m7.m7_verdict(results)

    # ---- B: HF-TEST packages + high flow ---------------------------------
    ok_b = False
    session, ok = boot(args, GCODE_FLOW_HF, "B_hf")
    try:
        set_flow(session, "High Flow", "B")
        select_packages(session, PROC_HF, FIL_HF, "B")
        flow = set_flow(session, "High Flow", "B2")
        results["#135 flow switches to High Flow"] = (
            "PASS" if "High Flow" in (flow or "") else f"FAIL ({flow!r})")
        ok_b, g_b = slice_export(session, results,
                                 "#135 B: hf packages+hf flow",
                                 "m8f_hfB.gcode")
    finally:
        session.close()
        print(f"{LOG} session B closed")
        time.sleep(3.0)
    if not ok_b:
        return m7.m7_verdict(results)

    rc, report = compare_gcodes(g_a, g_b)
    mode_diff, num_diff = report_counts(report)
    results["#135 std-vs-hf configs identical"] = (
        "PASS" if rc == 0
        else f"FAIL (rc={rc}, mode={mode_diff}, numeric={num_diff})")

    # ---- C: FLOW-TEST packages, standard vs high (single variable) --------
    session, ok = boot(args, GCODE_FLOW_SINGLE, "C_single")
    ok_c = ok_d = False
    g_c = g_d = None
    try:
        set_flow(session, "Standard", "C")
        select_packages(session, PROC_FLOW, FIL_FLOW, "C")
        set_flow(session, "Standard", "C2")
        ok_c, g_c = slice_export(session, results,
                                 "#136 std slice (single-var)",
                                 "m8f_singleC.gcode")
        if ok_c:
            flow2 = set_flow(session, "High Flow", "C2")
            print(f"{LOG} [C] flow -> {flow2!r}")
            ok_d, g_d = slice_export(session, results,
                                     "#136 hf slice (single-var)",
                                     "m8f_singleD.gcode")
    finally:
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        session.close()
        print(f"{LOG} session C closed")

    if ok_c and ok_d:
        rc2, report2 = compare_gcodes(g_c, g_d)
        mode2, num2 = report_counts(report2)
        results["#136 single-variable: numeric diffs 0"] = (
            "PASS" if num2 == 0 and mode2 >= 0
            else f"FAIL (numeric={num2}, mode={mode2})")
    return m7.m7_verdict(results)


if __name__ == "__main__":
    raise SystemExit(main())
