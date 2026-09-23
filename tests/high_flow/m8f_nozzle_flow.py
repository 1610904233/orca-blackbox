#!/usr/bin/env python3
# m8f_nozzle_flow.py — 飞书基线用例 #133/#135/#136 (高流量热端, P0)。
# feishu: baseline#133 baseline#135 baseline#136
#
# 判定口径来自飞书文档「gcode测试方案」
# (wiki RZQuwbdFzi3E2YkES5acOcB3nIf, 2026-09-23 拉取):
#   * 三个手造工艺/耗材包（resources/user/default，播种到 <datadir>/user/
#     default）:
#       标准测试    = [标准, 高流量] 两档值，如 inner_wall_speed ['550','600']
#       高流量测试  = ['300','550'] —— 构造上满足 (标准测试+标准流量) 与
#                     (高流量测试+高流量) 取到的值完全相等
#       流量测试    = 两档值相同（单变量对比用）
#   * 对比工具用官方 compare_gcode.py（本仓 tools/ 已 vendored）：只比 gcode
#     里 CONFIG_BLOCK 的最终配置，分「高流量模式字段变化」与「数值配置变化」
#     两类；rc=0 表示无差异。
#   * 文档注意事项：必须单耗材、必须简单正方体——多耗材/多岛/带孔/旋转对称
#     的模型会因岛序互换与起笔漂移造成 gcode 不一致（与产品无关）。
#     夹具 = fixtures/gcode_flow_{std,hf,single}.3mf（官方立方体工程，
#     只替换了内嵌的包名）。
#
#   #133 默认值: diameter 读回 '0.4mm' + flow 'Standard'
#   #135 标准/高流量全量模拟: (标准测试包+标准流量) vs (高流量测试包+
#        高流量) 两份 gcode 的最终配置应【完全一致】(官方脚本 rc=0)
#   #136 单一变量（流量测试包，两档值相同）: 标准 vs 高流量切片，
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

from harness.anchors import capture_bgr  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8f]"
ART = HERE / "artifacts"
FIXTURES = HERE / "fixtures"
FLOW_STD = FIXTURES / "gcode_flow_std.3mf"
FLOW_HF = FIXTURES / "gcode_flow_hf.3mf"
FLOW_SINGLE = FIXTURES / "gcode_flow_single.3mf"
COMPARE = HERE / "tools" / "compare_gcode.py"


def compare_gcodes(a: Path, b: Path):
    """官方 compare_gcode.py 的 rc + 报告（rc=0 无差异, 1 有差异, 2 解析失败）。"""
    r = subprocess.run([sys.executable, str(COMPARE), str(a), str(b)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    report = (r.stdout or "") + (r.stderr or "")
    print(f"{LOG} compare rc={r.returncode}")
    for line in report.splitlines()[:12]:
        print(f"{LOG}   {line}")
    return r.returncode, report


def counts(report: str):
    """(mode_diff, numeric_diff) from the official report wording."""
    def grab(pat):
        m = re.search(pat, report)
        return int(m.group(1)) if m else -1
    return (grab(r"高流量模式字段变化：(\d+) 项"),
            grab(r"数值配置变化：(\d+) 项"))


def export_slice(session, results, key, name, timeout_s=900):
    out = ART / name
    out.unlink(missing_ok=True)
    return m7.op_slice(session, results, key=key, export_to=out,
                       timeout_s=timeout_s) and out.exists(), out


def sweep_dialogs(session, tag):
    """High-flow switching can raise a nozzle-assignment / confirmation
    #32770 (doc screenshot) — confirm the first button when one appears."""
    dlg = m7.wait_dialog(session.pid, timeout_s=3.0)
    if dlg:
        print(f"{LOG} [{tag}] dialog: {dlg[1]!r} — confirming")
        m7.click_dialog_button(dlg[3], "ok")
        time.sleep(1.0)
        dlg2 = m7.wait_dialog(session.pid, timeout_s=2.0)
        if dlg2:
            m7.click_dialog_button(dlg2[3], "ok")


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
    ap = add_common_args(argparse.ArgumentParser(), default_model=FLOW_STD)
    args = ap.parse_args()
    results = {}

    # ---- session A: 标准测试 + 标准流量 -> gcode A ----------------------
    session, ok = boot(args, FLOW_STD, "A_std")
    try:
        results["U1 0.4 project loads"] = "PASS" if ok else "FAIL"
        reads = m8.nozzle_reads(session)
        print(f"{LOG} nozzle reads: {reads}")
        results["#133 diameter default 0.4mm"] = (
            "PASS" if reads["diameter"] == "0.4mm"
            else f"FAIL ({reads['diameter']!r})")
        results["#133 flow default Standard"] = (
            "PASS" if reads["flow"] == "Standard"
            else f"FAIL ({reads['flow']!r})")
        back = m8.switch_flow_combo(session, "Standard")
        print(f"{LOG} flow ensure Standard -> {back!r}")
        sweep_dialogs(session, "A_std")
        ok_a, g_a = export_slice(session, results, "#135 A: std package+std flow",
                                 "m8f_flow_stdA.gcode")
    finally:
        session.close()
        print(f"{LOG} session A closed")
        time.sleep(3.0)
    if not ok_a:
        return m7.m7_verdict(results)

    # ---- session B: 高流量测试 + 高流量 -> gcode B ----------------------
    session, ok = boot(args, FLOW_HF, "B_hf")
    try:
        flow = m8.switch_flow_combo(session, "High Flow")
        print(f"{LOG} flow -> {flow!r}")
        results["#135 flow switches to High Flow"] = (
            "PASS" if "High Flow" in flow else f"FAIL ({flow!r})")
        sweep_dialogs(session, "B_hf")
        ok_b, g_b = export_slice(session, results, "#135 B: hf package+hf flow",
                                 "m8f_flow_hfB.gcode")
    finally:
        session.close()
        print(f"{LOG} session B closed")
        time.sleep(3.0)
    if not ok_b:
        return m7.m7_verdict(results)

    rc, report = compare_gcodes(g_a, g_b)
    mode_diff, num_diff = counts(report)
    results["#135 std-vs-hf configs identical"] = (
        "PASS" if rc == 0
        else f"FAIL (rc={rc}, mode={mode_diff}, numeric={num_diff})")

    # ---- session C: 流量测试包（两档值相同）标准 vs 高流量 ---------------
    session, ok = boot(args, FLOW_SINGLE, "C_single")
    ok_c = ok_d = False
    g_c = g_d = None
    try:
        back = m8.switch_flow_combo(session, "Standard")
        print(f"{LOG} flow -> {back!r}")
        sweep_dialogs(session, "C_std")
        ok_c, g_c = export_slice(session, results, "#136 std slice (single-var)",
                                 "m8f_single_stdC.gcode")
        if ok_c:
            flow2 = m8.switch_flow_combo(session, "High Flow")
            print(f"{LOG} flow -> {flow2!r}")
            sweep_dialogs(session, "C_hf")
            ok_d, g_d = export_slice(
                session, results, "#136 hf slice (single-var)",
                "m8f_single_hfD.gcode")
    finally:
        session.close()
        print(f"{LOG} session C closed")
    if ok_c and ok_d:
        rc2, report2 = compare_gcodes(g_c, g_d)
        mode2, num2 = counts(report2)
        results["#136 single-variable: numeric diffs 0"] = (
            "PASS" if num2 == 0 and mode2 >= 0
            else f"FAIL (numeric={num2}, mode={mode2})")

    results["app alive"] = "PASS" if session.alive() else "FAIL"
    return m7.m7_verdict(results)


if __name__ == "__main__":
    raise SystemExit(main())
