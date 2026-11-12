# HANDOFF_242_ADAPT — Orca 2.4.2 适配交接提示词

> 用法：把本文件「提示词正文」整段贴到新窗口即可继续。写入日期 2026-10-29。

---

## 提示词正文（复制以下全部）

继续 orca_blackbox 的 **Orca 2.4.2 适配 + 全量复跑**。仓库 `D:\code\orca_blackbox`（branch main，HEAD `960dfb3`）。

### 0. 硬纪律（先读 AGENTS.md 与 README「跑批纪律与收尾」）

- 批量/用例/探针一律在 Hyper-V 客机 `win11-test` 跑，唯一入口 `runner/hv_go.ps1`；宿主直跑须 `ORCA_BB_ALLOW_HOST=1`，`harness/host_guard.py` 会 exit 2。
- 给客机下任务只能走宿主 `C:\coil\vm_setup\submit_job.ps1 -Job <job.ps1>`（relay 以**交互计划任务**身份执行；只有交互会话才能建出稳定主窗口）。
- **所有 job .ps1 / 探针脚本一律用 Write 工具写文件**，禁止 Git Bash heredoc（会吞反斜杠：`\a`→BEL、`\r`→CR，已多次导致 job 未启动）。
- token / app secret / user_access_token **不进对话**；飞书写回只用 `tools/feishu_writeback.py`，**绝不把扫码/授权 URL 甩给用户**。
- 上游源码 `C:\coil\Projects\SnapmakerOrca` **只读**。
- 一次只跑一个 suite；重跑前先杀残留（`C:\coil\vm_setup\jobs\j669_killsuite.ps1`），必要时重启客机（`j715_reboot.ps1`）。
- 用户明确要求：**全量执行过程中出错不要自行改用例**，先跑完、再统一适配。

### 1. 当前状态

**2.4.1（已完成，勿动）**：57 条基线脚本全 GREEN，全部 commit+push（HEAD `960dfb3`），飞书 79 行（75 已自动化 + 4 部分自动化）已写回「已自动化」并回读验证。基线 suite = 57 个脚本，覆盖飞书 79 行。

**2.4.2 第一轮全量**（旧包 `orca242c`）：**6 GREEN / 51 RED**
- GREEN：`m7a_boot_shutdown`, `m8x_192`, `m8x_193`, `m8x_194`, `m8x_195`, `m8x_203`
- 结论：不是包坏了。红色集中在 5 个观察面（见 §3）。

**新包已替换并逐文件校验**（与宿主 MD5 一致）：
```
C:\coil\apps\orca242d\Snapmaker_Orca\snapmaker-orca.exe
zip                f283825f52a09c7deffc17d33f424f2d
exe                8ae99dabc8497929e30662a53708c9ff
Snapmaker_Orca.dll 77a922562e074b372e1b28c3f79b4276
TKMath.dll         2995dd21136f734668c1a900dd39b1a2
```
2.4.1 仍在默认路径；`runner/hv_go.ps1` 已有 `-Exe` 参数（commit `c336ae5`，注入 `ORCA_VISION_APP_EXE`）。

### 2. 运行命令与日志

```powershell
# 全量（job 模板 j800_full242c.ps1 / j802_hvgo.ps1，把路径改成 orca242d）
runner/hv_go.ps1 -NoSync -Suite baseline -Exe 'C:\coil\apps\orca242d\Snapmaker_Orca\snapmaker-orca.exe'
# 单例
runner/hv_go.ps1 -NoSync -Cases 'm8x_194' -Exe '<同上>'
```
- 客机日志：`C:\coil\p242.log`（探针/任务输出）、`C:\coil\orca-blackbox\artifacts\...`（结果 json / 视频 / 截图）。
- 取回宿主：`runner/hv_harvest.ps1`。
- 查询类 job：`j816_p242state.ps1`（任务状态+日志尾）、`j812_tiplog.ps1`、`j823_finalstate.ps1`。

### 3. 2.4.2 已确诊的观察面变化（适配依据）

