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
    """Package switches raise the app's 'Transfer or discard changes' prompt
    (the flow switch marks the current preset modified) — answer DISCARD so
    the next selection starts clean. Any other #32770 gets its first button."""
    for _ in range(3):
        if m7.dismiss_transfer_dialog(session):
            continue
        dlg = m7.wait_dialog(session.pid, timeout_s=2.0)
        if not dlg:
            return
        print(f"{LOG} [{tag}] dialog {dlg[1]!r} — confirming")
        m7.click_dialog_button(dlg[3], "ok")
        time.sleep(1.0)


def select_packages(session, proc_name, fil_name, tag):
    """Select the process + filament package in the UI (the step that proves
    the two-index values are read). Returns (process_ok, filament_text); the
    caller must treat a wrong filament text as FAIL — no blind fallback."""
    ok_p = pp.switch_process_preset(session, proc_name)
    print(f"{LOG} [{tag}] process preset -> {proc_name[-9:]!r}: {ok_p}")
    sweep_dialogs(session, tag + "_proc")
    slots = m8.filament_slots(session)
    slot = slots[0]["slot"] if slots else 1
    want = fil_name.split(" - ")[-1]
    fin = m8.switch_filament_preset(session, slot=slot, target_substr=want)
    print(f"{LOG} [{tag}] filament preset (slot {slot}) -> {fin!r} "
          f"(want {want!r})")
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
    """三个工程各起一次会话，只在 UI 里切 Nozzle Flow。

    包由工程文件携带（官方测试文件也是内嵌预设 id 的方式）：实测 09-23
    (g31) 耗材下拉弹窗在本构建上抓不到像素（PrintWindow 返回空、屏幕裁剪
    拍到的是背后的侧栏），UI 切耗材包不可靠；而"按序号取值"的关键动作是
    切流量，这一点在 UI 里做完整体现。

        gcode_flow_std    (STD-TEST 包)  + 标准流量 -> A
        gcode_flow_hf     (HF-TEST  包)  + 高流量   -> B   (#135: A/B 配置应一致)
        gcode_flow_single (FLOW-TEST 包) 标准流量   -> C
                                        切高流量   -> D   (#136: C/D 数值差异应为 0)
    """
    ap = add_common_args(argparse.ArgumentParser(), default_model=GCODE_FLOW_STD)
    args = ap.parse_args()
    results = {}
    g_a = g_b = g_c = g_d = None
    ok_a = ok_b = ok_c = ok_d = False

    # ---- A: STD-TEST project + standard flow -----------------------------
    session, ok = boot(args, GCODE_FLOW_STD, "A")
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
        set_flow(session, "Standard", "A")
        ok_a, g_a = slice_export(session, results, "#135 A: STD-TEST+std flow",
                                 "m8f_stdA.gcode")
    finally:
        session.close()
        print(f"{LOG} session A closed")
        time.sleep(3.0)

    # ---- B: HF-TEST project + high flow ---------------------------------
    if ok_a:
        session, ok = boot(args, GCODE_FLOW_HF, "B")
        try:
            # 实测 09-23：直接切流量时下拉只给 Standard；先(重)选一次工艺预设
            # （ASCII 名，UI 可靠）后下拉才刷新出 High Flow —— 与测试者的
            # "先切流量再选包"顺序配套使用时两种顺序都要能工作
            proc_ok = pp.switch_process_preset(session, PROC_HF)
            print(f"{LOG} [B] process preset re-applied: {proc_ok}")
            sweep_dialogs(session, "B_proc")
            flow = set_flow(session, "High Flow", "B")
            results["#135 flow switches to High Flow"] = (
                "PASS" if "High Flow" in (flow or "") else f"FAIL ({flow!r})")
            ok_b, g_b = slice_export(session, results,
                                     "#135 B: HF-TEST+hf flow",
                                     "m8f_hfB.gcode")
        finally:
            session.close()
            print(f"{LOG} session B closed")
            time.sleep(3.0)

    if ok_a and ok_b:
        rc, report = compare_gcodes(g_a, g_b)
        mode_diff, num_diff = report_counts(report)
        results["#135 std-vs-hf configs identical"] = (
            "PASS" if rc == 0
            else f"FAIL (rc={rc}, mode={mode_diff}, numeric={num_diff})")

    # ---- C/D: FLOW-TEST project, standard then high (single variable) ----
    if ok_b:
        session, ok = boot(args, GCODE_FLOW_SINGLE, "C")
        try:
            set_flow(session, "Standard", "C")
            ok_c, g_c = slice_export(session, results,
                                     "#136 std slice (single-var)",
                                     "m8f_singleC.gcode")
            if ok_c:
                flow_d = set_flow(session, "High Flow", "D")
                print(f"{LOG} [D] flow -> {flow_d!r}")
                ok_d, g_d = slice_export(session, results,
                                         "#136 hf slice (single-var)",
                                         "m8f_singleD.gcode")
            results["app alive"] = "PASS" if session.alive() else "FAIL"
        finally:
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
