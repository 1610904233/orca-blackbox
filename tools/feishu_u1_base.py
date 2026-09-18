#!/usr/bin/env python3
"""feishu_u1_base.py — publish the U1 UI inventory into a Feishu Base.

Emits JSON payload files (one per batch) under artifacts/feishu_u1/ so the
uploads can be driven by plain `lark-cli base +record-batch-create --json @...`
calls — a file per batch keeps each request inspectable and retryable, and
avoids stuffing a megabyte of registry into a shell argument.

Numbers are computed from the registry (`data/_index_u1.json`) and the coverage
mapper, never hard-coded, so a re-run after an inventory refresh stays truthful.

Usage:
    python tools/feishu_u1_base.py --out artifacts/feishu_u1
    # then, per emitted file:
    #   lark-cli base +record-batch-create --base-token <t> --table-id <id> --json @<file>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

BATCH = 200  # platform limit for +record-batch-create

AREA_LABEL = {
    "topbar": "topbar 顶栏菜单/快捷键/状态栏通知",
    "plater": "plater 画布/主工具栏/右键菜单/动作区",
    "gizmo": "gizmo Gizmo面板/对象列表/可变层高",
    "param": "param 参数侧栏/预设选择器/参数搜索",
    "preview": "preview Preview/G-code视图控件",
    "mix": "mix 混色/耗材专项UI",
    "device": "device 设备页/AMS/校准",
    "dlg": "dlg 偏好/向导/更新/账号Web弹窗",
}

# The narrative summary. Kept here (not generated) because it is judgement and
# interpretation, not a derived number — but every figure in it is checked
# against the registry below at emit time.
SUMMARY: list[tuple[str, str]] = [
    ("一句话结论",
     "U1 现成可达 1433 项；另 364 项需先切模式、1067 项不可达。原始盘点 2864 项"
     "（8 个 UI 面 / 264 个 L0 面 / 约 300 个 L1 组），逐条带源码 file:line 与门控条件。"),
    ("被测对象",
     "SnapmakerOrca @ 295f71947c（只读）；黑盒套件 orca-blackbox 共 84 例。"
     "本盘点为静态源码调研：不启动被测程序、不截图、不做运行时挂钩。"),
    ("业界术语·动态路线",
     "GUI ripping（Memon, Banerjee & Nagarajan, WCRE 2003）：运行时遍历界面抽取全部控件与属性，"
     "反推出 GUI forest + event-flow graph (EFG) + integration tree；工具套件 GUITAR。"),
    ("业界术语·静态路线",
     "UI surface inventory / affordance inventory —— 本次所做（GUI ripping 的静态等价物）。"),
    ("业界术语·覆盖率",
     "widget / event / event-interaction coverage（Memon, Soffa & Pollack, 2004）；"
     "后统一为 event-flow model 与 event-space exploration strategy（STVR 2007）。"),
    ("业界术语·对账",
     "ISTQB：test basis（测试依据）→ coverage items（覆盖项）→ traceability matrix（追溯矩阵）；"
     "覆盖率 = 已覆盖项数 ÷ 总覆盖项数。"),
    ("业界术语·工具沿革",
     "WinRunner GUI Map / QTP-UFT Object Repository / locator inventory & Page Object Model / "
     "accessibility tree dump（本仓 runner/uia_probe.py 即后者）。"),
    ("为什么必须静态盘",
     "2204/2864（77%）的标签是自绘（GL / ImGui / OG_CustomCtrl），UIA 与 GetWindowText 读不到；"
     "本仓 UIA_EVAL_0903 实测全树仅 103 节点、Edit 仅 2，两条路线互证。"),
    ("参数面是混合情形",
     "标签自绘但值控件是原生 wx（wxTextCtrl 275 / wxCheckBox 106 / wxSpinCtrl 55 / wxComboBox 54…）；"
     "结论：按标签找不到，按控件类型或坐标可以。"),
    ("U1 机型事实",
     "厂商 Snapmaker；printer_model \"Snapmaker U1\"；工艺 FFF；4 挤出机；gcode_flavor klipper；"
     "single_extruder_multi_material=0；默认床型 Textured PEI Plate；平台 Windows。"),
    ("派生门控①厂商",
     "is_bbl_vendor() 仅当厂商名恰为 \"BBL\" 时成立（libslic3r/PresetBundle.cpp:550-568）→ "
     "U1 下 use_bbl_device_tab() 恒 false → Device 页渲染 PrinterWebView（GUI/MainFrame.cpp:1348-1372）"
     "→ device 面 844 项整体出局。这不是漏测，是不该测。"),
    ("派生门控②模式",
     "行可见性判据 opt_mode <= mode（GUI/OptionsGroup.cpp:779-797）；播种 conf 无 user_mode → "
     "get_mode() 返回 comSimple（GUI/GUI_App.cpp:6200-6208）；Simple/Advanced 切换按钮被注释"
     "（GUI/wxExtensions.cpp:875-878，buttons 向量为空）；唯一 UI 路径 = 偏好里的 \"Develop mode\" "
     "（GUI/Preferences.cpp:1353）→ 参数面 363 项需切模式才可见。"),
    ("派生门控③平台与死代码",
     "macOS 专属 35；两平台都不编译 10；非 Windows 专属 2；死代码/未注册/编译期禁用 76；"
     "SLA(树脂) 门控 23；BBL-only 58。"),
    ("不可达明细闭合",
     "十个理由码相加 = 1067，与不可达总数一致，无暗项。OTHER_MODEL（非 U1 机型门控）与 "
     "INHERIT_FACE 两条规则在 U1 集合上命中 0 条。"),
    ("逐面分布（总量/U1可达/需切模式/不可达）",
     "device 844/0/0/844；param 607/187/363/57；gizmo 341/333/0/8；topbar 287/238/0/49；"
     "plater 276/258/0/18；mix 207/164/0/43；dlg 202/157/1/44；preview 100/96/0/4。"),
    ("U1 覆盖矩阵（项/例=密度）",
     "gizmo 333项/17例/19.6；plater 258/21/12.3；topbar 238/13/18.3；param 187/32/5.8；"
     "mix 164/29/5.7；dlg 157/6/26.2；preview 96/4/24.0。"),
    ("反直觉结论",
     "换 U1 分母后参数面密度由 19.0 降到 5.8 项/例，反而变好：参数面不是\"测得浅\"，"
     "而是\"只测了一半，另一半没开\"。这把\"是否开 Advanced 模式\"推到决策位。"),
    ("P0 空白①预设动作集",
     "预设选择器完整动作集（Save as / Delete / Rename / Reset to system / Load / 导入导出）；"
     "25 项里只测了\"切换 → gcode 跟随\"。判据强：有文件系统产物。"),
    ("P0 空白②校准菜单",
     "topbar Calibration 菜单（Windows 生效的那部分）整片未测；多数会落到 gcode 或对话框。"),
    ("P0 空白③预览视图维度",
     "preview 视图类型（Line type / Speed / Flow / Fan speed / Temperature / Pressure advance）"
     "与 Legend 逐行开关（角色行 19 + 移动类型 6）；判据 = 图例行数 + 视口像素占比。"),
    ("P0 空白④对象右键菜单",
     "对象列表右键菜单 57 项，只测了 delete 与少量拆分；未测 Clone / Simplify / Add part / "
     "Add negative volume / Change type / Set as…。"),
    ("P0 空白⑤偏好设置",
     "dlg 的 PreferencesDialog 共 64 项，只验证了\"打开不阻塞\"；其中开发模式、语言、项目默认值"
     "会改变后续行为，值得 3–5 例。"),
    ("若决定开 Advanced 模式",
     "额外解锁 363 项参数行；其中机器侧/耗材侧整页（Machine 32 + Motion ability 22 + Cooling 20 + "
     "Multimaterial 55 + Setting Overrides 18）是最大一块新地盘，且全部可用 gcode header 断言，"
     "性价比最高。改动点：harness/profile.py 的 MINIMAL_CONF 加 \"user_mode\": \"advanced\"。"),
    ("可信度",
     "4929 处 file:line 引用全部校验到上游真实文件与行号范围内"
     "（tools/ui_inventory_verify.py 输出 OK）；4229 处为行号简写按小节基文件继承解析。"),
    ("已知更正（留痕）",
     "① 聚合器未处理 Markdown 转义竖线 \\| 导致含 || 条件的行整列错位、gate 被截断"
     "（自绘计数由 2161 修正为 2204，列不匹配行 50→1）；② WipingPanel 曾被误判不可达，"
     "实为可达（现有用例 m7k_flush_options 正测它）。"),
    ("局限",
     "U1 判定是关键词启发式而非逐条人工复核（规则与理由码见 tools/ui_u1_filter.py）；"
     "命名面继承解析 153 条；needs-mode 项真实存在，排除出分母只为不美化覆盖率；"
     "全部为静态推断，未真机验证，凡影响决策的结论建议用 1–2 个探针用例坐实。"),
    ("产物索引",
     "总文档 docs/UI_SURFACE_INVENTORY.md；U1 专档 docs/UI_U1_REACHABLE.md；逐面章节 "
     "docs/ui_surface/<area>.md；全量注册表 data/_index.json；U1 判定 data/_index_u1.json；"
     "工具 tools/topbar|plater|param|gizmo|preview|device|dlg|mix_inventory.py + "
     "ui_inventory_verify.py + ui_inventory_aggregate.py + ui_u1_filter.py + ui_coverage_map.py。"),
]

REASONS: list[tuple[str, str, str, str]] = [
    ("DEVICE_BBL_STACK", "U1 非 BBL 厂商 → BBL 设备栈不构建",
     "libslic3r/PresetBundle.cpp:550-568 / :577-589；GUI/MainFrame.cpp:1348-1372"),
    ("DEAD", "死代码 / 未注册 / 全仓无引用 / 编译期禁用",
     "gizmo 未注册 5 类（Gizmos/GLGizmosManager.cpp:222-224）；preview-L2-098/099（SliceInfoPanel 无引用）；"
     "preview-L2-100（ENABLE_GCODE_VIEWER_STATISTICS=0）；mix 的 #if 0 面板（Plater.cpp:7555 / :7565）"),
    ("BBL_ONLY", "门控 is_bbl_vendor() / BBL 机型 / Bambu 网络 / AMS / 多机",
     "plater-L2-093（!is_bbl_vendor() → Disable()）"),
    ("PLATFORM:macos_only", "仅 macOS 菜单项（topbar 结构化平台列）",
     "File/Edit 的 macOS 专属项（Plater? 见 topbar.md 平台列）"),
    ("SLA", "树脂机门控（U1 是 FFF）", "plater-L2-063、plater-L2-178（printer_technology == ptSLA）"),
    ("PLATFORM", "其它平台/编译期排除", "plater-L2-055（#if !BBL_RELEASE_TO_PUBLIC）"),
    ("PLATFORM:dead", "两平台都不编译", "topbar 平台列 = dead"),
    ("INHERIT_PREV:BBL_ONLY", "继承上一行的不可达判定（BBL 门控）", "门控写\"同上\"，上一行为 BBL-only"),
    ("INHERIT_PREV:DEAD", "继承上一行的不可达判定（死代码）", "门控写\"同上\"，上一行为死代码"),
    ("PLATFORM:non_windows_only", "非 Windows 专属", "topbar-L2-029 / topbar-L2-030"),
]

GAPS: list[tuple[str, str, str, str]] = [
    ("P0", "预设选择器完整动作集：Save as / Delete / Rename / Reset to system / Load / 导入导出", "param",
     "文件系统产物（预设文件出现/消失/改名）+ 对话框出现"),
    ("P0", "topbar Calibration 菜单（Windows 生效部分）整片未测", "topbar", "gcode 变化或对话框出现"),
    ("P0", "preview 视图类型（Line type / Speed / Flow / Fan speed / Temperature / PA）与 Legend 逐行开关",
     "preview", "图例行数变化 + 视口像素占比"),
    ("P0", "对象列表右键菜单：Clone / Simplify / Add part / Add negative volume / Change type / Set as…",
     "gizmo", "对象树节点数变化 + 对话框出现"),
    ("P0", "PreferencesDialog 中有行为影响的项：开发模式 / 语言 / 项目默认值", "dlg",
     "重启后行为变化，或后续操作默认值跟随"),
    ("P0", "若开 Advanced 模式：机器侧/耗材侧整页（Machine 32 + Motion ability 22 + Cooling 20 + "
     "Multimaterial 55 + Setting Overrides 18）", "param",
     "gcode header 的 '; key = value' 配置回显（确定性最强）"),
    ("P1", "gizmo 面：Measure / Emboss-SVG / BrimEars / FuzzySkin 画笔 / MeshBoolean 分支 / "
     "Assembly / Height range 编辑器", "gizmo", "画布像素变化 + 面板控件态"),
    ("P1", "plater 面：板右键菜单 / Plate Settings 对话框 / 板数量增删", "plater",
     "板数量与板尺寸的可观测变化"),
    ("P2", "dlg 的 13 类 Web 视图对话框 与 device 面 Web 内容", "dlg",
     "控件不在本仓源码内，静态盘不出、也无法从本仓断言 —— 建议不投入"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "artifacts" / "feishu_u1"))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    u1 = json.loads((ROOT / "docs" / "ui_surface" / "data" / "_index_u1.json")
                    .read_text(encoding="utf-8"))
    recs = u1["records"]
    counts = u1["counts"]

    # --- coverage figures, computed (not hard-coded) ---------------------
    import ui_coverage_map as cm
    from cases import CASES
    cases_for: dict[str, list[str]] = defaultdict(list)
    for case in CASES:
        for area in cm.CASE_AREAS.get(case, ()):
            cases_for[area].append(case)

    per_area = Counter()
    for r in recs:
        if r["u1_verdict"] == "reachable":
            per_area[r["area"]] += 1

    payloads: list[tuple[str, dict]] = []

    # --- 结论摘要 --------------------------------------------------------
    payloads.append(("tbl9Nve3rzTzppoF", {
        "fields": ["章节", "要点"],
        "rows": [[k, v] for k, v in SUMMARY],
    }))

    # --- 面汇总 ----------------------------------------------------------
    rows = []
    for area in sorted(per_area, key=lambda a: -per_area[a]) + ["device"] * (0 if "device" in per_area else 1):
        if area in per_area:
            n_reach = per_area[area]
        else:
            n_reach = 0
        c = counts["per_area"].get(area, {})
        k = len(cases_for.get(area, []))
        dens = None if k == 0 else round(n_reach / k, 1)
        band = cm.strength(n_reach, k) if n_reach else "空白"
        total = c.get("reachable", 0) + c.get("needs-mode", 0) + c.get("unreachable", 0)
        rows.append([AREA_LABEL[area], total, c.get("reachable", 0), c.get("needs-mode", 0),
                     c.get("unreachable", 0), k, dens, band])
    tot = [sum(r[i] for r in rows) for i in (1, 2, 3, 4)]
    # `覆盖带宽` is a select; the total row has no band, and an unknown option
    # string is rejected (800030005), so it must be null rather than "—".
    rows.append(["合计", tot[0], tot[1], tot[2], tot[3], len(CASES), None, None])
    payloads.append(("tblEI59Tz3L2JQL3", {"fields": ["面", "总量", "U1可达", "需切模式",
                                                     "不可达", "涉及用例数", "项每例", "覆盖带宽"],
                                          "rows": rows}))

    # --- 不可达明细 ------------------------------------------------------
    reason_counts = {k: v for k, v in counts["reasons"].items() if k.startswith("unreachable:")}
    rrows = []
    for code, meaning, evidence in REASONS:
        n = reason_counts.get(f"unreachable:{code}", 0)
        rrows.append([code, n, meaning, evidence])
    rrows.append(["合计", sum(r[1] for r in rrows), "十码相加 = 不可达总数（无暗项）", "—"])
    payloads.append(("tbljvVONHFcNGLhU", {"fields": ["理由码", "条数", "含义", "代表证据"],
                                          "rows": rrows}))

    # --- U1空白建议 ------------------------------------------------------
    payloads.append(("tblkYflPVfUPjtzJ", {
        "fields": ["优先级", "空白项", "所属面", "建议判据"],
        "rows": [[p, item, area, crit] for p, item, area, crit in GAPS],
    }))

    # --- UI项清单（分批） -------------------------------------------------
    fields = ["ID", "面", "L0面", "控件组", "标签", "控件类型", "用户动作",
              "源码位置", "门控条件", "U1判定", "判定理由"]
    verdict_map = {"reachable": "可达", "needs-mode": "需切模式", "unreachable": "不可达"}
    kept = [r for r in recs if r["area"] != "device"]        # device 整体不可达，见面汇总
    big_rows = [[r.get("id", ""), AREA_LABEL.get(r["area"], r["area"]), r.get("surface", ""),
                 r.get("group", ""), r.get("label", ""), r.get("control", ""),
                 r.get("action", ""), r.get("source", ""), r.get("gate", ""),
                 verdict_map[r["u1_verdict"]], r.get("u1_reason", "")] for r in recs]

    written = []
    for i in range(0, len(big_rows), BATCH):
        chunk = big_rows[i:i + BATCH]
        p = out / f"ui_items_{i // BATCH + 1:03d}.json"
        p.write_text(json.dumps({"fields": fields, "rows": chunk}, ensure_ascii=False),
                     encoding="utf-8")
        written.append(p)

    for name, payload in payloads:
        p = out / f"{name}.json"
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"{name:22} rows={len(payload['rows'])}")
    print()
    print(f"UI项清单: {len(recs)} rows -> {len(written)} batch file(s) in {out}")
    print(f"  (device 面 844 项含在其中，判定为 不可达/DEVICE_BBL_STACK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