**① 工具条 tooltip 完全取不到（根因，约 17 例红）**
跳变 / 微移 / 滑入三种悬停都拿不到可见 `tooltips_class32` 窗口，主窗口 OCR 也空；`m7.find_slot` 依赖 tooltip 文本，因此全线失效。
**已有解药**：2.4.1 的 x→tooltip 槽位表已导出并取回宿主 `artifacts/slot_table_241.json`（2690B，40 条）。关键 x：
```
686 ?            722 Add [Ctrl+1]      758 Add plate        794 ?
812 Auto orient 848 Arrange all [A]   902 Split to objects 938 Split to parts
992 Variable layer height             1064 Move            1100 Rotate
1154 Scale       1190 Lay on Face [F]  1244 Mesh Boolean [B]
1280 Support Painting [L]             1334 Seam painting [P]
1370 Paint-on fuzzy skin [H]          1406 Color painting [N]
1460 Emboss [T]  1496 Measure          1550 Assemble        1586 Brim Ears
1658 Assembly View
```
注意表里 y 有 76/84/92 三个值，`m7.BAR_Y=84`；少数条目是 OCR 噪声，匹配谓词时用关键词（"rotate"/"arrange"/"add plate"…）。

**② 菜单结构未变，HMENU 可直读（约 14 例红）**
hover 开子菜单在 2.4.2 上不稳定，但 `MN_GETHMENU` 枚举稳定：
```
FILE: New 325 / Open 326 / Save 328 / Save as 329 / Import 子菜单(330 导入模型, 331 Zip, 332 配置) / Export 子菜单(334–340) / Quit 5006
DROPDOWN: Edit(Delete Selected 347, Delete All 348) / View(Default View 353, Fit in all view 360, Perspective 34918, Orthogonal 34919)
```
→ 适配：用 `GetSubMenu` + `FindItem` + `WM_COMMAND` 按 id 派发，绕开 hover。可复跑 `diag/probe_242_submenu.py`。

**③ Print/Export 模式切换：探针已证明「消息点击行」有效**
`find_print_buttons`：opt=`(1784,37,1808,61)`、main=`('Print',(1810,37,1882,61))`；chevron 点击后弹 `wxWindowNR 'panel' (1757,67,1920,123)`，行 `['Export G-code file','Print']`；`wait_popup` 正常；**msg-click 后主按钮标签变为 `Export G-code file`**。
→ 所以 `harness/export_util.switch_to_export_mode` 不是断点；`m3e`/`m4i`/`m8x_123`/`m8x_156` 的红要回到各自用例日志看**进入导出模式之后**的步骤（切片按钮模板 0.666 疑似状态相关，不是模板漂移：2.4.1 vs 2.4.2 的 Slice plate 裁图肉眼几乎一致）。

**④ 混色对话框可打开，但控件点不中（14 例红，m3j..m4d）**
`m3j` 能读到默认模式 `Auto`；`m3k` 输出 `mode switched to Manual: False`。→ 需要新探针标定 2.4.2 对话框内控件几何（打开对话框 → PrintWindow 截图 → 枚举子控件 → 逐控件试点击并回读模式文本）。

**⑤ 启动多一个 `configuration update` 拦截窗**
boot 等待建议 90s → 150s（`harness/launcher.find_main_window` 调用处 / 用例 boot 等待）；`m8x_194` 曾因 90s 不足偶发。

**其余零星红（3 例，单独看）**
- `m8x_190`：`tz 10.00 -> 1.00` —— 2.4.2 的 Move 字段顺序/索引漂移（绝对字段仍会持久化，可用回读确认）。
- `m8b`：官方材质色弹窗不出现。
- `m8f`：Python traceback（先看栈）。

### 4. 适配补丁清单（按序做，每项先小冒烟）

1. `tests/m7_common.py::scan_slots/find_slot`：hover 无 tooltip 时回退到 `STATIC_SLOTS_241`（读 `artifacts/slot_table_241.json` 或内置常量）。**回退必须做效果验证**：点完 rotate 看 `gizmo_row_boxes` 是否非空；点完 add plate 看盘层宽度是否 ≥1.25 倍；无效果则试 x±22 邻位。
2. `harness/topbar_util.py`：新增 `dispatch_submenu(session, top_idx, child_substr_or_id)`（MN_GETHMENU→GetSubMenu→WM_COMMAND），替换 `harness/export_util` 与用例里所有 hover 开子菜单的路径（Import / Export / Delete All / Fit in all view）。
3. `harness/export_util.switch_to_export_mode`：**保持现状**（探针已证明有效）；转而排查 export 模式之后的步骤。
4. boot 等待 90→150s。
5. 混色对话框：新写 `diag/probe_242_mix.py` 做控件标定，再改 `m4e_mixing_*` 的点击位。
6. `m8x_190` 字段索引、`m8b` 弹窗、`m8f` 栈：逐条定位。

