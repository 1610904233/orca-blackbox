# 交接：Orca 2.4.1 基线收敛（新会话从这里开始）

> 会话纪律以 `README.md`「跑批纪律与收尾（新会话必读）」为唯一权威，`PITFALLS_0901.md` 是证据库
> （**§21 是 2.4.1 专章，动手前必读**）。本文件只是**当前进度快照**。

## 0. 一句话状态

Orca **2.4.1** 基线复跑剩下的 **8 条真失败已全部转绿**（逐条客机复跑确认），
全部根因都在驱动层/环境，**没有发现产品侧的功能缺陷**（两条"行为变化"见 §3）。
全量 36 例基线复跑（本轮修复后）正在进行/已完成，结果见 `241_FAILURES.md` 末尾「收敛结论」。

## 1. 环境事实（都已验证）

| 项 | 值 |
|---|---|
| 客机 | Hyper-V `win11-test`，账号 `test`，Python `C:\Python311\python.exe`（探针用 `pythonw.exe`，见 §4） |
| 仓库 | 客机 `C:\coil\orca-blackbox`（宿主 `D:\code\orca_blackbox`） |
| 应用（2.4.1） | `C:\coil\apps\Snapmaker_Orca_Windows_V2.4.1_portable\snapmaker-orca.exe` |
| 应用（2.4.0，保留） | `C:\coil\apps\Snapmaker_Orca_Windows_V2.4.0_portable\snapmaker-orca.exe` |
| 选构建 | 客机**机器级**环境变量 `ORCA_VISION_APP_EXE`（当前指向 2.4.1） |
| 跑批沙盒 datadir | `artifacts/m3_profile`（`harness/profile.py` 播种；**播种的默认槽位耗材是用户预设 `... - FLOW-TEST`**） |
| 夹具 | `fixtures/mixed_filament_test.3mf` |
| 唯一跑批入口 | `runner/hv_go.ps1`（宿主直跑须 `ORCA_BB_ALLOW_HOST=1`） |
| 作业提交 | 宿主 `C:\coil\vm_setup\submit_job.ps1 -Job <job.ps1> -TimeoutSec N`，job 放 `C:\coil\vm_setup\jobs\` |
| 2.4.1 故障/取证 | `artifacts/videos/241_failures/`、客机 `artifacts/{pscan,pscan2,pchip,pchip2,pslot,phf,prot,pgiz,puseed,pug}*.{log,png}` |

## 2. 本轮改了什么（都在未提交的工作区里）

| 文件 | 内容 |
|---|---|
| `tests/m8_common.py` | 2.4.1 双栏耗材选择框原语：小步滚动扫描（`_picker_scan_for`）、hover 切分支、同厂商跳过厂商行、**tooltip 全名消歧**（`_picker_tooltip_scan`）、取色 chip/16x25 的**坐标空间修正**（子窗口 rect 即屏幕坐标）+ 取色重试 |
| `tests/m7_common.py` | `confirm_filament_grouping()`（2.4.1 切片时弹的 `Custom Filament Grouping` 确认框）+ 接进 `op_slice`；gizmo 网格的"两行合成"加**真行距/同面板**约束；`type_into_field` 加"点兄弟格去焦后复核再提交"（`_sibling_box`） |
| `harness/export_util.py` | `wait_save_dialog` 改**按标题**匹配（原来任意 #32770 都算，会抓到残留提示框）；`_dismiss_stale_prompts()`；每个 early return 加诊断打印 |
| `PITFALLS_0901.md` | 新增 **§21**（9 条实测坑：控制台吞点击 / 屏幕坐标 / hover 语义 / 小步滚动 / 同厂商 / tooltip 消歧 / 2.4.1 配置事实 / relay 只认 token\|path / job 需 BOM） |
| `241_FAILURES.md` | 末尾新增「收敛结论」：8 条逐条根因 + 结论表 |
| `diag/probe_241_*.py`、`diag/analyze_gizmo_ocr.py` | 本轮全部取证探针（约 20 个，未提交） |

## 3. 两条 2.4.1 的**行为变化**（测试方需要知道）

1. **切片前的喷嘴分配确认框改了时机与形态**：2.4.0 是"切 Nozzle Flow 时"提示；2.4.1 是
   **点 Slice 之后**弹 `Custom Filament Grouping`（'Slicing will follow the nozzle assignment
   below:' / Cancel / **Confirm**），不 Confirm 不开始切片（表现为"点击被吞"）。
2. **新的双栏耗材选择框**（产品文档《准备页——耗材分类管理》V0.1）实测形态：
   左栏 = `------ System presets ------` + 厂商列表 + `------ Add/Remove filament ------`；
   **槽位当前是用户预设时**，左栏顶部变成 `------ User presets ------` + `Custom »`；
   用户预设行**被面板截断**，全名只在 hover tooltip 里（`PLA SnapSpeed @U1 - STD-TEST`）。
   `PLA Rainbow` 在 Snapmaker 二级列表里（**无需**任何"配置可选材料"勾选）；
   `PLA Full Spectrum` 反而不在该列表里。

## 4. 探针纪律（血泪，务必遵守）

- 探针一律 **`C:\Python311\pythonw.exe`** + 自写日志（`sys.stdout` 为 None 要守卫）：
  用 `cmd /c python` 起探针会在桌面留一个控制台窗口**盖住 app 吞掉真实点击**
  （PITFALLS §21.1，前一会话的"控件没反应"结论全栽在这）。
- 探针要 `WindowFromPoint` + 比对 pid，确认点击真的落在被测 app 上。
- 只读探针不要 `session.close()`（attach 到在跑的实例）；自己 boot 的才关。
- 套件在跑时**不要**起探针（`seed_profile` 会 taskkill 掉套件的 app，PITFALLS §10/§11）。
- 文件投放/回传：relay 只认 `token|脚本路径`，所以 push_verify/fetch_file 是哑的 →
  一律"job 内 base64"（投放：`j360_ship_rerun.ps1` 模板；回传：`j413_*` 字符串分块模板）。
- job .ps1 带中文注释要 **UTF-8 BOM**（`encoding='utf-8-sig'`），否则 PS 5.1 解析崩。

## 5. 收尾状态（10-12 已全部完成）

1. **提交推送**：已完成，4 个提交 `cc8dda9..59216ff`（m8 原语 / m7+harness / 探针 17 个 / 文档）。
2. **客机同步**：已 `fetch + merge --ff-only` 到 `59216ff`，跟踪文件工作区干净；
   按用户决定，上一会话的试错链探针 15 个（picker1..9 / rainbow_enable1..4 / material_pick1..2）
   **未入库**，仅存在于宿主与客机工作区。
3. **飞书写回**：已完成 `python tools/feishu_writeback.py --from-annotations --apply <36 例>`
   → **62 条记录**写入并读回校验通过（`自动化状态=已自动化`）。
   注意：写回需 lark-cli **用户身份** token，bot 身份会被拒（PITFALLS §21.10）。
4. **全量 36 例**：修复后单批 PASS=36 FAIL=0（junit tests=36 failures=0）。

### 下次可做（非本轮范围）
- 把 `regression` 套件（74 例）在 2.4.1 上跑一遍。
- 2.4.1 的两条行为变化（切片确认框时机、双栏耗材框的用户预设分组/截断行）
  是否要作为产品反馈提给开发，由测试方定。
