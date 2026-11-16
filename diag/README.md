# diag/ — 历史诊断与标定探针

本目录是**取证/标定用的历史脚本集合**，不是用例套件的一部分。

- 不参与 `hv_go` 批量、不参与 74 条基线、不产生验收结论。
- 只用于复现问题、标定坐标/控件、验证某个假设；结论应回写到
  [`docs/PITFALLS.md`](../docs/PITFALLS.md) 或对应版本的报告里。
- 没有代码 `import diag`；移动/归档这些脚本不影响 `harness/`、`tests/`、
  `runner/` 的运行路径。

## 目录快照（2026-11-16）

共 221 个 tracked 文件（178 个 `.py` + 34 个 `.ps1` + 数据/文档）：

| 前缀/子目录 | 数量 | 用途 |
|---|---:|---|
| `probe_241_*` | 53 | Orca 2.4.1 的控件/坐标/耗材选择器标定 |
| `probe_242_*` | 51 | Orca 2.4.2 的菜单、对象列表、PA 对话框、输入通道标定 |
| `diag_*` | 55 | 按用例的临时诊断（`diag_m4_*`、`diag_m5_*`、`diag_m7_*`、`diag_m8_*` 等） |
| `guest_*.ps1`、`vm_*.ps1`、`read_*.ps1` 等 | 22+ | 客机/relay/Hyper-V 的临时操作与读数脚本 |
| `feishu_0908/` | 10 | 2026-09-08 飞书记录的一次性快照与解析脚本 |

其中不少是**迭代试错链**（如 `probe_241_picker2..10`、
`probe_242_pa207b..f`、`probe_241_plate2..12`）。它们保留是为了证据可追溯，
不代表都应该再跑一遍。

## 命名约定

- `probe_<版本>_<主题>.py`：版本相关探针，例如 `probe_242_submenu.py`。
- `diag_<用例或主题>[_<序号>].py`：按用例/主题的诊断，例如
  `diag_m7_slots.py`、`diag_125_probe_aux2.py`。
- `guest_*.ps1`、`vm_*.ps1`、`read_*.ps1`：客机/relay 的临时脚本；
  当前正式的跑批入口在 [`runner/`](../runner/README.md)，不要从 diag 里找跑批入口。
- 新探针遵循同样前缀；一次性输出放 `artifacts/`，不要提交大文件。

## 运行规则

1. 批量化/启动 app 的探针按仓根 [`README.md`](../README.md) 的跑批纪律走：
   默认在 Hyper-V 客机；宿主直跑必须 `ORCA_BB_ALLOW_HOST=1`，且结果只算 dev 证据。
2. 必须用独立 `--datadir`/沙盒，不碰真实用户配置。
3. 跑前杀残留 app/python；跑后自己收尾，避免下一次用例撞 datadir 锁。
4. 先读脚本头部的日期/版本/前提；历史探针可能针对 2.4.0/2.4.1 的 UI，
   在 2.4.2 上不保证仍成立。
5. 探针结论不要直接当用例判据；需要固化的，走
   `tests/<分组>/` + `cases.py` 注册 + `# feishu:` 注解的正式流程。

## 常用入口

- 2.4.1 探针索引：[`docs/PITFALLS.md`](../docs/PITFALLS.md) §21.9。
- 2.4.2 适配与探针清单：
  [`docs/handoffs/242/adapt.md`](../docs/handoffs/242/adapt.md) §7。
- 用例判定/覆盖口径：[`docs/BLACKBOX_CASES.md`](../docs/BLACKBOX_CASES.md)。
- MCP 的 `list_cases` 会把 `diag/*.py` 作为可选脚本列出；通过 MCP 跑它们
  仍然只是探针，不会进入基线统计。

## 维护

- **不要物理删除**历史探针；确实要淘汰时移到 `archive/`（若后续做 Phase 4b）
  或保留原处，并在提交信息里说明。
- 归档/改名后用 `git log --follow <新路径>` 追溯历史。
- `__pycache__/` 是本地缓存，已在 `.gitignore` 中，不属于探针资产。