### 5. 验证与收尾

- 每项补丁：2.4.2d 上跑对应单例（`-Cases`）确认由红转绿，再进入下一项。
- 全量复跑：`-Suite baseline -Exe ...\orca242d\...`，出**分类诚实报告**（GREEN / 红按根因归类，不许把未验证写成 GREEN）。
- 结果 md5/视频在客机 `artifacts/`，用 `hv_harvest.ps1` 拉回；需要用户看片时先拉视频再等确认。
- 改动 commit+push 前先讲清变动；飞书写回仅 GREEN/已覆盖，走 `tools/feishu_writeback.py`（`--from-annotations --export artifacts/feishu_241_batch2.ndjson --base-token NhqXbsLgPaJ4wvsGtjecsx83n3c --table-id tblWFGvJ5KQGVInq --field 自动化状态`）。

### 6. 踩坑速查（都已付过代价）

1. **PS 5.1 `Expand-Archive` 会毁大包**（同尺寸全零 DLL，`e_lfanew=0`）→ 客机解压一律用 **Python `zipfile`**，逐文件比 MD5。之前「2.4.2 包坏了」的结论已推翻。
2. `Copy-VMFile` 首次常静默失效，第二次才成；以客机侧 MD5 为准。
3. `j654` 推送在客机离线时会静默不生效 → job 输出必须看到 `shipped <file>` 行。
4. `SendMessageW(dlg, WM_COMMAND, IDOK)` 在目标文件已存在/路径不存在时会**永久阻塞**（10 分钟挂死）→ 保存前先 `unlink`，临时文件名必须以 `.3mf` 结尾。
5. 相对字段提交后回读恒为 0.00（假阴性）→ 用「临时保存 + 矩阵 Δ」验证；绝对字段可回读。
6. gizmo 面板开着会**抑制盘侧图标点击**（§21.19）；同一会话第二次开面板是聋的。
7. DWM 崩溃风暴（约 12 分钟卡驱动 + 归档器狂拍 PrintWindow）会硬杀交互任务树 → 会话要短，长跑前重启客机；父进程捕获 `TimeoutExpired` 继续。
8. 3mf：component `p:path` 带前导 `/`，zip 条目没有 → `lstrip("/")`；float32 序列化噪声 → 容差 1e-3。
9. pyflakes 报警会截断 `&&` 链（曾导致推送 job 根本没生成）→ 推送前先确认 `ALL-CLEAN`。
10. 涂色黑盒六条硬约束见 `PITFALLS_0901.md` §21.20；`§21.17/18/19` 分别对应 DWM 风暴、IDOK 死锁、gizmo 抑制。

### 7. 现成资产

- 探针：`diag/probe_242_surfaces.py`（菜单+工具条）、`probe_242_submenu.py`（HMENU，最有用）、`probe_242_printbtn.py`（msg vs real click，已跑通）、`probe_242_tipwin.py`/`tipnudge.py`/`tooltip.py`（均证明 2.4.2 无 tooltip）、`probe_241_slottable.py`（生成槽位表）。
- 槽位表：`artifacts/slot_table_241.json`（已取回宿主）。
- job：`C:\coil\vm_setup\jobs\` 下 `j800_full242c.ps1`（全量 2.4.2）、`j802_hvgo.ps1`、`j816_p242state.ps1`、`j819_slottable.ps1`、`j822_printbtn.ps1`、`j823_finalstate.ps1`、`j669_killsuite.ps1`、`j715_reboot.ps1`。
- 未跟踪文件：`HANDOFF_241_BATCH2.md`、`artifacts/slot_table_241.json`、上述 diag 探针——适配完成后再决定是否提交（提交前先讲变动）。

现在从「§4 第 1 项」开始，先补 `find_slot` 的固定几何回退并在 2.4.2d 上冒烟。

---

## 附：本次会话的判定要点（给新窗口的背景，不必逐条执行）

- #184 检测内存占用维持人工，不做黑盒；其余 #185–#204 全部已自动化。
- 2.4.1 阶段最后 4 条（#190/#192/#193/#203）与 #187/#188/#189/#191/#194/#195 均在 `960dfb3` 之前提交，飞书已回读。
- 2.4.2 的适配只允许改 harness/用例的定位方式，**不放宽判据**；红线仍是「未验证不得写 GREEN」。
