"""cases.py — the single source of truth for runnable black-box cases.

Pure data, no batch logic. Every batch entry point (tools/run_regression.sh,
runner/hv_go.ps1, mcp_server.py run_case/list_cases) consumes THIS dict —
never keep a second hardcoded list anywhere.

Rules:
- key = script stem; keys are stable IDs, NEVER rename (push_verify.py /
  zlog.ps1 / Feishu tables index history by case name).
- add a case = add one entry (+ the script); disable = enabled: False
  (soft-off — logs/history stay intact). Do not physically delete entries.
- suite: "regression" = the nightly suite; "smoke" = m0/m1/m2 engine/chain
  checks; None = registered & runnable via MCP but not in any default batch
  (m3a-m3i early business-path cases, m1b engine experiment).
- tier: coverage tier from docs/BLACKBOX_CASES.md (A strong / B weak / C
  not-blackbox-testable). "TBD" = not yet registered in docs/BLACKBOX_CASES.md
  (the m5 series — its pitfalls live in docs/PITFALLS.md instead).
- summary: NOT stored — extracted live from the script's line-2 header
  comment ("# <stem>.py — ..."), so the script stays the single home for
  it (sync enforced by tools/check_registry.py).
- platforms: tuple of platforms the case can run on.  Default ("windows",)
  keeps every existing case Windows-only; a future macOS-migrated case
  opts in with platforms=("windows", "macos").  ``enabled`` stays the
  authoritative on/off switch — platform filtering never changes it.
- MACOS_SMOKE: macOS-only smoke suite (m0/m1/m2), registered separately
  from CASES so the Windows 126/74 registry and Feishu mapping stay
  untouched.  Run it with tools/run_macos_smoke.sh.
- MACOS_BASELINE: macOS ports of enabled Windows baseline cases.  Kept
  separate from CASES so the Windows suite never tries to run them; each
  entry names its Windows source in ``windows_case``.  Run it with
  tools/run_macos_baseline.sh.
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Platform registry: canonical names are "windows" / "macos".
DEFAULT_PLATFORMS: tuple[str, ...] = ("windows",)
_PLATFORM_ALIASES = {
    "windows": "windows", "win": "windows", "win32": "windows",
    "macos": "macos", "darwin": "macos", "mac": "macos",
}


def _r(milestone: str, tier: str, **extra) -> dict:
    """Shorthand for an enabled regression-suite entry (file filled below).
    known_limitation=True = documented PARTIAL/降级 (docs/BLACKBOX_CASES.md) — the
    pytest shell maps it to xfail(strict=False)."""
    d = {"file": None, "milestone": milestone, "tier": tier,
         "suite": "regression", "enabled": True}
    d.update(extra)
    return d


def _o(milestone: str, tier: str, **extra) -> dict:
    """Shorthand for an enabled but not-in-any-suite entry (file filled
    below). Extra kwargs mirror _r (e.g. known_limitation)."""
    d = {"file": None, "milestone": milestone, "tier": tier,
         "suite": None, "enabled": True}
    d.update(extra)
    return d


CASES: dict[str, dict] = {
    # --- smoke (engine / chain checks) --------------------------------------
    # file= is filled in below from the on-disk layout: cases live in
    # tests/<group>/ keyed by the Feishu baseline table's 二级分类 (see
    # GROUP_LABELS); unclassified engine/chain cases live in tests/engine/.
    "m0_boot_check": {
        "milestone": "m0", "tier": "A",
        "suite": "smoke", "enabled": True,
    },
    "m0_anchor_health": {
        "milestone": "m0", "tier": "A",
        "suite": "smoke", "enabled": True,
    },
    "m1_minimal_loop": {
        "milestone": "m1", "tier": "A",
        "suite": "smoke", "enabled": True,
    },
    "m1b_maa": {
        "milestone": "m1", "tier": "A",
        "suite": None, "enabled": False,  # engine experiment (m0: MaaFw rejected)
    },
    "m2_slice_chain": {
        "milestone": "m2", "tier": "A",
        "suite": "smoke", "enabled": True,
    },
    # --- m3a-m3i: early business-path cases (runnable, not in the suite) -----
    "m3a_empty_slice": _o("m3", "A"),
    "m3b_delete_scene": _o("m3", "A"),
    "m3c_corrupt_3mf": _o("m3", "A"),
    "m3d_param_reslice": _o("m3", "A"),
    "m3e_preset_switch": _o("m3", "A"),
    "m3f_multi_plate": _o("m3", "A"),
    "m3g_export_3mf": _o("m3", "A"),
    "m3h_undo_redo": _o("m3", "A"),
    "m3i_view_menu": _o("m3", "A"),
    # --- regression suite: mixing (m3j-m4j) ----------------------------------
    "m3j_mixing_entry": _r("m3", "A"),
    "m3k_mixing_match": _r("m3", "A"),
    "m3l_mixing_delta": _r("m3", "A"),
    "m3m_mixing_filaments": _r("m3", "A"),
    "m3n_mixing_cancel": _r("m3", "A"),
    "m3o_mixing_nomodel": _r("m3", "A"),
    "m3p_mixing_persist": _r("m3", "A"),
    "m3q_mixing_view": _r("m3", "A"),
    "m3r_mixing_progress": _r("m3", "A"),
    "m3s_mixing_hover": _r("m3", "B", known_limitation=True),   # #8 hover tooltips — 降级/PARTIAL in docs/BLACKBOX_CASES.md L85
    "m3t_mixing_add_ratio": _r("m3", "A"),
    "m3u_mixing_ratio_flow": _r("m3", "A"),
    "m3v_mixing_cycle_input": _r("m3", "A"),
    "m3w_mixing_cycle_flow": _r("m3", "A"),
    "m3x_mixing_match": _r("m3", "A"),
    "m3y_mixing_gradient": _r("m3", "A"),
    "m3z_mixing_compat": _r("m3", "A"),
    "m4a_mixing_gates": _r("m4", "A"),
    "m4b_batch_manual": _r("m4", "A"),
    "m4c_mixing_panel": _r("m4", "A"),
    "m4d_mixing_filops": _r("m4", "A"),
    "m4e_mixing_paint": _r("m4", "B", known_limitation=True),   # 表1#39 部分 — docs/BLACKBOX_CASES.md L96
    "m4f_mixing_cap64": _r("m4", "A"),
    "m4g_mixing_sublayer": _r("m4", "A"),
    "m4h_mixing_templates": _r("m4", "A"),
    "m4i_mixing_slice": _r("m4", "A"),
    "m4j_mixing_samecolor": _r("m4", "A"),
    # --- regression suite: process params (m5a-m5h) --------------------------
    # tier TBD: not registered in docs/BLACKBOX_CASES.md (pitfalls in docs/PITFALLS.md)
    "m5a_preset_cycle": _r("m5", "TBD"),
    "m5b_quality_params": _r("m5", "TBD"),
    "m5c_strength_infill": _r("m5", "TBD"),
    "m5d_support_enable": _r("m5", "TBD"),
    "m5e_combo_params": _r("m5", "TBD"),
    "m5f_negative_params": _r("m5", "TBD"),
    "m5g_preset_manage": _r("m5", "TBD"),
    "m5h_ironing_combos": _r("m5", "TBD"),
    # --- m6: transform via artifact (absorbed from white-box ab3b34adf5:459) --
    "m6a_transform_verify": _r("m6", "A"),
    # --- regression suite: main flow (m7, Feishu 测试用例 base tblLR8zYgwBuggDI
    #     — GUI业务 #7-#24 原子 + 主流程-模板 O/M 链; mapping in docs/feishu/MAINFLOW.md)
    "m7a_boot_shutdown": _r("m7", "A"),
    "m7b_new_project": _r("m7", "A"),
    "m7c_import_stl": _r("m7", "A"),
    "m7d_import_corrupt": _r("m7", "A"),
    "m7e_rotate45": _r("m7", "A"),
    "m7f_scale120": _r("m7", "A"),
    "m7g_arrange": _r("m7", "A"),
    "m7h_context_delete": _r("m7", "A"),
    "m7i_add_primitive": _r("m7", "A"),
    "m7j_change_filament": _r("m7", "A"),
    "m7k_flush_options": _r("m7", "B", known_limitation=True),
    "m7t72": _r("m7", "A"),
    "m7t73": _r("m7", "A"),
    "m7t74": _r("m7", "A"),
    "m7t75": _r("m7", "B"),
    "m7t77": _r("m7", "B"),
    "m7t78": _r("m7", "B"),
    "m7t79": _r("m7", "B", known_limitation=True),
    "m7t80": _r("m7", "B"),
    "m7t81": _r("m7", "B", known_limitation=True),
    "m7t82": _r("m7", "B"),
    "m7t83": _r("m7", "A"),
    "m7t84": _r("m7", "B", known_limitation=True),
    "m7t86": _r("m7", "B"),
    "m7t87": _r("m7", "B"),
    "m7t88": _r("m7", "B"),
    "m7t89": _r("m7", "B"),
    "m7t109": _r("m7", "B", known_limitation=True),
    # --- m8 (2026-09-17 批次: 飞书基线用例 base EDUAbYWcbaL2HOsgFM1cXmBpn5f,
    #     Fit/官方颜色/温类门/净化器/高流量; 2026-09-21 用户确认 b/c/d/f 也挂进
    #     regression —— 此前 suite=None 导致"实现了却没人跑"，是覆盖盲区) ------
    "m8a_fit_view": _r("m8", "A"),                       # GREEN 09-17 客机
    "m8z_assembly_import": _r("m8", "A"),   # #20 导入含装配关系工程 + 装配视图（11-12 新增）
    "m8b_official_color": _r("m8", "A", known_limitation=True),
    "m8c_temp_mix_gate": _r("m8", "A", known_limitation=True),
    "m8d_purifier_gcode": _r("m8", "A", known_limitation=True),
    "m8e_purifier_weakcool": _r("m8", "A"),              # GREEN 09-17 客机
    "m8f_nozzle_flow": _r("m8", "A", known_limitation=True),
    # 2026-09-23 拆分: #136 单一变量对比独立成例（同会话连切两次会把客机
    # 内存吃满 → cv2/tesseract OOM；各流量状态一个会话后不再撞墙）
    "m8g_flow_single": _r("m8", "A"),
    # 2026-09-28 新增 #123（软化温度 → 温类归类 → GCode 更新）: 编辑器里
    # 'Softening temperature' 就是 temperature_vitrification；改它并走
    # "Save Filament as" 保存后重切，顶盖 SET_PURIFIER_MODE 的分支翻转
    # （vitr<=50 → 强冷 MODE=1，>50 → 保温 MODE=3）。
    "m8x_123_softening_temp": _r("m8", "A"),
    # 2026-09-29 新增 #137（三类配置带流量喷嘴标志的参数对比）: 面在**0.4 喷嘴机型的
    # 0.20mm Standard 工艺预设**里——工艺参数面板会出现 Standard / High Flow 两个 tab；
    # 喷嘴区那个 Flow 组合框不是这条用例的面（0.8 喷嘴机型上它不可交互）。
    "m8x_137_flow_param_tabs": _r("m8", "A"),
    # 2026-09-29 新增 #125（工艺全局辅材冲突，打开偏好后可切片）: 测试方口径
    # **主材 = 对象的耗材丝、辅材 = 涂色**；面在准备页耗材列 + 涂色 gizmo +
    # 切片按钮门禁 + Preferences 的 "Allow high/low temperature filament mixing"。
    "m8x_125_aux_mix_pref": _r("m8", "A"),
    # 2026-10-15 主流程四行逐行落地（一行一例；打印链=人工 -> 飞书「部分自动化」）：
    "m8x_152": _r("m8", "A"),     # #152 首次安装后新建项目并完成打印（本地段）
    "m8x_153": _r("m8", "A"),     # #153 多模型布局与本地文件打印（本地段）
    "m8x_156": _r("m8", "A"),     # #156 模型快速调整与局域网打印（本地段）
    "m8x_158": _r("m8", "A"),     # #158 模型布局优化与多设备切换（本地段）
    # 2026-10-22 飞书新增 #184–#204：逐条落地（B 类先写）
    "m8x_199": _r("m8", "A"),     # #199 新建项目（未保存确认）
    "m8x_200": _r("m8", "A"),     # #200 打开项目
    "m8x_202": _r("m8", "A"),     # #202 项目另存为
    "m8x_201": _r("m8", "A"),     # #201 保存项目
    "m8x_204": _r("m8", "A"),     # #204 导出（STL）
    "m8x_185": _r("m8", "A"),     # #185 添加（工具栏按钮导入）
    "m8x_186": _r("m8", "A"),     # #186 添加新盘
    "m8x_187": _r("m8", "A"),     # #187 自动定位/调整对象（Q/Shift+Q）
    "m8x_188": _r("m8", "A"),     # #188 全局整理（多盘 + 空盘删除）
    "m8x_189": _r("m8", "A"),     # #189 单盘整理（Shift+A 只动当前盘）
    "m8x_191": _r("m8", "A"),     # #191 旋转（X/Y/Z 相对+绝对 45°）
    "m8x_194": _r("m8", "A"),     # #194 移除当前板
    "m8x_195": _r("m8", "A"),     # #195 调整零件朝向（Auto orient）
    "m8x_196": _r("m8", "A"),   # #196 排列零件（盘侧按钮，11-12 新增）
    "m8x_197": _r("m8", "A"),   # #197 锁定当前板（盘侧按钮，11-12 新增）
    "m8x_198": _r("m8", "A"),   # #198 编辑盘名（Plate Settings，11-12 新增）
    "m8x_206": _r("m8", "A"),   # #206 校准菜单存在性（顶栏 Calibration，11-12 新增）
    "m8x_207": _r("m8", "A"),   # #207 压力提前弹窗非法输入（警告框拒绝，11-12 新增）
    "m8x_208": _r("m8", "A"),   # #208 温度塔（默认 230→190，9 档 gcode，11-12 新增）
    "m8x_209": _r("m8", "A"),   # #209 流量粗调（Pass 1，9 块 flowrate，11-12 新增）
    "m8x_210": _r("m8", "A"),   # #210 流量细调（Pass 2，10 块 flowrate，11-12 新增）
    "m8x_211": _r("m8", "A"),   # #211 压力提前默认 PA 塔（0~0.1/0.002，11-12 新增）
    "m8x_212": _r("m8", "A"),   # #212 回抽测试（0~2mm 步长 0.1，11-12 新增）
    "m8x_213": _r("m8", "A"),   # #213 最大体积流量（5~20/0.5 mm³/s，11-12 新增）
    "m8x_214": _r("m8", "A"),   # #214 输入整形频率（X/Y 15~110Hz/0.15，11-12 新增）
    "m8x_217": _r("m8", "A"),   # #217 YOLO 流量对比（11/16 块，11-13 新增）
    "m8x_218": _r("m8", "A"),   # #218 温度塔默认区间（6 组耗材映射，11-13 新增）
    "m8x_221": _r("m8", "A"),   # #221 PA 划线模式（Print numbers 勾选可编辑，11-13 新增）
    "m8x_222": _r("m8", "A"),   # #222 PA V 形模式（Print numbers 勾选禁用，11-13 新增）
    "m8x_190": _r("m8", "A"),     # #190 移动（X/Y/Z 输入 100）
    "m8x_192": _r("m8", "A"),     # #192 缩放（150% 等比）
    "m8x_193": _r("m8", "A"),     # #193 涂色（多色区域 + 切片分段）
    "m8x_203": _r("m8", "A"),     # #203 导入（文件菜单 → STL）
}


# 分组目录的 slug ↔ 飞书基线表「二级分类」中文名（目录命名用 slug，避开非 ASCII
# 路径在这条 PowerShell/PSDirect 工具链上的编码坑；中文名只作展示与映射）。
GROUP_LABELS: dict[str, str] = {
    "mixing_match": "混色匹配映射",
    "mixing": "混色功能",
    "mainflow": "主流程-用例",
    "gui": "GUI业务",
    "topcap": "顶盖1.4.0",
    "filament": "耗材管理",
    "fit_view": "一键还原视图",
    "high_flow": "高流量热端",
    "engine": "(无基线映射 / 引擎与链路用例)",
}

# 归属特例（迁移时人工判定，2026-09-21）：用例覆盖的飞书记录跨多个二级分类，或某条
# 映射只是 PARTIAL 交叉引用 —— 此时用例的实际分组与记录的分组不同，校验器
# （tools/check_feishu_map.py）把这些登记为已知例外。
GROUP_OVERRIDES: dict[str, str] = {
    "m4d_mixing_filops": "记录跨「混色功能」+「主流程-用例」→ 归更具体的功能组",
    "m4i_mixing_slice": "记录跨「混色功能」+「主流程-用例」→ 归更具体的功能组",
    "m4e_mixing_paint": "仅一条 PARTIAL 主流程引用 → 留在混色功能组",
    "m2_slice_chain": "仅一条 PARTIAL 耗材管理引用 → 留在 engine（核心切片引擎）",
}


def _group_of(stem: str) -> str | None:
    """tests/ 下持有该用例脚本的分组目录名（None = 还没归组）。"""
    tdir = HERE / "tests"
    for d in sorted(tdir.iterdir()):
        if d.is_dir() and not d.name.startswith("__") and (d / f"{stem}.py").exists():
            return d.name
    return None


# file= 由磁盘布局推导（键名 == 脚本 stem）：tests/<group>/<key>.py。移动脚本
# 只需挪文件，注册表自动跟随。
for _k, _v in CASES.items():
    if _v.get("file") is None:
        _g = _group_of(_k)
        _v["file"] = f"tests/{_g}/{_k}.py" if _g else f"tests/{_k}.py"
    _v["group"] = _group_of(_k) or "engine"
    # Every existing case is Windows-only unless it explicitly opts in.
    _v.setdefault("platforms", DEFAULT_PLATFORMS)


# macOS-only smoke suite.  Deliberately separate from CASES: the Windows
# registry (126 entries / 74 enabled), Feishu mapping and soft-off logic must
# not change just because the macOS chains exist.
MACOS_SMOKE: dict[str, dict] = {
    "m0_macos_boot_check": {
        "file": "tests/engine/m0_macos_boot_check.py",
        "milestone": "m0", "tier": "A",
        "suite": "macos_smoke", "platforms": ("macos",), "enabled": True,
    },
    "m1_macos_tab_switch": {
        "file": "tests/engine/m1_macos_tab_switch.py",
        "milestone": "m1", "tier": "A",
        "suite": "macos_smoke", "platforms": ("macos",), "enabled": True,
    },
    "m2_macos_slice_chain": {
        "file": "tests/engine/m2_macos_slice_chain.py",
        "milestone": "m2", "tier": "A",
        "suite": "macos_smoke", "platforms": ("macos",), "enabled": True,
    },
}
for _name, _meta in MACOS_SMOKE.items():
    _meta.setdefault("platforms", ("macos",))
    _meta.setdefault("group", "engine")


# macOS ports of ENABLED Windows baseline cases (the 74).  These are the
# first entries; m8a/m4 ports will follow.  They stay out of CASES so the
# Windows pytest/runner never collects them.
MACOS_BASELINE: dict[str, dict] = {
    "m2_macos_slice_chain": {
        "file": "tests/engine/macos_pilot/m2_slice_chain.py",
        "windows_case": "m2_slice_chain",
        "milestone": "m2", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m7a_macos_boot_shutdown": {
        "file": "tests/engine/macos_pilot/m7a_boot_shutdown.py",
        "windows_case": "m7a_boot_shutdown",
        "milestone": "m7", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3j_macos_mixing_entry": {
        "file": "tests/engine/macos_pilot/m3j_mixing_entry.py",
        "windows_case": "m3j_mixing_entry",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m4a_macos_mixing_gates": {
        "file": "tests/engine/macos_pilot/m4a_mixing_gates.py",
        "windows_case": "m4a_mixing_gates",
        "milestone": "m4", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8a_macos_fit_view": {
        "file": "tests/engine/macos_pilot/m8a_fit_view.py",
        "windows_case": "m8a_fit_view",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m7b_macos_new_project": {
        "file": "tests/engine/macos_pilot/m7b_new_project.py",
        "windows_case": "m7b_new_project",
        "milestone": "m7", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m7h_macos_context_delete": {
        "file": "tests/engine/macos_pilot/m7h_context_delete.py",
        "windows_case": "m7h_context_delete",
        "milestone": "m7", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m7t73_macos_new_create_delete": {
        "file": "tests/engine/macos_pilot/m7t73_new_create_delete.py",
        "windows_case": "m7t73",
        "milestone": "m7", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m7t75_macos_layout_arrange_delete": {
        "file": "tests/engine/macos_pilot/m7t75.py",
        "windows_case": "m7t75",
        "milestone": "m7", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m7t74_macos_transform_chain": {
        "file": "tests/engine/macos_pilot/m7t74.py",
        "windows_case": "m7t74",
        "milestone": "m7", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m7t89_macos_create_paint_slice": {
        "file": "tests/engine/macos_pilot/m7t89.py",
        "windows_case": "m7t89",
        "milestone": "m7", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_199_macos_new_project_confirm": {
        "file": "tests/engine/macos_pilot/m8x_199_new_project_confirm.py",
        "windows_case": "m8x_199",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_206_macos_calibration_menu": {
        "file": "tests/engine/macos_pilot/m8x_206_calibration_menu.py",
        "windows_case": "m8x_206",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_202_macos_save_as": {
        "file": "tests/engine/macos_pilot/m8x_202_save_as.py",
        "windows_case": "m8x_202",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m7c_macos_import_stl": {
        "file": "tests/engine/macos_pilot/m7c_import_stl.py",
        "windows_case": "m7c_import_stl",
        "milestone": "m7", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_200_macos_open_project": {
        "file": "tests/engine/macos_pilot/m8x_200_open_project.py",
        "windows_case": "m8x_200",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_204_macos_export_stl": {
        "file": "tests/engine/macos_pilot/m8x_204_export_stl.py",
        "windows_case": "m8x_204",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_207_macos_pa_invalid": {
        "file": "tests/engine/macos_pilot/m8x_207_pa_invalid.py",
        "windows_case": "m8x_207",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_201_macos_save_project": {
        "file": "tests/engine/macos_pilot/m8x_201_save_project.py",
        "windows_case": "m8x_201",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_218_macos_temp_defaults": {
        "file": "tests/engine/macos_pilot/m8x_218_temp_defaults.py",
        "windows_case": "m8x_218",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_203_macos_import_stl": {
        "file": "tests/engine/macos_pilot/m8x_203_import_stl.py",
        "windows_case": "m8x_203",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_185_macos_toolbar_add": {
        "file": "tests/engine/macos_pilot/m8x_185_toolbar_add.py",
        "windows_case": "m8x_185",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_186_macos_add_plate": {
        "file": "tests/engine/macos_pilot/m8x_186_add_plate.py",
        "windows_case": "m8x_186",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_188_macos_arrange_all": {
        "file": "tests/engine/macos_pilot/m8x_188_arrange_all.py",
        "windows_case": "m8x_188",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_189_macos_arrange_plate": {
        "file": "tests/engine/macos_pilot/m8x_189_arrange_plate.py",
        "windows_case": "m8x_189",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_198_macos_plate_name": {
        "file": "tests/engine/macos_pilot/m8x_198_plate_name.py",
        "windows_case": "m8x_198",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_211_macos_pa_tower": {
        "file": "tests/engine/macos_pilot/m8x_211_pa_tower.py",
        "windows_case": "m8x_211",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_212_macos_retraction": {
        "file": "tests/engine/macos_pilot/m8x_212_retraction.py",
        "windows_case": "m8x_212",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_213_macos_max_flow": {
        "file": "tests/engine/macos_pilot/m8x_213_max_flow.py",
        "windows_case": "m8x_213",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_214_macos_input_shaping": {
        "file": "tests/engine/macos_pilot/m8x_214_input_shaping.py",
        "windows_case": "m8x_214",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_208_macos_temp_tower": {
        "file": "tests/engine/macos_pilot/m8x_208_temp_tower.py",
        "windows_case": "m8x_208",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_209_macos_flow_pass1": {
        "file": "tests/engine/macos_pilot/m8x_209_flow_pass1.py",
        "windows_case": "m8x_209",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_210_macos_flow_pass2": {
        "file": "tests/engine/macos_pilot/m8x_210_flow_pass2.py",
        "windows_case": "m8x_210",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_217_macos_yolo": {
        "file": "tests/engine/macos_pilot/m8x_217_yolo.py",
        "windows_case": "m8x_217",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_195_macos_auto_orient": {
        "file": "tests/engine/macos_pilot/m8x_195_auto_orient.py",
        "windows_case": "m8x_195",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_187_macos_auto_orient_all": {
        "file": "tests/engine/macos_pilot/m8x_187_auto_orient_all.py",
        "windows_case": "m8x_187",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8z_macos_assembly_import": {
        "file": "tests/engine/macos_pilot/m8z_assembly_import.py",
        "windows_case": "m8z_assembly_import",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_194_macos_remove_plate": {
        "file": "tests/engine/macos_pilot/m8x_194_remove_plate.py",
        "windows_case": "m8x_194",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_193_macos_two_region_paint": {
        "file": "tests/engine/macos_pilot/m8x_193.py",
        "windows_case": "m8x_193",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_192_macos_uniform_scale": {
        "file": "tests/engine/macos_pilot/m8x_192.py",
        "windows_case": "m8x_192",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_190_macos_move_xyz": {
        "file": "tests/engine/macos_pilot/m8x_190.py",
        "windows_case": "m8x_190",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_191_macos_rotate_xyz": {
        "file": "tests/engine/macos_pilot/m8x_191.py",
        "windows_case": "m8x_191",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_152_macos_transform_merge": {
        "file": "tests/engine/macos_pilot/m8x_152.py",
        "windows_case": "m8x_152",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_156_macos_drag_transforms": {
        "file": "tests/engine/macos_pilot/m8x_156.py",
        "windows_case": "m8x_156",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_197_macos_lock_plate": {
        "file": "tests/engine/macos_pilot/m8x_197_lock_plate.py",
        "windows_case": "m8x_197",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_196_macos_plate_arrange": {
        "file": "tests/engine/macos_pilot/m8x_196_plate_arrange.py",
        "windows_case": "m8x_196",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_158_macos_layout_multi": {
        "file": "tests/engine/macos_pilot/m8x_158_layout_multi.py",
        "windows_case": "m8x_158",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8d_macos_purifier_gcode": {
        "file": "tests/engine/macos_pilot/m8d_purifier_gcode.py",
        "windows_case": "m8d_purifier_gcode",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8c_macos_temp_mix_gate": {
        "file": "tests/engine/macos_pilot/m8c_temp_mix_gate.py",
        "windows_case": "m8c_temp_mix_gate",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_153_macos_layout_print": {
        "file": "tests/engine/macos_pilot/m8x_153_layout_print.py",
        "windows_case": "m8x_153",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8b_macos_official_color": {
        "file": "tests/engine/macos_pilot/m8b_official_color.py",
        "windows_case": "m8b_official_color",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8g_macos_flow_single": {
        "file": "tests/engine/macos_pilot/m8g_flow_single.py",
        "windows_case": "m8g_flow_single",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8f_macos_nozzle_flow": {
        "file": "tests/engine/macos_pilot/m8f_nozzle_flow.py",
        "windows_case": "m8f_nozzle_flow",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3e_macos_preset_switch": {
        "file": "tests/engine/macos_pilot/m3e_preset_switch.py",
        "windows_case": "m3e_preset_switch",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8e_macos_purifier_weakcool": {
        "file": "tests/engine/macos_pilot/m8e_purifier_weakcool.py",
        "windows_case": "m8e_purifier_weakcool",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_123_macos_softening_temp": {
        "file": "tests/engine/macos_pilot/m8x_123_softening_temp.py",
        "windows_case": "m8x_123_softening_temp",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_137_macos_flow_param_tabs": {
        "file": "tests/engine/macos_pilot/m8x_137_flow_param_tabs.py",
        "windows_case": "m8x_137_flow_param_tabs",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m8x_125_macos_aux_mix_pref": {
        "file": "tests/engine/macos_pilot/m8x_125_aux_mix_pref.py",
        "windows_case": "m8x_125_aux_mix_pref",
        "milestone": "m8", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3k_macos_mixing_match": {
        "file": "tests/engine/macos_pilot/m3k_mixing_match.py",
        "windows_case": "m3k_mixing_match",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3l_macos_mixing_delta": {
        "file": "tests/engine/macos_pilot/m3l_mixing_delta.py",
        "windows_case": "m3l_mixing_delta",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3m_macos_mixing_filaments": {
        "file": "tests/engine/macos_pilot/m3m_mixing_filaments.py",
        "windows_case": "m3m_mixing_filaments",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3s_macos_mixing_hover": {
        "file": "tests/engine/macos_pilot/m3s_mixing_hover.py",
        "windows_case": "m3s_mixing_hover",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3r_macos_mixing_progress": {
        "file": "tests/engine/macos_pilot/m3r_mixing_progress.py",
        "windows_case": "m3r_mixing_progress",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m4b_macos_batch_manual": {
        "file": "tests/engine/macos_pilot/m4b_batch_manual.py",
        "windows_case": "m4b_batch_manual",
        "milestone": "m4", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m4d_macos_mixing_filops": {
        "file": "tests/engine/macos_pilot/m4d_mixing_filops.py",
        "windows_case": "m4d_mixing_filops",
        "milestone": "m4", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3t_macos_mixing_add_ratio": {
        "file": "tests/engine/macos_pilot/m3t_mixing_add_ratio.py",
        "windows_case": "m3t_mixing_add_ratio",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3u_macos_mixing_ratio_flow": {
        "file": "tests/engine/macos_pilot/m3u_mixing_ratio_flow.py",
        "windows_case": "m3u_mixing_ratio_flow",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3v_macos_mixing_cycle_input": {
        "file": "tests/engine/macos_pilot/m3v_mixing_cycle_input.py",
        "windows_case": "m3v_mixing_cycle_input",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3x_macos_mixing_match": {
        "file": "tests/engine/macos_pilot/m3x_mixing_match.py",
        "windows_case": "m3x_mixing_match",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m3y_macos_mixing_gradient": {
        "file": "tests/engine/macos_pilot/m3y_mixing_gradient.py",
        "windows_case": "m3y_mixing_gradient",
        "milestone": "m3", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m4i_macos_mixing_slice": {
        "file": "tests/engine/macos_pilot/m4i_mixing_slice.py",
        "windows_case": "m4i_mixing_slice",
        "milestone": "m4", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
    "m4e_macos_mixing_paint": {
        "file": "tests/engine/macos_pilot/m4e_mixing_paint.py",
        "windows_case": "m4e_mixing_paint",
        "milestone": "m4", "tier": "A",
        "suite": "macos_baseline", "platforms": ("macos",), "enabled": True,
    },
}
for _name, _meta in MACOS_BASELINE.items():
    _meta.setdefault("platforms", ("macos",))
    _meta.setdefault("group", "engine")


def _case_meta(name: str) -> dict:
    """Metadata for a Windows CASES entry or a macOS registry entry."""
    return (CASES.get(name) or MACOS_SMOKE.get(name)
            or MACOS_BASELINE.get(name) or {})


def normalize_platform(name: str | None) -> str:
    """Canonical platform name ('windows' / 'macos' / unchanged)."""
    if not name:
        return ""
    low = str(name).lower()
    return _PLATFORM_ALIASES.get(low, low)


def case_platforms(name: str) -> tuple[str, ...]:
    """Platforms a registered case declares (default: Windows-only)."""
    return tuple(_case_meta(name).get("platforms", DEFAULT_PLATFORMS))


def supports_platform(name: str, platform: str | None) -> bool:
    """Whether `name` declares support for `platform` (aliases accepted)."""
    plat = normalize_platform(platform)
    if not plat:
        return True
    return plat in {normalize_platform(p) for p in case_platforms(name)}


def enabled_cases_for(platform: str, suite: str | None = None) -> list[str]:
    """Enabled case names that declare support for `platform`.

    This is an additive filter: ``enabled_cases`` keeps its historical
    behaviour (no platform filtering) so existing Windows entry points are
    untouched.  ``suite="baseline"`` intersects the baseline set.
    """
    if suite == "baseline":
        names = baseline_cases()
    else:
        names = enabled_cases(suite)
    return [n for n in names if supports_platform(n, platform)]


def group_label(name: str) -> str:
    """用例所属分组的飞书二级分类中文名（无映射的为 engine 的说明文案）。"""
    g = _case_meta(name).get("group", "engine")
    return GROUP_LABELS.get(g, g)


# 每个用例脚本头部声明其飞书来源，形如：
#     # feishu: baseline#164 baseline#156      （多条用空格分隔）
#     # feishu: none                            （引擎/链路用例，无基线记录）
# 注解是"代码 → 飞书"的唯一权威来源；tools/check_feishu_map.py 做双向校验。
_FEISHU_RE = re.compile(r"^#\s*feishu:\s*(.+?)\s*$")


def feishu_refs(name: str) -> list[str] | None:
    """脚本注解里声明的飞书引用。

    None = 没有注解（校验器会报错：新用例漏加注解）
    []   = 显式 none
    else = ["baseline#164", ...]
    """
    path = case_path(name)
    if not path or not path.exists():
        return None
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()[:8]:
        m = _FEISHU_RE.match(ln.strip())
        if m:
            val = m.group(1).strip()
            return [] if val.lower().startswith("none") else val.split()
    return None


def summary(name: str) -> str:
    """Live-extract the case's summary from its line-2 header comment
    ("# <stem>.py — ..."); empty string when the script has none."""
    meta = _case_meta(name)
    if not meta:
        return ""
    try:
        head = (HERE / meta["file"]).read_text(
            encoding="utf-8", errors="replace").splitlines()[:5]
    except OSError:
        return ""
    for ln in head:
        m = re.match(rf"#\s*{re.escape(name)}\.py\s*[—-]?\s*(.+)$", ln.strip())
        if m:
            return m.group(1).strip()
    return ""


def enabled_cases(suite: str | None = None) -> list[str]:
    """Enabled case names, optionally filtered to a suite (None = all enabled).

    suite="baseline" = 只在飞书基线表里有映射的用例（注解 `# feishu: baseline#N`），
    即"基线用例文档里"的那些 —— 日常只跑它们即可，其余引擎/链路用例按需再跑。
    """
    if suite == "baseline":
        return baseline_cases()
    return [k for k, v in CASES.items()
            if v["enabled"] and (suite is None or v["suite"] == suite)]


def baseline_cases() -> list[str]:
    """启用的、在飞书基线表里有用例映射的用例（按注册表顺序）。"""
    return [k for k, v in CASES.items()
            if v["enabled"] and any(r.startswith("baseline#")
                                    for r in (feishu_refs(k) or []))]


def case_path(name: str) -> Path | None:
    v = _case_meta(name)
    return HERE / v["file"] if v else None


def macos_smoke_cases(enabled_only: bool = True) -> list[str]:
    """macOS-only smoke case names (registered in MACOS_SMOKE)."""
    return [k for k, v in MACOS_SMOKE.items()
            if not enabled_only or v.get("enabled", True)]


def macos_baseline_cases(enabled_only: bool = True) -> list[str]:
    """macOS ports of enabled Windows baseline cases (MACOS_BASELINE)."""
    return [k for k, v in MACOS_BASELINE.items()
            if not enabled_only or v.get("enabled", True)]


def macos_case_path(name: str) -> Path | None:
    v = MACOS_SMOKE.get(name) or MACOS_BASELINE.get(name)
    return HERE / v["file"] if v else None


# --- 非基线用例软关闭（2026-11-15，用户要求） ------------------------------
# 只把「没有 # feishu: baseline#N 注解」的用例置为 enabled=False：文件、注册
# 项、文档引用和历史索引全部保留（不物理删除）；基线 74 个脚本 / 96 行不受
# 影响。需要恢复某条时，把它自己的 enabled 改回 True，或把下面总开关改
# False 一次性恢复全部非基线用例。
_SOFT_OFF_NON_BASELINE = True
if _SOFT_OFF_NON_BASELINE:
    for _name, _meta in CASES.items():
        if not _meta["enabled"]:
            continue
        if not any(r.startswith("baseline#")
                   for r in (feishu_refs(_name) or [])):
            _meta["enabled"] = False
