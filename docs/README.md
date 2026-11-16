# docs — 文档索引

仓根 `README.md` 的「跑批纪律与收尾」是唯一权威条文，`AGENTS.md` 是会话纪律指针；
本目录存放证据、映射、报告和交接，不重复纪律条文。

## 证据与登记

| 文档 | 内容 |
|---|---|
| [PITFALLS.md](PITFALLS.md) | 实测坑册（原 `PITFALLS_0901.md`；§1–§21，全部有日志/帧证据） |
| [BLACKBOX_CASES.md](BLACKBOX_CASES.md) | 用例登记册：判定标准、证据链、覆盖状态 |
| [feishu/BASELINE.md](feishu/BASELINE.md) | 飞书「基线用例」表 → 套件映射 |
| [feishu/MAINFLOW.md](feishu/MAINFLOW.md) | 飞书主流程/模板 → 套件映射 |
| [feishu/MAPPING.md](feishu/MAPPING.md) | 飞书证据表映射 |

## 版本报告（`reports/<版本>/`）

| 文档 | 内容 |
|---|---|
| [reports/241/FAILURES.md](reports/241/FAILURES.md) | Orca 2.4.1 失败清单与收敛结论 |
| [reports/242/FINDINGS.md](reports/242/FINDINGS.md) | Orca 2.4.2 疑似产品问题清单（F-1…） |
| [reports/242/RUN_REPORT.md](reports/242/RUN_REPORT.md) | Orca 2.4.2 全量复跑分类报告 |
| [reports/242/ACCEPTANCE_LATEST.md](reports/242/ACCEPTANCE_LATEST.md) | 最新 2.4.2 验收记录（含 exe/DLL MD5） |
| [reports/plate_b04c365/ACCEPTANCE.md](reports/plate_b04c365/ACCEPTANCE.md) | plate 专项构建 b04c365 验收 |

## 交接（`handoffs/<版本>/`）

| 文档 | 内容 |
|---|---|
| [handoffs/241/batch1.md](handoffs/241/batch1.md) | 2.4.1 基线第一批（#152/153/156/158 + 预设选择） |
| [handoffs/241/batch2.md](handoffs/241/batch2.md) | 2.4.1 基线第二批（#184–#204） |
| [handoffs/242/adapt.md](handoffs/242/adapt.md) | 2.4.2 适配交接提示词 |

## 方案与评估

| 文档 | 内容 |
|---|---|
| [STRUCTURING_PLAN.md](STRUCTURING_PLAN.md) | 套件结构化方案（第一期落地 + 第二期路线） |
| [UIA_EVAL_0903.md](UIA_EVAL_0903.md) | UIA 混合定位评估（2026-09-03） |
| [UIA_WIZARD_PROBE_PLAN.md](UIA_WIZARD_PROBE_PLAN.md) | UIA 向导探针方案 |
| [VM_SETUP_HYPERV.md](VM_SETUP_HYPERV.md) | Hyper-V Win11 测试客机装机记录 |

## 命名约定

- **版本进目录，不进文件名**：`reports/242/FINDINGS.md`，不写 `242_FINDINGS.md`。
- 点时间分析（如 `UIA_EVAL_0903.md`）保留日期，便于判断结论时效。
- 新报告先放 `reports/<版本>/`；跨版本通用证据放 `docs/` 顶层或 `PITFALLS.md`。
- 移动/改名后用 `git log --follow <新路径>` 仍可追溯历史。
