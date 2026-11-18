# vision_gui 黑盒套件 — 0901 踩坑实录（最大化 + m5 主流程）

按"现象 → 根因 → 修法 → 证据/复跑"汇总 2026-08-31 ～ 09-01 的全部坑。
复跑入口：`hv_go.ps1 -Cases <diag 脚本名>`（诊断脚本都在本目录，日志落
`artifacts\regress_<名>.log`，帧落 `artifacts\` 与 `artifacts\shots\<case>\`）。

---

## 1. Hyper-V 控制台分辨率自动跌落（本轮最大坑）

- **现象**：m5b/c/d"侧栏坍缩"、OCR 全空、`options_viewport None`，帧尺寸
  1366×751 → 误判为"窗口被还原/布局坍缩"，查了 ensure_advanced、tab 点击
  等一路弯路。
- **根因**：VMConnect 控制台断开/变化后，客机显示模式**自动降级**
  （1920×1080 → 1366×768 → 1024×768）。最大化的窗口跟着屏幕缩——不是窗口
  问题，`ShowWindow(SW_MAXIMIZE)` 修不了（实测 re-maximize 后 rect 仍是
  `(-7,-7,1373,727)` = 小屏上的最大化）。所有按 1920×1032 client 标定的
  判定全部失效。
- **修法**：重启 VM（控制台重连）+ 保持一个 vmconnect 会话 +
  `tools/setres_1080.py`（交互会话内 ChangeDisplaySettings 1920×1080，rc=0 且
  生效）。跑套件前必查分辨率。
- **证据/复跑**：`tools/setres_1080.py`（自报交互会话分辨率）；diag 日志
  `re-maximized: rect=(-7,-7,1373,727)`。
- **附**：PS Direct 会话里 `Screen.AllScreens` 的读数（1024×768）是它自己
  会话的，**不代表交互桌面**，不可信；要在交互会话内读
  （GetSystemMetrics / setres 自报）。

## 2. 空盘启动三重坑：Setup Wizard + 无打印机 + 工艺预设下拉为空

- **现象**：空盘 boot 弹 `#32770 'Setup Wizard'`（820×660，盖在最上方）；
  Printer 区空、无喷嘴直径；**Slice 按钮灰**（无法切片）；工艺预设下拉
  只有 `Default Setting` 一项（System presets 分节头是空的）。
- **根因**：未选打印机触发首启向导 + Slice 门禁；且工艺预设库按
  **打印机预设名**过滤——`0.24 Standard @Snapmaker U1 (0.8 nozzle)` 的
  `compatible_printers = ['Snapmaker U1 (0.8 nozzle)']`，基础版
  `Snapmaker U1`（0.4 喷嘴）不匹配任何一个，全部被滤掉。
- **修法**：m5 弃用空盘启动 → **fixture 上下文 boot**（3mf 内嵌
  U1 (0.8 nozzle) 打印机 + 0.40 工艺预设）→ 删除载入模型 → 右键加标准
  Cube。预设下拉随即列出全部 U1 0.8 系统预设（0.24/0.32/0.40/0.48/…）。
- **备选**：向导本身 `WM_CLOSE` 可直接关（diag 验证 `wizard closed: True`）；
  "配置掉"需补"已选打印机"相关 conf 键，未验证。
- **证据/复跑**：`diag_m5_wizard.py`；录像里若见欢迎页遮挡即此（空盘 boot
  才有；fixture boot 的正式录像没有）。

## 3. Setup Wizard 是 HTML（wxWebView）

- **现象**：向导内没有可枚举的原生按钮（children 只有 wxWebView/
  Chrome_RenderWidgetHostHWND），OCR 定位按钮 + 相对坐标点击太脆。
- **修法（0901 判）**：不驱动它——绕开（见 #2）或 WM_CLOSE。**HTML 界面一律不碰**。
- **证据/复跑**：`diag_m5_wizard.py` v1。
- **0904 修订（--wizard 实弹 5 轮，UIA_EVAL §七）**：前提半过时——"不可枚举"
  只对 pywinauto 控制视图成立；comtypes RawViewWalker 重根 + 激活重试（Chromium
  web a11y 树懒激活，激活前是 chrome 结构+空 Document 的 stub）后 web 内容可见
  （24 节点/12 命名/交互 2），且可经 **LegacyIAccessible.DoDefaultAction** 结构化
  驱动（InvokePattern 不可得；方法名不是 DoDefault——AttributeError 是 pre-click
  失败，别误标已点击）。"OCR 点 HTML 太脆"结论保留；"HTML 一律不碰"收窄为
  **"回归用例不碰 HTML"**（探针/评估通道可经 UIA 检测与驱动）。

## 4. 真右键被远控层吞掉

- **现象**：SendInput 右键 3/3 无效（菜单不弹），同点位 message-level
  `WM_RBUTTONDOWN/UP` 100% 弹出原生菜单。
- **修法**：`add_shape.py` / `m5_common.py` 一律 msg 右键开菜单 +
  **真实左键**点行（原生菜单跑模态循环，message 左键点不动行——沿用
  topbar_util 结论）。
- **证据/复跑**：`diag_m5_menu.py` v2/v3。

## 5. 右键菜单行定位：序列匹配 + 坐标空间

- **现象**：'Delete All' / 'Select All' / 'Delete Plate' 都含 "Delete"或
  "All"，子串匹配会点错；曾因菜单截图相对坐标被当屏幕绝对坐标使用，点到
  屏幕左上角把应用点死。
- **修法**：`m5_common._seq_point(mr, words, seq)` 词**序列**匹配且一律加
  菜单 rect 偏移；`_delete_row_point` 优先 'Delete All'，裸 'Delete' 排除
  后缀 'Plate'。
- **证据/复跑**：`diag_m5_menu.py` v3（Cube 落盘全链路）。

## 6. 选项面板 combo：值是绘制的、无窗口文本

- **现象**：Seam position 的 'Aligned' OCR 得到，但 GetWindowText 为空；
  dialog 式 `switch_combo`（wxWindowNR 'panel' 弹窗、28px 行）不适用——
  点击落到 `hwnd 0x0`。
- **根因**：选项面板的值由 OG_CustomCtrl **绘制**，控件本身无文本；且其
  下拉不是 dialog 的 panel 弹窗。
- **修法**：`process_panel.find_option_combo` = OCR 找值文本 →
  `WindowFromPoint` 解析真实控件；`cycle_combo_to` = 真实点击聚焦 →
  方向键 + 回车逐项切换 → OCR 验证提交值。
- **证据/复跑**：m5b/m5d 日志（cycle 逐步打印）；m5a 的预设选择器走的是
  真文本（'0.40 Standard …'），两者机制不同。

## 7. 参数目标必须先实证标签存在（Quality 页没有 'Wall loops'）

- **现象**：按上游 Orca 习惯去 Quality 页找 'Wall loops'，OCR 轮询 6 次
  全空；Seam 组滚动定位一度 420s 超时。
- **根因**：这个 fork 的 Quality 页 'Walls and surfaces' 组只有两个
  Only-one-wall 复选框；**'Wall loops 2' 在 Strength 页顶部**。
- **修法**：选参数前先用 diag/帧确认标签在哪个页面；click_tab 的
  expect_word 用**首屏可见**内容（Strength 页 = 'loops'，不是 'infill'）。
- **证据/复跑**：m5c 日志 band 打印 `'walls wall loops 2 alternate …'`。

## 8. Tree (auto) 支撑在 U1 0.8 预设上配置非法

- **现象**：Enable support 勾选后 Slice 按钮变灰，红色错误 toast
  "Organic support tree tip diameter must not be smaller than support
  material extrusion width"；切片模板匹配 0.666（done/灰特征）。
- **根因**：默认 Type=Tree (auto) 的有机树尖端直径与 U1 0.8 预设的支撑
  挤出宽冲突，配置校验失败禁用切片。
- **修法**：m5d 勾选后把 Type 组合框切到 Normal（cycle_combo_to）。
- **证据/复跑**：`shots/m5d_support_enable/L010`（灰按钮 + 错误 toast）。

## 9. 小模型的"落盘"判定阈值

- **现象**：右键 Cube 已落盘但判定 FAIL（chroma 0.581% < 0.006）。
- **根因**：0.006 是按 mixed fixture 大模型标的；20mm Cube 在 1920 视口里
  只贡献 ~0.58%。
- **修法**：`add_shape.py` 落盘判定改为 `≥0.003 且 >3×空盘基线`
  （空盘 ~0.063%）。

## 10. seed PermissionError（datadir 被上一个 app 占住）

- **现象**：套件首例 `seed_profile` 在 rmtree m3_profile 时
  `WinError 32 … log\*.log.0 being used by another process`。
- **根因**：上一用例 app 的收尾竞态（graceful close 未完全退出）持有日志
  句柄；套件背靠背启动时必现。
- **修法**：`profile.py` seed 前先 `taskkill /IM snapmaker-orca.exe /F` +
  rmtree 重试 ×3（间隔 3s）。另：跑套件前先经 relay 杀孤儿
  （`Get-Process snapmaker-orca,python | Stop-Process -Force`）。

## 11. hv_go 重复启动 = 双实例互踩

- **现象**：误触发两次 `hv_go.ps1`：第二个实例重新注册同名计划任务，两套
  driver 在同一桌面互打（输入注入互相吞），日志/帧污染，排查极难。
- **修法**：launch 前 `(Get-ScheduledTask suite).State` + 客机 python 进程
  数确认；套件运行中**绝不**重复启动。

## 12. m4e/m4g/m4i 最大化重校准（详见 commit 9e23500991）

- m4e：工具栏扫描带/质心带/调色板带全部改为视口自适应；"已选中"判定改用
  扫描定位的**真 Rotate 槽位**（固定 x 在最大化后读到相邻 tooltip 假阳性）。
- m4g：视口 panel 高度帽（73px→随窗口拉伸）→ 滚轮静默失效；`view_band()`
  动态 OCR/验收带；勾选阈值 0.25→0.13（实测选中 0.21 / 未选 ≤0.06）；
  tab 切换 40 格强制回顶（滚动位置跨页共享）。
- m4i：`export_util.topbar_buttons` 改窗口相对带（绝对 y140-170/x>1150 只
  匹配一个窗口化位置）。

## 13. 侧栏布局双形态 → 锚定式定位

- **现象**：同一套 y 带在 fixture boot 全绿、空盘 boot 全空（Process 行
  614 ↔ 462，差 ~150px；空盘预设行文本是 'Default Setting'）。
- **修法**：`process_panel.process_row_y()` 以 'Process' 标题行为锚，
  advanced/tabs/viewport/组定位全部相对化；两种 boot 通吃（m4g 回归绿）。

## 14. 工具链小坑（relay/bash/PS Direct）

- bash 双引号里 `\$f` 是**字面量 `$f`**（两次踩：路径带 `$f` 去了不存在的
  文件）——循环推文件用 `var="..."; "…/$var"` 或逐条写全路径。
- PS Direct 的 `byte[]` 返回值不可靠（0 字节）→ 客机内 base64 编码成
  **字符串**回传，宿主解码（`fetch_mp4.py` / `send_to_guest.ps1`）。
- 经 relay 的 PS 命令里 `Select-String "a|b"` 的管道符会被转义损坏 → 拉
  日志直接 `Get-Content -Tail N`，过滤在宿主侧做。
- 多行 python 补丁脚本里的 `\\` 续行/花括号转义极易错——补丁后必须
  `py_compile` + grep 断言确认替换真的发生。

## 15. 跑套件前 checklist（血泪浓缩）

1. relay 心跳（`relay_alive.txt`；注意它只在命令完成时刷新）
2. 客机杀孤儿（relay → `Stop-Process snapmaker-orca,python`）
3. 客机交互分辨率 = 1920×1080（`hv_go -Cases setres_1080` 看自报）
4. 无残留 suite 任务实例（`(Get-ScheduledTask suite).State`）
5. 长等待用后台任务（单条 bash ≤10min）；录像/大文件走 base64 relay


## 16. 宿主↔客机通信通道规范（血泪协议）

**通道选择**（每条都有实测翻车记录）：

| 用途 | 通道 | 备注 |
|---|---|---|
| 宿主→客机文件 | `send_to_guest.ps1`（base64 经 relay） | 唯一可靠上行 |
| 客机→宿主文件 | base64 字符串经 relay_out（`fetch_mp4.py`） | PS Direct 的 `byte[]` 返回值不可靠（0 字节实测） |
| 客机内命令 | relay → `Invoke-Command -VMName`（PS Direct） | 非交互会话：GUI 判定必须走 hv_go 的 INTERACTIVE 计划任务 |
| 大文件 | 逐文件 base64，~7MB/文件 ~20s/文件 | 209MB/27 文件实测 ~15 分钟 |

**推送纪律**（每次推送后必须做，血泪教训）：

1. 看排队回显：`queued (0 KB)` = 推送路径错误（bash 双引号里 `\$var`
   变字面量等），`queued (N KB)` 才是出队成功。
2. **推送后必须双端 MD5 比对**——relay 命令会被后续命令覆盖、bash 转义
   会静默失败，"没推上"伪装成"修复无效"能烧掉几小时。用
   `C:\coilm_setup\push_verify.py <local> <guest>`（推+校验一体，
   MD5 不匹配退出码非 0）。
3. relay 命令文件是单槽的：连续两次推送中间必须等 relay 消费（文件
   被删除），否则后一次覆盖前一次——静默丢命令。

**relay 应答解析竞态**（`fetch_mp4.py` v2 的规则）：relay_out.txt 里
上一次的 `=== DONE` 还在，只等 DONE 会读到旧应答。必须等三件事同时
成立：①首行 `=== RUN` 时间戳与发送前不同；②出现 `=== DONE`；③文件
大小连续两次采样不变。

**PS Direct 陷阱**：

- `Screen.AllScreens` 的读数是 **PS Direct 自己会话的**，不代表交互
  桌面（实测它报 1024×768 而交互桌面是 1366/1920）——分辨率只能在
  交互会话内自报（如 `tools/setres_1080.py` 走 hv_go）。
- 复杂 PowerShell（多层引号/管道/Here-String）内联进 relay_cmd 必炸
  （实测 `Select-String "a|b"`、Add-Type C#）——写成 `.ps1` 文件用
  `& 文件名` 调用（见 `clean_guest.ps1` / `max_vmconnect.ps1` 模式）。
- `Set-VMVideo` 单独设置不生效（枚举是 Maximum/Single/Default；且需
  控制台 attached）——恢复分辨率用「重启 VM + 保持 vmconnect 最大化」。

**双套件互踩**（§11 的补充细节）：hv_go 的 Unregister+Register **不会
杀掉运行中的任务实例**——上一套件没跑完就启新一轮，两个驱动 +
两个 app 争抢全局输入注入和同一个 datadir，失败模式完全不确定（实测
m5b 三个不同断言在三轮里各挂各的）。启新套件前：`clean_guest.ps1` 杀
孤儿 + 确认上一套件 SUMMARY 已出。

**通信工具清单**（`C:\coil\vm_setup\`，未入仓库）：
`push_verify.py`（推+校验一体）/ `fetch_mp4.py` + `fetch_all_mp4.py`
（guest→host base64，v2 修了 DONE 竞态）/ `fetch_relay.sh`（单文件
bash 版）/ `clean_guest.ps1`（杀孤儿）/ `max_vmconnect.ps1`（控制台
最大化，分辨率恢复用）。

---

## 17. 0902 补充：m5e–m5h 轮实测新坑

### 17.1 hv_go 必须在提权 PowerShell 里跑
- **现象**：非提权 bash 里 `powershell -Command "& hv_go.ps1 ..."` 照样
  打印 `[4] DONE`，但客机侧什么都没发生（任务/progress/log 全是上一轮
  的遗留）——`Get-VM` Permission denied 被 tail 截掉。
- **修法**：hv_go 一律经 elevated relay 跑：
  `relay_run.py "& hv_go.ps1 -Cases ..."`。
- **佐证**：log mtime + `progress_tail` 是旧的 = 启动没生效。

### 17.2 PS Direct 查询一律写成 .ps1 探针文件
- **现象**：经 relay 的内联 `Get-Content/Get-ChildItem | ...` 命令间歇性
  返回空；`Format-List` 多行输出被 Out-String 吃行。
- **修法**：宿主侧写专用探针 `zstate.ps1 / zlog.ps1 / zshots.ps1 /
  zfind.ps1`（字符串拼接输出 + `-ArgumentList` 传参），relay 只
  `& 文件`。
- **附加坑**：`relay_run.py` 读取端 v1 把正文第一行当头行丢掉——单行
  应答读成空串。已修（raw 直接 rsplit DONE）。

### 17.3 宿主→bash→heredoc 的反斜杠会被吃掉一层
- **现象**：bash heredoc python 里写 `"C:\\coil\\vm_setup"`，落盘内容是
  `C:\coil\x0bm_setup`（`\v` = 竖直制表符！）——`\\v` 经工具层解码一次
  变 `\v` 再被 python 转义。
- **修法**：heredoc python 里路径一律 `r""` 原始串或纯 argv 传参；绝不
  手写双反斜杠。

### 17.4 neutralize_focus 的 ESC 会回退"刚 Ignored"的字段值
- **现象**：m5f 里层高 1.0 → Adjust/Ignore 对话框点 Ignore（值保留
  1.0），若**紧接着** neutralize_focus（先发 ESC），ESC 把字段回退到
  提交前值（0.16）→ 配置恢复合法 → Slice 复活，"1.0 拒绝切片"断言
  随机翻车。
- **修法**：依赖"Ignore 保留值"的断言窗口内**禁止任何 ESC**；恢复焦点
  挪到断言之后。

### 17.5 模态框关掉后下一次真输入可能失焦（焦距死区）
- **现象**：m5f run1：Ignore 点击后 real_edit_set 连续 4 次拿不到焦点，
  输入全吞；`E-pre toplevel` 抓到无关的 `#32770 'Snapmaker Orca info'`
  漂浮窗（不挡点击）。
- **修法**：断言窗口过后 neutralize_focus（ESC + Process 标题行点击）
  即恢复；E/F 步已内建重试+取证打印。

### 17.6 层高越界对话框的真实边界来自 3mf 内嵌机器预设
- **事实**：fixture（Snapmaker U1 0.8 nozzle）运行时边界
  min=0.16 / max=0.56（m5b gcode echo 实证；任务表与 m4g 注释里的
  0.32/0.08 是 fdm_U1 基础值，stale）。
- **行为**（Tab.cpp:1778-1812 实测复现）：界内 0.4 无对话框；0.04 →
  "exceeds the limit" Adjust/Ignore 对话框，Adjust→0.16；0 →
  "too small" OK 对话框自动置下限；1.0 → Ignore 保留 → Print::validate
  失败 → Slice 置灰（0.666 灰特征）+ 红色错误 toast；'abc' →
  "Invalid numeric." → 字段重写为 0 → 级联 too-small 对话框 → 0.16。

### 17.7 OCR psm3 会被 '-----' 分隔线艺术字搞瞎
- **现象**：工艺预设下拉的 `------- User presets -------` 区头让
  tesseract psm3 整块丢行——`m5g_flow_preset` 行明明在截图里，词表里
  就是没有；psm 6 全部读出。
- **修法**：`ocr_words_img(img, scale, psm=...)` 加参数；列表类截图
  （popup、分区列表）一律 psm=6。

### 17.8 预设管理的黑盒坐标（m5g 全链路实测）
- **Save/Delete 按钮**：在**预设行**（Process 锚行 +20..+70px），不在
  Process 标题行（那行是 Advanced 开关 + view/compare 图标，x 314-341
  的 btn 是 Advanced 开关本体，点击/悬停都无反应）。软盘 tooltip
  'Save current Process'；删除 cross 只在选中用户预设时出现。
- **SavePresetDialog**：#32770 'Save preset'，名称 Edit 有预填文本且
  实时生效（**不需要 Enter**）；'User Preset'/'Preset Inside Project'
  单选与 'OK'/'Cancel' 全是 wxWindowNR 类（按 class 找 Button 会扑空，
  必须按文本找）。
- **落盘**：`<datadir>/user/default/process/<name>.json`（+
  .info），不是 `<datadir>/process/`。
- **重启**：空盘重启不恢复打印机上下文，预设列表只剩 'Default
  Setting'（=PITFALLS #2）；带 fixture 3mf 重启则列表完整（User
  presets 分区在 System presets 之上，psm6 可读可点）。
- **删除确认**：'Delete Preset' / 'Are you sure you want to Delete the
  selected preset?' Yes/No。

### 17.9 Ironing Type 提交后：重建期滚轮会杀死 app
- **现象**：Ironing Type popup 行点击后立刻 scroll/hunt，PrintWindow
  报 DC 失效（app 进程已死）两次；type 提交 + 12s 长静置 + tab 往返
  （Strength→Quality 复位 viewport）则稳定。
- **配套事实**：Ironing Type 行在组内**最底部**（下面就是 Wall
  generator 组标题）；Pattern 行的绘制值 psm3/psm6 都读不出、
  WindowFromPoint 也只解析到容器 panel——m5h 的第二个 combo 用 Seam
  position（'Aligned' 值 OCR 稳定）替代，Type+Seam 双 combo echo
  全绿。

### 17.10 子菜单展开过的原生菜单，WM_CANCELMODE 关不掉
- **现象**：m4d merge 步（回归 RED，solo 复跑也 RED，2/2 确定）：
  读 submenu targets（hover 展开 'Merge with' 子菜单）后
  `close_entry_menu`（WM_CANCELMODE）不生效——mp4 帧显示菜单一直开着，
  后续 re-open 的真实点击全打在悬浮菜单上，`wait_menu_popup` 5s 超时
  → "options menu did not open" ×3。
- **修法**：菜单模态循环只认真实输入（m3b 先例）——真实 **ESC ×2**
  （关子菜单 + 关主菜单）再 close_entry_menu 兜底；merge 重试环每次
  尝试前也补一发 ESC。修复后 solo GREEN 且 35 例回归全绿。
- **通用化**：任何"hover 展开过子菜单"的菜单，关闭一律先真实 ESC。


## 18. 0903 补充：relay/提权/PS Direct 边界五坑一约定（夜间批次事故链）

### 18.1 UAC 安全桌面无法穿透远控层
- **现象**：`Start-Process -Verb RunAs` 两次瞬时报 "operation was
  canceled by the user"；Appinfo Running、EnableLUA=1、Consent=5 全正常
  ——弹窗在安全桌面渲染，用户态远控（GameViewer 类）看不到也点不到，
  consent 直接取消。
- **修法**：一次性动作到物理控制台点 UAC；长期方案 = 提权计划任务
  （OrcaRelayWatchdog，RUNLEVEL HIGHEST + logon/15min 双触发器）。注册
  动作本身可经**已提权的 relay** 完成，不需要新的 UAC。
- **通用化**：远控环境里一切"弹窗式提权"都不可依赖；要自愈就注册任务。

### 18.2 powershell -File 位置绑定怪癖（string[] 只吃第一个）
- **现象**：`powershell -File hv_go.ps1 m3j m3k m3l m3m m3n` 只把 m3j
  绑进 `[string[]]$Cases`，其余静默落入 `$args`（交互式
  `& script.ps1 a b c` 才全量绑定）→ "launching suite: 1 cases"，
  36 例批次实际只跑了 1 例。
- **修法**：`$Cases = @($Cases + @($args)) | Where-Object { $_ }`。
- **通用化**：-File 与会话内调用绑定语义不同，多值参数一律显式合并
  $args，并让入口把实际计数打进日志。

### 18.3 PS Direct 会话拆解挂死 → relay 守护连坐；掉权限则静默空输出
- **现象**：守护经 Invoke-Expression 同步执行含 `Invoke-Command
  -VMName` 的命令，客机侧工作已完成，宿主侧调用不返回——守护卡死
  数小时，通道整个失效（RUN 头无 DONE，09-02 夜 21:43 实锤）。
- **相关现象**：守护掉成 medium 完整性时（误以非提权重启），PS Direct
  权限报错在守护的 Out-String 捕获里渲染为**空**——通道"成功返回但
  零输出"，极具迷惑性。
- **修法**：launch 类长事务一律 detached（hv_go_detached.ps1 以隐藏子
  进程跑 hv_go，输出重定向 artifacts\，守护 2s 释放）；守护必须提权。
- **通用化**：可能长时间不返回的 PS Direct 调用禁止在守护进程内同步
  执行；PS Direct 异常静默先查守护完整性级别。

### 18.4 冷启动首批 GUI 交互丢点击（WM_LBUTTONUP 超时）
- **现象**：客机空闲数小时后的首批用例，`SendMessageTimeoutW
  (msg=0x202)` 投递超时，首个交互断言（切 Manual / Auto 门控 / 匹配）
  失败并连锁。36 例恰好前 5 例 RED、第 6 例起 31 连绿；失败例热重跑
  5/5 GREEN——不是 SUT 回归，是会话冷启动。
- **修法**：full run 正式批前丢弃式预热第一例（hv_go 自动注入
  `$warmupCode` 片段，日志 `*.log.warmup`，不计判定）。
- **通用化**：长 idle 后的交互失败先重跑一次再定性；冷启动预热进
  批次协议而非人肉记忆。

### 18.5 PS Direct 的 DateTime 按目标旧时区反序列化
- **现象**：宿主 `Get-Date` 传给客机 `Set-Date`，参数绑定发生在目标
  `Set-TimeZone` 之前——值按客机**旧时区**（Pacific）转换，墙钟又设
  错一次。客机时钟差 14.7h 的根因即 TZ=Pacific 且无时间同步。
- **修法**：传字符串 `yyyy-MM-dd HH:mm:ss`，目标侧
  `[datetime]::ParseExact` 后再 `Set-Date`；先改 TZ 后对钟。时区修正
  后 `vmictimesync` 会持续保持。
- **通用化**：跨 PS Direct 传时间一律字符串显式格式，不传 DateTime。

### 18.6 约定：relay 执行的脚本禁止 exit/return
- 守护用 `Invoke-Expression` 在**自身 runspace** 执行 relay_cmd 内容：
  脚本里的 `exit` 会杀死守护进程，`return` 会中断 relay.ps1 主循环
  （alive 停止更新，等效死亡）。所有可能经 relay 调用的脚本
  （hv_harvest / hv_go_detached / register_relay_watchdog 等）一律以
  自然结束收尾；需要"提前结束"用 if/else 结构化。`exit` 只允许出现
  在 `-File` 子进程形态（relay_watchdog 即如此）。

### 18.7 PS Direct 进程的桌面指标是无桌面默认值（GUI 门禁会误中）
- **现象**：经 `Invoke-Command -VMName` 直跑的进程不在交互桌面会话内，
  `GetSystemMetrics` 返回 1024x768 默认值——分辨率/DPI 类 RIG 门禁在该
  形态下必炸（09-03 夜 pytest 壳首跑实锤）；同一命令放进 INTERACTIVE
  计划任务（或控制台手动）则返回真实 1920x1080。
- **修法**：GUI/桌面相关的检查与用例，经 PS Direct 验证时一律走
  INTERACTIVE 计划任务通道（hv_go 的 suite 任务同款），不要直跑。
- **通用化**：PS Direct = "客机服务上下文"，不是"客机桌面会话"。

### 18.8 relay 守护的 Invoke-Expression 是宿主上下文（不带包装 = 查的是宿主）
- **现象**：relay 守护把命令字符串在**宿主**自己的 runspace 里
  Invoke-Expression——命令里不显式包 `Invoke-Command -VMName ...` 就根本
  没到客机。宿主上恰好存在同形路径的陈迹（`C:\coil\run_suite.ps1` 是
  08-30 老模板、`C:\coil\orca-blackbox\artifacts` 为空、没有 suite 计划
  任务），查出来全是"文件消失了/任务没了"的假象（09-03 下午定性 22 RED
  时实际发生：三次"客机状态消失"全是查了宿主）。判别信号：任务列表里
  冒出 `OrcaRelayWatchdog` = 查的是宿主。
- **修法**：凡经 relay 的客机查询/操作，命令体一律显式包
  `Invoke-Command -VMName ... -Credential ... -ScriptBlock { ... }`（轮询、
  harvest 类脚本内部已自带包装）。relay 侧脚本要用 Write-Output 回传——
  守护只捕获管道输出，Write-Host（信息流）是空的。
- **通用化**：relay 通道 ≠ 客机；它是"宿主执行器"，客机是包装出来的。
  两者对同一路径各自有状态，排查时先确认自己在哪一侧。

## 19. 0903 补充：在线预设包更新弹窗会整批毒杀（22 RED 实录）

- **现象**：Orca 启动时在线检查预设包，服务端推出新包（2.2.56.2，腔温
  gcode 修复）后，启动路径弹模态框 "A new configuration package is
  available. Do you want to install it?"。框一在，交互类断言成片倒塌：
  topbar 模板找不到（被遮挡）、dropdown 8 次点不开、model selected: FAIL、
  确认对话框不驱动——而被动视觉断言（multicolor project loads）照常绿。
  09-03 全量 36 例 PASS=14 FAIL=22，-OnlyFailed 热重跑 PASS=1 FAIL=21
  （确定性）；前一晚同 commit 基线 31 绿——劣化完全来自这个弹窗。
  m4e 失败帧已存 `artifacts/m4e_fail_frame.jpg`。
- **判别**：散布的 GREEN（谁的启动没撞上弹窗谁过）+ 交互断言死、视觉
  断言活 + SUT/exe 与 commit 未变 = 环境级新变量。抓用例失败现场帧
  （artifacts\shots\<case>\ 经 base64 拉 JPEG）一步定案。
- **修法（已实施 ③，09-03 傍晚）**：启动序列确定性关弹窗——
  `harness/launcher.py` 的 `sweep_boot_blockers()` 在 launch() 启动窗内
  （demote 之后、用例交互之前，默认 15s）按**窗口标题**匹配并 WM_CLOSE
  （wx 模态框 close=Cancel）：`Configuration update`（MsgUpdateConfig）
  + `Snapmaker Orca Update`（MsgUpdateSlic3r）；强制升级框按构造排除
  （任意按钮会退 app）。locale 钉 en_US 由 seed conf 保证；
  `session.blockers` 留痕。验证：合成 #32770 同名对话框双相判别
  （`runner/blocker_sweep_check.py`，无关标题存活 + 同名标题被关）双
  PASS；全量 36 例复跑 **PASS=36 FAIL=0**（同日 14:40 为 14/22、热重跑
  1/21）。boot_probe 的 census 相传 `dismiss_blockers=False`（要看原始
  boot）。残余注意：sweep 窗 15s 是拍脑袋值，若未来弹窗出现晚于它，
  批次会再次中毒——case 日志里没有 `[launcher] blocker dismissed` 却
  有遮挡症状时，先加大 `blocker_sweep_s`。
- **未采用的候选**：① 客机网络隔离/hosts 屏蔽更新端点（更彻底但动
  客机全局状态）；② datadir conf 关更新检查——`profile.py` 的
  `conf_extra` knob（f562284）已具备能力，且 `orca_upgrade_url` 键
  可路由 app 版本检查（AppConfig::get_version_upgrade_url），但实测
  localhost feed 未触发弹窗（fetch 无证据，AppConfig::get 段落行为
  未定），配置包弹窗走 bambulab preset 链无法 conf 合成——两条线都
  留给 census（boot_probe）后续实锤。
- **通用化**：任何带外网的项目，"服务端推新"是回归基线的隐藏变量；
  批次劣化先查弹窗/托盘/更新类覆盖物，再怀疑代码。

### 19.1 census v2 裁决（09-03 夜，boot_probe 全部 5 相跑通）

修复③实施后跑 boot_probe census v2（watcher 分类豁免 + 弹窗全程跟踪 +
feed 请求日志 + 真实弹窗 WM_CLOSE 实测），逐条收敛 §19 的残余未知：

- **conf 段落根因（v1"未证明"的真因）**：`AppConfig::get(key)` 只读
  **"app" 段**（AppConfig.hpp：get(key) → get("app", key)）。v1 把
  `orca_upgrade_url` 写在 conf JSON **顶层** = 一个假 section → app 静默
  回退真 feed URL → localhost 无请求、无弹窗。改放 `{"app": {...}}` 后
  phase b/f 的 localhost feed **立刻收到请求**（feed 日志 1 次/相）。
- **Setup Wizard 是模态链阻塞器，且不"自愈"**：空种子 boot 每相 t=2s 弹
  #32770 'Setup Wizard'（820×660），实测**持续 ≥150s 不自行关闭**
  （推翻此前"~10s 自关"假设）；它模态阻塞 post-init 启动链
  （config_wizard_startup → preset sync → check_new_version_sf），弹窗
  在时这些全不执行（phase b 弹窗在 150s 内 0 次 feed 请求实证）。census
  在 8s 宽限后 WM_CLOSE 向导（m3 驱动同款路径；close 后 app_alive=True
  逐相记录）。**sweep 不碰向导**（m5 relocate 派的告诫：部分路径 close
  会退出 app；回归用例各自 relocate/无视它）。向导在大部分空种子 boot
  常驻 → 那些 boot 的链永远不跑 → 无配置弹窗 → 14:40 部分用例因此"侥幸"
  绿的机制也在此。
  **0904 更新**：本 build 上 WM_CLOSE 向导已多通道证实 app-safe（census v2
  五相 + uia_probe --wizard 五轮 + close 后链解锁复现 t=15s 配置弹窗并被同
  窗口 sweep 接住，UIA_EVAL §七）。sweep 增 **opt-in** 的 `dismiss_wizard`
  （类 #32770 + 标题含 wizard；默认 False 保持 census/probe 原始 boot），
  case 正式通道在 `m3_common.boot_session` 翻 True——空 boot 用例从"各自
  relocate/侥幸"变为确定性处置；fixture boot 本就不弹向导（no-op）。
  blocker_sweep_check 增 wizard-off/on 两相钉死 opt-in 语义（5/5 PASS）。
  **0904 回归实测（85aa506 后首轮 36 例 PASS=36 FAIL=0）**：sweep 窗内
  dismiss 打印 0/36 boots，m5 家族 relocate=True×8——seeded boot 的向导
  **晚于 sweep 窗出现**（探针 boot 实测 ~t40-50s，census 的 t=2s 是空种子
  行为），晚现向导仍由 m5 relocate 兜底。即 dismiss_wizard 当前实际覆盖
  census 式早现向导；seeded case boot 的晚现机制存疑待查。
- **修法②（conf stub）盖章为完整双保险，且推翻"预设链不可 conf"旧判**：
  c 相把三段键（app 下）指向拒连端口 → **零弹窗**；同一晚 a/b/f/e 各相
  服务端仍在推 2.2.56.2（'Configuration update' 每相 ~t=15-16s 复现，
  OCR 同 14:40 文案）。e 相（只 stub orca_upgrade_url）配置弹窗照出 →
  配置包检查走 `get_preset_upgrade_url()`（读 app.profile_upgrade_url），
  **并非不可 conf 路由**——§19 上文"bambulab 预设链无法 conf 合成/无法
  conf 修复"的旧判来自 v1 的段落放错实验，作废。三个弹窗族全 conf 可控：
  app 版本/强制升级（orca_upgrade_url）、配置包（profile_upgrade_url）、
  flutter web 资源（flutter_upgrade_url）。sweep 仍保留（纵深防御）。
- **弹窗出现时刻实测 + blocker_sweep_s 回填**（主窗发现后秒数；向导于
  t=10s 被 census 关闭为前提）：配置弹窗 **t=15s**（真 feed，链解锁后
  ~5s）、版本弹窗 t=12s（localhost）、强制弹窗 t=12s。census 的向导关闭
  时刻（10s）晚于任何驱动（多数用例根本不关向导 → 链不跑 → 无弹窗），
  故 15s 拍脑袋值恰好压在配置弹窗实测值的边缘 → 默认提到 **25s**
  （向导最晚 ~19s 关闭仍兜得住；代价 +10s/例 ≈ +6 分钟/36 例批次）。
- **sweep 标题表实锤补齐**：真版本弹窗标题 = **'New version of Snapmaker
  Orca'**（UpdateVersionDialog/ReleaseNote.cpp）；'Snapmaker Orca Update'
  （MsgUpdateSlic3r）在本 build 是**死代码**（全树无实例化点），保留仅为
  对称。census b 相 close_test：真 UpdateVersionDialog WM_CLOSE 后
  app_alive=True → 加入 BLOCKER_TITLES；blocker_sweep_check 扩成三相
  （ignore/dismiss/version）全 PASS。强制框标题 'Snapmaker Orca needs an
  update'（DownloadDialog，EVT_ENTER_FORCE_UPGRADE）按构造不匹配——任意
  按钮退出 app，永远不得入表。
- census v2 报告/事件/帧在客机 `C:\coil\boot_probe_report.txt` /
  `boot_probe_events.json` / `boot_probe_shots\`（ASCII 报告可 relay 直拉）。


## 20. 0908 补充：m7 主流程批次（relay/PS Direct/右键菜单/任务计划）

- **ScheduledTask ExecutionTimeLimit 变 PT2M**：`New-ScheduledTaskSettingsSet
  -ExecutionTimeLimit (New-TimeSpan -Seconds N)` 注册后实测落成 PT2M（每个
  diagtask 实例 2 分钟被 0x41306 终止、Out-File 0 字节——症状极易误判为
  "GUI 会话坏了"）。`Register-ScheduledTask -Settings $st` 也复现过；
  **注册后再 `Set-ScheduledTask -TaskName X -Settings $st`（-Hours 形式）
  才稳**。guest_run.ps1 已固化该两步。
- **relay 守护 Invoke-Expression 宿主插值**：`powershell -Command "...{ $c=... }"`
  里的 `$var` 在宿主守护会话就被展开成空串（客机收不到）——凡经 relay 的
  PS Direct 命令，`$` 一律写成反引号+`$`（runner/fetch_file.py ic() 已固化）。
- **PowerShell 没有 r'' 原始字符串**：`r'C:/x'` 被解析成裸词 r 拼接，客机
  收到 `rC:/x` → 文件不存在 → 静默空输出。
- **PS 5.1 不能对赋值表达式取索引**：`($c = Get-Content f)[0..399]` 语法错；
  必须 `$c = Get-Content f; $c[0..399]`。
- **GetMenuItemRect 的 hWnd=NULL 在客机失败**（菜单开着也返回 0）——传弹出
  菜单自身的 #32768 窗口句柄才可靠；嵌套子菜单要用
  `topbar_util.wait_submenu(pid, known)`（wait_menu_popup 会把父菜单也列进
  来，取 subs[-1] 实测拿错过父菜单）。
- **Plater 右键菜单结构**（0908 dev build 实测）：空板 = Add Primitive /
  Add Handy models / Add Models / Show Labels；对象 = Clone/Simplify/
  Mesh boolean/Center/Drop/Split/Mirror/Delete/Add Part…/Printable/
  Flush Options/Reload/Replace STL/Export STL/Convert…/Change Filament。
  行点击 = GetMenuItemRect + 真实点击；行未命中必须显式失败（m7b 首版曾
  因 fall-through 到 success_fn 误报成功）。
- **gizmo 工具栏**（maximized 1920x1032, dpi96）：图标行 client y≈65–105
  （中心 ~84），x≈690–1700，pitch≈45px；Move/Rotate/Scale/Cut/Flatten/
  Supports/Seam/Fuzzy/ColorPaint/Measure/Assemble/BrimEars 需**选中模型**
  才启用（灰色也出 tooltip）。tooltip 悬停 OCR 断言用 ≥4 字符阈值（m4e 的
  6 字符阈值会漏 Move/Rotate 短词）。
- **Prusa.stl 到板信号只有 ~0.35% 彩色占比**（空板 0.06%）——混色夹具
  校准的 0.6% MODEL_COLORED_THRESHOLD 对小单色模型过严，小模型导入用
  0.25% + blob 双信号。
- **File > Import 是子菜单**（STL/3MF/ZIP 在第二层）：对子菜单标题发
  WM_COMMAND 是 no-op，须先真实进入子菜单再对行分发。
- **fetch 通道二进制不可靠**：fetch_mp4 单发 base64 两次损坏（420KB/76KB
  截断）——文件拉取用 runner/fetch_file.py（MIME 行分块 + MD5 校验）。
- **launcher 的 --datadir 必须绝对路径**：launcher 以 exe 目录为子进程
  cwd，相对 datadir 落到 exe 旁 → 种子 conf 不生效 → 首启向导模态阻塞
  主窗口 → find_main_window 90s 超时。

---

## 21. 1012 补充：2.4.1 耗材选择框收敛（三条根因 + 三个环境坑）

### 21.1 探针的控制台窗口会吞掉真实点击（"控件没反应"的假象）
- **现象**：scheduled task 里 `cmd /c python script.py > log` 起的 Windows
  Terminal 窗口盖在 app 上；`WindowFromPoint` 在槽位行的**每个点**都返回
  `'CASCADIA_HOSTING_WINDOW_CLASS' '...cmd.exe'`——chip 点 3 次"毫无反应"，
  酷似 2.4.1 改了取色入口的语义（前一会话的 probe 结论即栽在这里）。
- **修法**：探针一律 `C:\Python311\pythonw.exe`（无控制台）+ 自写日志
  （pythonw 下 `sys.stdout is None`，`sys.stdout.reconfigure(...)` 会
  AttributeError 秒崩——探针要 `if sys.stdout is not None:` 守卫）。
- **通用化**：任何"点击没反应"的现场先 `WindowFromPoint` + 比对 pid，再怀疑
  SUT。批量套件不受影响（app 由用例后启动、占前台），交互式探针必受影响。

### 21.2 子窗口 rect 已是屏幕坐标——不要再 client_to_screen
- **现象**：m8b `#48 dialog opens: FAIL (no popup)` 的**根因**：chip 的 rect 来自
  子窗口 `GetWindowRect`（屏幕坐标），代码又走了一次 `client_to_screen()`
  （最大化窗口 client 原点 ≈ (+8,+31)）→ 点落到 chip 下方 20px 的 combo 上，
  什么都不弹。2.4.0 时代窗口几何不同所以侥幸没炸。
- **修法**：直接用 rect。实测 chip 首点即开官方色卡（`#32770` kids =
  'Mint Lemonade' / 'sku 34205' / 'Official Filaments'）。
- **通用化**：`export_util._children_texts()` 的 rect 是屏幕坐标，凡再转换处
  都要复查。

### 21.3 2.4.1 双栏选择框：**hover 即切换右栏**
- **现象**：弹层开在鼠标落点，光标恰好压在 'Generic' 行上 → 右栏显示 Generic
  的列表。前一会话据此判定"Snapmaker 分支里没有 PLA Rainbow、需人工在
  耗材管理里勾选"——**结论是错的**（扫错了分支）。
- **事实（10-12 实测）**：Snapmaker 二级列表**包含 `PLA Rainbow`**
  （pscan2_Snapmaker_hover.png：置顶 7 项 + 字典序，PLA Rainbow 在 PLA Glow 与
  PLA Silk 之间）；置顶 8 项里的 `PLA Full Spectrum` 反而不在列表里。
  **不需要任何人工勾选**→ m8b #55 端到端 GREEN。
- **修法**：点厂商行前先 hover（SetCursorPos 停在行上）再点击；右栏内容变了
  才算切换成功。

### 21.4 右栏滚动必须小步（-1 档）且每档 OCR，且先回顶
- **现象**：一次 -3 档跨 ~7 行，目标行落在两屏之间被跳过（'PLA Rainbow' 就是
  这样漏的）；另外弹层开在"回显行"处，目标可能在当前视口**上方**。
- **修法**：`m8_common._picker_scan_for()`：先回顶（+3 × 24 次，列表到顶即夹住）
  → 再 -1 档逐步向下，每档 OCR + 匹配。列表很短（Snapmaker 二级 ≈ 24 项 ≈ 3 屏）。

### 21.5 同厂商内切换不要点厂商行
- **现象**：m8d 的 `Generic ABS → Generic PC`：当前值已属于 Generic，厂商行正是
  "当前展开分支"（高亮渲染）→ OCR 读不到该行；插值坐标又可能落在回显行上，
  一点把弹层点关（日志 `candidate无效（pane=False）`）。
- **修法**：`combo_text().startswith(vendor)` 时**跳过**厂商点击，直接扫右栏
  （弹层打开时右栏展示的就是当前值的分支）。

### 21.6 2.4.1 耗材相关配置的实测事实（供后续会话）
- `filament_allow_list.json`（2.4.1 新增，app resources + datadir/system 各一份，
  由 app 自己 stage）只含 **`high_flow` 限制 + `filament_order` 置顶顺序**，
  **不是**"可选材料白名单"。
- 用户预设的父预设 `Snapmaker PLA SnapSpeed @U1` 在 2.4.1 **存在**（app resources
  + datadir 都有），datadir 日志无预设加载错误 → "继承父预设缺失"假设**不成立**；
  用户预设（`- STD-TEST` 等）为何不出现在耗材双栏框里**仍未定论**。
- `Add/Remove filament` 行开的是 **WebView 对话框**（`#32770` kids = wxWebView /
  'loading' / Chrome Legacy Window）——产品文档的「混色品牌 → 配置可选择的材料」
  应该在里面（HTML，回归用例不碰；探针可看）。

### 21.7 relay 守护只认 `token|脚本路径`——push_verify/fetch_file 是哑的
- **现象**：`runner/push_verify.py` / `runner/fetch_file.py`（写 **裸命令** 进
  relay_cmd.txt）在 10-12 全部超时；relay_history 里根本没有 RUN 记录。
  当前守护是 `C:\coil\vm_setup\relay.ps1`（`$parts = $line -split '\|', 2`，
  非 `token|path` 形式的命令直接 `continue` 丢弃）。
- **修法（10-12 起）**：
  - 宿主→客机文件：**base64 塞进 job .ps1**（`[Convert]::ToBase64String` 传参 +
    客机 `[IO.File]::WriteAllBytes`），模板 `jobs/j360_ship_rerun.ps1`；
  - 客机→宿主文件：**同一个 job 里**把文件读成 base64 **字符串**分块回传，
    在宿主侧（守护就是宿主提权进程）直接 `[IO.File]::WriteAllBytes` 落地
    （`jobs/j382_pull_shots.ps1` / `j413_*` 模板）。PS Direct 的 byte[] 返回值
    仍不可靠，但**字符串**分块可靠（本次 8 个文件全部 MD5-MATCH）。
- **通用化**：动 relay 前先看 `relay_history.txt` 最后几条是不是自己的 token；
  通道"成功但零输出"先怀疑命令形式不对（守护把裸命令当垃圾丢掉）。

### 21.8 job .ps1 里有中文注释必须带 UTF-8 BOM，否则 PS 5.1 解析崩
- **现象**：新写的 job 脚本（中文注释、无 BOM）经 relay `powershell -File` 执行，
  报 `表达式或语句中包含意外的标记"}"`（行号指向成对的 `} -ArgumentList ...`）——
  PS 5.1 按系统 ANSI（GBK）解码无 BOM 的 UTF-8，中文注释把解码游标带偏、
  吞掉后续 ASCII 引号/括号。
- **修法**：job 脚本一律 `encoding='utf-8-sig'` 写（或干脆只用 ASCII 注释）。
  本次两条 j380/j386 的解析事故都源于此。

### 21.9 本轮结论的复跑入口（探针索引，都在 `diag/`）

| § | 复跑入口 |
|---|---|
| 21.1 控制台吞点击 / pythonw | `probe_241_chip2.py`（打印 WindowFromPoint + pid，一眼看出点落在谁身上） |
| 21.2 子窗口 rect = 屏幕坐标 | `probe_241_chip.py`（chip 连点重试；对照 slot1 原生取色器 vs slot2 官方色卡）+ `probe_241_slotrow.py`（槽位行控件全枚举） |
| 21.3 hover 即切分支 / Rainbow 在不在 | `probe_241_picker_scan.py`（首轮扫到 Generic 分支）、`probe_241_picker_scan2.py`（hover 切 Snapmaker，**Rainbow 命中**） |
| 21.4 右栏小步滚动 | `probe_241_picker_scan2.py`（-1 档逐档 OCR 打印） |
| 21.5 同厂商不点厂商行 | `probe_241_picker_scan2.py` + m8d 用例日志（`candidate无效（pane=False）`） |
| 21.6 配置事实（用户组/截断行/WebView） | `probe_241_userpreset_seeded.py`（槽位是用户预设时左栏出 `------ User presets ------ → Custom »`）、`probe_241_usergroup.py`（hover tooltip 才是全名）、`probe_241_slotrow.py`（`Add/Remove filament` = WebView 对话框） |
| 切片确认框 `Custom Filament Grouping` | `probe_241_hfslice.py` |
| gizmo 网格空行 / rotate 聚焦读不出 | `probe_241_gizmo.py`（输入通道逐条试）、`probe_241_rotate.py`（逐格试）、`analyze_gizmo_ocr.py`（**离线**复算 OCR 行盒，不用起 app） |
| 环境体检 | `check_241_launch.py`（进程/窗口/截图）、`diag_241_uicheck.py`（菜单与工具条提示仍在，排除"界面被删"） |
| 两级原语冒烟（上一会话） | `probe_241_switch.py`；用户组探索 `probe_241_picker10.py`；已过时的编辑器入口 `probe_241_editor_preset.py` |

（上一会话的 `probe_241_picker1..9` / `rainbow_enable1..4` / `material_pick1..2` 是迭代试错链，
结论已被上表覆盖或推翻——**按用户 10-12 决定未入库**，避免仓库里留死路。）

### 21.10 飞书写回需要 lark-cli 的**用户身份** token（bot 身份会被拒）
- **现象**：`tools/feishu_writeback.py --apply` 报 `app_scope_not_applied / 99991672
  has not applied for the required scope(s): base:record:update`，看起来像"应用没申请权限"——
  实际 `lark-cli auth scopes` 里该 scope 在（app 层面没问题），真因是
  `lark-cli auth status` 显示 **user 身份 token 缺失**（只剩 bot），工具于是用 bot 身份发请求被拒。
- **修法**：本人在**宿主**跑一次 Device Flow：`lark-cli auth login --domain base`
  （`--domain base` 把授权范围收窄到多维表格；token 落系统钥匙串）。
  自检：`lark-cli auth status` 要 `user: ready`、`lark-cli auth check --scope base:record:update`
  要 `granted`。本轮实测：登录后同一条 `--apply` 62 条记录一次写入并读回校验通过。
- **通用化**：任何"权限被拒"先分三层看——app 是否有该 scope（`auth scopes`）、
  当前身份是否有 token（`auth status`）、token 是否有该 scope（`auth check`）。
  用户 token 有效期约 2h（refresh ~7 天），长时间不写回的会话要重新登录。

### 21.11 切片按钮的"标准/自定义模式"悬停框在 2.4.1 消失了（A/B 实证）

- **2.4.0 实测**（`probe_241_hover_slice.py --exe ...V2.4.0...`）：喷嘴高流量/标准混用时，
  **悬停**「Slice plate」按钮就弹一个 `wxWindowNR 'panel'`（305×140，自绘、**子控件无文本**，
  位置贴在按钮下方 (1464,65)-(1769,205)），内容是模式单选：
  - ● **Standard Mode** — *Prioritize print quality*（默认选中）
  - ○ **Custom Mode** — *Manually assign filaments to nozzles*
- **2.4.1 实测**（同探针、同状态：空盘 + cube + HF-TEST 过程预设 + flow=High Flow）：
  - **悬停 → 什么都不弹**（3.5s 内无任何新 toplevel，移开再悬停也无）；
  - **点击 → 直接弹 `Custom Filament Grouping`**（'Slicing will follow the nozzle
    assignment below:' / Standard Nozzle / High Flow Nozzle / Cancel / Confirm），
    Confirm 后才开始切片。
- **判读**：2.4.1 把"模式选择"从**悬停态**变成了**切片时的分组确认**——即默认走 Custom
  Mode 的确认路径；旧版那个悬停框（含"Standard Mode"入口）在本 build 上**没有等价入口**
  （至少切片按钮处没有）。取证帧 `artifacts/phover_panel_240.jpg`（裁自 2.4.0 截图）。
- **对用例的影响**：m8f/m8g 在 2.4.1 上点 Slice 必须答分组框（已实现
  `m7_common.confirm_filament_grouping`）；2.4.0 上同一步骤**不会**有框（A/B 日志里
  2.4.0 点击后无任何 #32770），所以旧版路径不需要答框。
- **复跑入口**：`diag/probe_241_hover_slice.py`（默认 2.4.1；`--exe <2.4.0 路径> --datadir <另一目录>`
  做 2.4.0 对照；日志按版本分开写 `phover241.log` / `phover240.log`）。

### 21.12 薄片对象的选中/右键：`+22px` 配方会把点击送到床上（10-16，#152 s4）

- **现象**：m8x_152 的 s4 里"耗材合并"整段失败在 `no context menu`。
- **根因链**（三处，全部实测）：
  1. `m7.select_model` / `m7.open_context_menu` 固定点 **质心 +22px**（为了躲开对象上方的
     名字标签）。本链夹具 `Prusa.stl` 是 **91.5 × 19.5 × 3.0 mm 的薄片**，屏幕上只有
     ~15px 高 → +22 落到**床面**，右键弹的是**盘子菜单**
     （`Select All / Delete All / … / Add Primitive`），不带 Change Filament 行。
  2. 选中判据用的是 `tooltip_text(session, rot_x, BAR_Y)`——**没有 tooltip 时**它 OCR 到的是
     工具栏按钮自身的标签（`'we Vv Rotate [R]'`），不含 `select` → **空床点击也判"已选中"**。
     本轮因此拿到了两个假 PASS（s4 的"模型选中"）。
  3. 兜底里把"两个点连点 + 只轮询一次"写成了**缩进错位**：两次右键（质心、质心+22）之后
     才轮询，第二个右键已把第一个菜单关掉 → 实际只测到了 +22 那个点。
- **可观测面（新口径）**：选中对象时**右下角出现 "Object name: … / Size / Volume /
  Triangles" 信息面板**（`m7.object_info_text` OCR）；ESC 取消选中后消失。
  `m7.select_object_strict` = 点质心 + (0,0)/(0,-8)/(0,+8) 小步，用该面板判成功并返回可用点。
- **右键配方**（`tests/mainflow/m8x_152.py:right_click_object_menu`）：先把光标挪开工具栏 →
  **真实左键**（画布聚焦 + 选中，并用信息面板确认）+ **右键同一点** → 轮询 `#32768`
  （**每个点独立轮询**）→ 菜单里**必须有 `change filament` 才接受**，否则关掉换下一个点。
- **判读**：这不是 app 侧 bug，是台架拿"大对象"经验套到薄片上的适配问题；薄片场景
  （#152 的 Prusa 徽标件）从此有可用配方。

### 21.13 2.4.1 的 Change Filament 子菜单：**行标签会重名、勾选态读不到**（10-16）

- **重名**：4 个物理槽都用同款预设时，子菜单 4 行标签**完全相同**
  （`'Snapmaker PLA SnapSpeed @U1 - FLOW-TEST'` ×4），只有色块不同。
  `m7.click_menu_row` 按标签匹配 → **永远点到第一行**：想让对象用第 4 槽，结果仍停在首槽
  （合并前切片 gcode 用量 `[1]` 而非 `[4]`，一度被误读成"app 不同步"）。
  → 改用按索引点：`click_menu_index`（`m7._menu_item_rect` 取行矩形 + 真实点击）。
- **勾选态**：子菜单行是**自绘色块**，`GetMenuState(hmenu, i, MF_BYPOSITION)` 的 `MF_CHECKED`
  在"赋值前后"都读到 `checked=[]`，**勾选不是可观测面**（注意 `-1 & 0x8 == 0x8`，读失败
  会被误判成"勾选了一行"，必须显式判 `-1`）。
- **替代口径（两条独立侧证互证）**：
  - **对象主色**：`object_color(session, pt)` = 点周围彩色像素的 BGR **中位数**（对选中高亮框、
    坐标轴箭头这类细线污染免疫）；与**槽位色板**（`m8.slot_swatch_rgb`，色板背景就是耗材色）
    做最近邻分类，即可回读"对象在用哪根丝"。
  - **gcode 用量**：`m8.used_filaments` 的非零下标。
- **2.4.1 实测行为**：对象指到第 4 槽后主色变 `[59,55,158]`（红，槽 4 色板 `[62,55,239]`）；
  并把掉第 4 槽 → 槽位 4→3、子菜单行 4→3、**对象主色回到槽 1** `[117,123,60]`，
  同时 gcode 用量 `[1]` —— 即**删除在用的那根丝时，对象被重映射到第一个存活槽**，
  两条侧证完全一致（这也顺带证明"合并会同步模型耗材丝"）。

### 21.14 多进程用例的父进程只回显子进程 stdout 最后 40 行（排查陷阱）

- `tests/mainflow/m8x_152.py` 的父进程 `print(...[-40:])` 只回显尾部 40 行，s4 段里
  `s4 model arrives` / `scale panel after ESC x2` 这些**失败步骤自己的打印会被挤掉**，
  导致看日志时误判"代码没跑/是旧版"（10-16 实测，白查了一轮 md5）。
- **修法**：每个会话的**完整 stdout+stderr 落盘** `artifacts/m8x_152_<tag>.log`（已实现），
  父进程仍回显尾部 40 行给 `regress_*.log`。
- **顺带**：`--only s4` 只跑单会话用于快速迭代，且**故意判 RED**
  （`partial run (--only s4): FAIL (debug run)`），防止局部结果被当成整用例 GREEN。

### 21.15 导出 gcode 的**假 PASS**：`wait_file` 只看"文件存在"，旧文件让空跑秒过（10-19）

- **现象**：m8x_152 报 `gcode exported: PASS`，但磁盘上最新 gcode 还是三天前的文件；
  随后的"gcode 用量"读数自然也是旧文件的（把 `[1]` 当成"对象换丝不进切片"的证据，
  一度据此给测试方下了错误结论）。
- **根因**：`harness/export_util.py:wait_file` 只判 `exists() and size>0`，而目标路径
  在上一轮就跑过、文件一直在 → 导出对话框里 IDOK 超时（`SendMessageTimeoutW(msg=0x111)
  ... did not complete`，app 还在写/卡住）时，等待函数立刻返回 True。
- **修法**（已实装）：`export_gcode` 在打开保存对话框**之前** `out_path.unlink()`；
  成功 = 新文件出现且非空。修正后同一用例立刻读出 `used=[3]`（与三维视图的 3 号丝一致），
  说明"对象在用丝 → 切片丝号"是**通的**，之前的 `[1]` 纯属旧文件假象。
- **教训**：任何"等文件落盘"的断言都必须先清目标文件；否则用例在上一轮产物上静默通过。

### 21.16 2.4.1 的 gizmo 手柄（拖拽式移动/旋转/缩放）：可拖，但命中区与绘制像素不一致（10-19/20）

- **目的**：#156 要求"旋转/移动/缩放用鼠标拖拽"（#152 是输入值）。实测结论：
  **移动、缩放可以稳定做成拖拽；旋转可拖但不可稳定复现**。
- **能拖的证据**：
  - 移动：按住对象本体拖 → 面板位置数值 `100.00 → 154.77` ✓
  - 缩放：点住模型上的方块控制点（饱和红/绿/蓝）拖 → `Scale 100.00 → 83.35 / 129.57` ✓
  - 旋转：拖**蓝色箭头** → `Rotate Z 0.00 → 171.54`，同时热床投影 `view_delta` 仅 2.4%（= 视角没动）✓
- **不可稳定复现的原因**（三件事叠加）：
  1. **命中区 ≠ 绘制像素**：圆环上 8 个真实像素点拖下去全部无效（`view_delta` 0），
     包围盒角多数落在**床面**（一拖 = 相机环绕，`view_delta` 27~72%）；
     命中的两次分别在"激活后质心"+(+80,-15) 与 (+73,+6)，位置逐轮漂移。
  2. **激活 Rotate 会改变对象在屏幕上的位置**（实测 y 585 → 547~578 不等），
     用激活前的坐标算偏移会整体偏掉（一次 16 点扫掠因此全部落空）。
  3. **同一会话第二次打开 gizmo 面板会失聪**（2.4.1 已知），所以不能"先试拖拽、
     失败再退化输入值"——退化那次面板打不开（`rotate: panel closed — nothing to type into`）。
- **取舍**：#156 的旋转仍用输入值（唯一稳定通道），移动/缩放用拖拽（面板数值作证）。
  要把旋转拖拽做稳，需要**箭头模板的多尺度匹配标定**（把箭头锥截成模板图），
  属于独立任务；标定脚本雏形见 `diag/probe_241_rotate_drag.py`。
- **顺带**：拖拽必须走 OS 级输入（`m7_common.real_drag_screen`），消息级点击不产生
  拖拽语义；扫掠式尝试会产生大量 OCR（`panel_value`），客机内存紧张时会
  `pix_malloc fail`（tesseract OOM，重启客机即恢复）。

### 21.17 客机 DWM 崩溃风暴会硬杀整棵 INTERACTIVE 任务树（10-29/10-30，#187 s2）

- **现象**：`m8x_187` 两次整跑（10-29 21:24、10-30 16:10）都无声死在 s2：无 s2/s3
  json、`regress_*.log` 0 字节、suite 汇总 `RED rc=1073807364`（0x40010004，
  进程被硬终止）。客机事件日志在死亡时刻各有一波 **dwm.exe APPCRASH 连环**
  （10-29 21:39–21:40 十连崩；10-30 16:25–16:26 七连崩，udwm/dwmcore/dwmredir）。
  DWM 崩溃循环 → 交互会话重置 → 计划任务（INTERACTIVE）下的 python 父进程连同
  子进程、orca 全部被硬杀，stdout 管道缓冲随进程蒸发（所以日志 0 字节）。
  10-30 会话末用户还遇到"虚拟机点不动/关不了"——同一会话卡死的后续。
- **触发面**：两次都是 s2 陷在 `op_gizmo_field` 的打字重试循环 ~12 分钟时崩
  （存档帧标签 `L042_..._char--3--not-landed-yet--field-reads--0-00`）。触发根因
  是**全选两个旋转值不同的模型后 absolute 字段呈混合态**（读作 0-00），字符
  永远落不进去；长时间高频「打字+PrintWindow 截图」疑似是压垮 VM 合成 GPU 里
  DWM 的诱因（未做对照实验，但两天的崩溃时刻与循环起点精确吻合）。
- **修法/规避**（#187 已实装）：
  1. 业务侧：**多选模型不做 absolute 输入**——按 `object_info_text` 认名单选
     目标对象（方案 B+），字段单值后打字与 s1 同路，不再进死循环；
  2. 框架侧：多会话用例的父进程**必须接住 `subprocess.TimeoutExpired`**
     （记 FAIL 继续下一会话，否则一个会话超时连坐后面全部），json 在
     `session.close()` 之前落盘（close 挂起也不丢判定证据）；
  3. 环境侧：整跑前 DWM/会话状态可疑（连跑多轮后）就先重启客机再跑；
     死循环诱因（打字重试 + 高频截图）出现在 VM 里超过 ~10 分钟就要警惕。
- **教训**：客机上「整跑无声消失 + 日志 0 字节 + rc=0x40010004」= 先查事件日志
  `Application/1000` 里有没有 dwm APPCRASH 风暴，别先怪用例代码。

### 21.18 #187 s2 收尾两坑：同步 IDOK 吊死 + 推送时 VM 关机静默失败（10-30）

- **同步 IDOK 吊死**：`save_project_as` 用 `SendMessageW(dlg, WM_COMMAND, IDOK)`
  收尾——目标是**已存在的文件**时，Vista 保存对话框弹内联「是否替换」确认框，
  同步发送方**永远不返回**（驱动线程整个吊死；实测 s2 卡 10 分钟直到会话被杀）。
  新文件不会弹框所以 s1 无恙——同一函数两种命运。**修法**：已命名项目回写用
  「文件 → 保存项目」普通保存（静默写回，m8x_201 已验证路径），用文件 mtime
  变化判定完成；凡是 save-as 覆盖已有文件的目标，先 `unlink` 再存。
- **job 推送在 VM 关机时静默失败**：j654 的 `Invoke-Command -VMName` 推文件 +
  `-ErrorAction SilentlyContinue`——VM 关着时两步全吞，无 'shipped' 输出，
  hv_go 随后开机跑的还是**旧代码**。**判定法**：j654 输出必须有 `shipped xxx`
  两行，没有就是没推上；先开 VM 再推。
- **DWM 风暴签名补充**（§21.17 的第三例）：17:04 一波，仍是 s2 挂起后 ~12 分钟、
  存档器累计 ~2600 帧 PrintWindow 时引爆。修掉 s2 挂起后整跑 ~7 分钟（视频
  mtime 17:27/17:30/17:32），不再触雷。

### 21.19 开着的 gizmo 面板会抑制盘侧图标点击（11-06，#195 六轮取证）

- **现象**：盘侧工具栏图标（orient/arrange 一列）tooltip 正常显示，但
  SendInput 真实点击零效果——单击/双击/先选中对象都无效，3mf 矩阵零变化，
  极易误判为「产品缺陷」（#195 第 4 轮就误判了，用户实测手点有效才推翻）。
- **根因**：打字用的 rotate_verify（m8x_191 的自写变体）打开 Rotate 面板
  后**不关面板**（op_gizmo_field 会关，自写版漏了）→ 画布处于变换模式，
  盘侧图标点击被抑制。#194 点删除图标有效，是因为它的流程从未开过面板。
- **修法**：任何 gizmo 打字流程结束后，重新 find_slot 点一次把面板**关掉**
  （并可用 gizmo_row_boxes 复核已关），再操作盘侧图标。
- **连带教训**：判别探针的环境必须与用户手动路径一致（无面板）；被污染
  的 A/B 判别会产出自信但错误的「产品缺陷」结论——发缺陷报告前先找用户
  手动复现一遍（本次即靠用户实测纠正）。

### 21.20 2.4.1 涂色（Color Painting）黑盒驱动的六条硬约束（11-09/10，#193）

- **一色一会话**：同一个 app 会话里**第 2 笔涂色恒不落墨**（模型区像素差
  0.3–0.5，换瓦片/换方向/先激活画布均无效）。→ 两色拆两个会话，每会话
  只涂一笔（与 §21.16「一变换一进程」同源）。
- **涂色会话必须走「打开项目」**：新导入(import)后的首笔常不落墨
  （实测采样 Δ=0），而打开项目(open)后的首笔稳定落墨（Δ=114/210）。→
  结构固定为「s0 导入+另存基准 → s1/s2 打开项目各涂一笔」。
- **瓦片位置必须从像素检测**：6 个色瓦片时 ImGui 会**换行**，固定间距
  实测 2–6 号全读到白色背景（[238,238,238]）；真实间距 ~51px（不是 34）。
  `palette_tile_points()` 用连通块质心定位。
- **选色必须测色差，不能按序号**：4 个丝里 2 号与模型底色几乎同色
  （Δ=4），涂了也看不出、gcode 也不记丝号 → 读每个瓦片中心的 RGB，挑与
  参考色（s1=模型底色、s2=s1 已涂色）差异最大的那个。
- **目标点必须用 object-info 认证**：色块启发式会把 Prusa 长条（359px）
  当成模型 → 点候选点直到 info 报 `8000mm³`，用这个**证明在 cube 上**的
  点做锚（实测点 28px 的小 cube 也能稳定落墨）。
- **不要放大视图**：滚轮把 cube 放大到 138px 后首笔反而失效（diff 0.1）。
  小 cube（28px）+ ±8px 短笔划是可复现组合；单笔整框像素差会被稀释
  （1.4–2.7），**判据用采样点色差 Δ≥10**，整框差值只作证据行。
- 附带：cube20 纯几何体彩色占比仅 0.20–0.21%，`m8.wait_arrival` 的
  0.25% 门槛会误判 → 抛低饱和模型时自定义 0.15% + 双采样。

### 21.21 客机中文输入法在系统层拦截字母真实键（11-12，#207）

- **现象**：`Start PA` 字段真实键输入 `abc` 后回读恒为空；`keybd_event`
  字母键、`SendMessage(WM_CHAR)`、`SendInput(KEYEVENTF_UNICODE/VK_PACKET)`
  三条通道全部不落字，但 `END/BACKSPACE` 等非字母键正常、剪贴板 Ctrl+V
  正常。摘掉 Edit 或对话框顶层窗口的 IME 上下文（本就 `None`）、发
  `WM_INPUTLANGCHANGEREQUEST` 切 en-US 均无效（probe_242_pa207d/e/f）。
- **结论**：这是客机中文输入法/TSF 在系统输入层消费字母键，不是产品
  字段过滤；真人点按键盘不受影响（用户手工验证）。
- **用例处理**：需要"字段里可见地出现非数字文本"的校验步骤，改用
  `SendMessage(edit, EM_REPLACESEL, 1, text)` 写入并在用例里回读断言
  （视频可见、提交校验路径不变）；**不要**继续在真实字母键上重试浪费
  会话。其余输入仍优先真实通道（剪贴板粘贴已验证可用）。

### 21.22 PA 校准对话框的复选框是 owner-drawn：BM_GETCHECK 恒 0（11-13，#221/#222）

- `Print numbers` 的 Button 样式 `0x5a01100b` = **BS_OWNERDRAW**，
  `BM_GETCHECK`/`BM_CLICK`/`BM_SETCHECK` 全部无效（实测恒 0，强塞无效）。
- 只能截图判态，且两种勾选颜色不同：
  - 启用+勾选（PA Line）：青色方块 + 白勾，teal 像素 ≈130；
  - 禁用+勾选（PA Pattern/V 形）：**灰色勾**，teal=0、暗像素（gray<190）≈13；
  - 未勾选（PA Tower）：teal=0、dark=0。
- 判据：`checked = teal>=50 or dark>=5`；`enabled` 另读 IsWindowEnabled。
  probe_242_pa222b 三态实测 + 用户中文界面截图确认。

## 22. 1117 补充：macOS 移植（AX/面板/Vision/3mf 构造）

> 证据：`harness/platform/macos.py`、`tests/engine/macos_pilot/*`、
> `diag/macos_probe_*.py`；最近全量 `artifacts/mac/baseline_run23.log`
> （MACOS_BASELINE 32/32 GREEN，HEAD 5804f87）。

### 22.1 AX 遍历被代理地址复用截断（最隐蔽）

- **现象**：`_walk` 遍历 NSOpenPanel 只拿到 14/144 个元素，侧边栏 home 行
  偶尔“不存在”；同一棵树先 `list()` 再 `for` 结果不同。
- **根因**：AXUIElement 代理在两次 yield 之间被释放，`objc.pyobjc_id`
  地址被复用，`seen` 误判重复而跳过真实子节点。
- **修法**：遍历期间持有所有元素引用（`keep` 列表），`_walk` /
  `_walk_static` 均已修。排查 AX“缺控件”先怀疑这条。

### 22.2 对话框里有“影子”控件：取第一个匹配

- **现象**：完整遍历后 `AXPress(Save)` 返回 `-25205`（action unsupported）
  或返回 0 但面板不关；同一视觉按钮存在多个 AX 代理。
- **修法**：`_dialog_widgets` **保留第一个**匹配，不要取最后一个；
  第一个才是真实可操作控件。AX 错误码要用原始返回值判断，不要只看 bool。

### 22.3 Save As 面板不是 key window

- **现象**：`AXFocused=False`；真实鼠标/键盘事件到不了面板（点 Cancel
  也不关），但 `AXSetValue` 改字段可见、`AXPress Save` 可提交。
- **修法**：Save Project as 走 `AXSetValue + AXPress`；**不要**真实点击
  或键盘。保存目录跟随当前项目/模型目录；`window_mainframe` 已在 seed
  里固定为 `360; 80; 1200; 800; 0`。
- **导出面板相反**：忽略 AXPress，必须真实点 Save；默认目录是全局
  上次目录、还会自动补 `.stl`。m8x_204 采用“接受默认位置 + 按 mtime 取
  最新 .stl 再归位”，不再深目录导航。

### 22.4 NSOpenPanel：停 Recents、文件行无 AX

- 面板打开停在 Recents，`AXBrowser` 每列只有空 `AXScrollArea`；文件行只能
  靠 OCR + 真实点击。
- **导航**：AXOpen/点击侧边栏 home → OCR 面板 → 逐级单击目录（取最右列
  的匹配词）。**滚动只用滚轮**（x≈面板 0.85、y≈0.55）；AX
  `AXScrollDownByPage` 会把列滚回去、抵消滚轮。
- **底部行陷阱**：行靠近面板底部（y>bottom-100）时词中心落在 Cancel 的
  hover padding 上，点击会关闭面板 → 改点该行**右侧**（panel.right-40）。
- 文件名 OCR 常把结尾 `l` 读成 `I`；按 stem/字母数字归一化匹配。

### 22.5 启动/加载弹窗

- `Customized Preset`（启动与打开项目都会出现）不关则菜单全 disabled、
  标题为空；已加入 `_BLOCKER_TITLES`。
- 旧配置项目会弹 `Snapmaker Orca information`（“newer version … values
  have been replaced”）；OK 是自绘按钮，AX 无标题 → 已加 OCR `OK`
  兜底并加入 blocker 列表。

### 22.6 Vision OCR 会挂死（VNCRImageReaderDetector）

- **现象**：m4a 整例卡 18+ 分钟；`sample` 栈停在
  `com.apple.VN.detectorSyncTasksQueue.VNCRImageReaderDetector`。
- **修法**：`macos_ocr.recognize_text` 用 daemon 线程 + 30s 超时
  （`ORCA_BB_OCR_TIMEOUT` 可调），超时抛 `OcrError`；runner 再加单例
  600s watchdog、超时清 app、失败重试 1 次。

### 22.7 切片/G-code oracle

- Slice 按钮在 `(1000,45)`；完成后窗口 OCR 出现
  `stop printing object …` / `WIPE_START`，`File > Export G-code…` 变为
  可用。导出走普通 Save 面板（AXPress 可提交），默认名来自项目。
- 校准对话框字段都是 AXTextField：温度 230/190/5（step disabled）、
  回抽 0/2/0.1、最大流量 5/20/0.5、输入整形 15/110/15/110/0.150；OK 用
  OCR 点击。小模型 vp 增量要按模型调（回抽塔 +0.0049，用 0.003 门）。
- 温度塔 gcode 的 M104/M109 S 值可验证 9 档 230→190 顺序。

### 22.8 自绘 gizmo / 字段

- Move/Rotate/Scale 面板**没有 AX 字段**；点数值后 Cmd+A/键入常导致面板
  关闭，190/191/192 暂缓。
- 可用的真实输入配方（Plate Settings 已验证）：点标题栏激活 → 点字段
  两次 → Cmd+A → Backspace → 剪贴板 Cmd+V → AXPress 第一个 AXButton(OK)。

### 22.9 用 3mf 构造前置（绕开 gizmo）

- 直接改写 `3D/3dmodel.model` 里 `<item transform>` 的旋转部分即可构造
  倾斜模型；应用加载时会自动落床（tz 变化），所以**基线必须在加载后
  另存 P0** 再比较。
- auto orient oracle：某旋转行 ≈ (0,0,±1)、tz=半高、x/y 不变、行范数≈1；
  Prusa 旁观 item 按 3 位小数比较（浮点序列化末位会变）。

### 22.10 仍未打通（后续会话直接从证据继续）

- 盘侧导轨 Remove/Lock：已打通（见 22.12）；底部盘条 OCR 仍读不到
  “Plate N”。Customize(1070,300) 可用，#198 已绿。
- m8z Assembly View：默认 1200 宽窗口把它裁到窗口外；1512 宽后已打通
  （见 22.11）。
- m8x_221/222：PA Line 生成后切片报
  `Error: A G-code path goes beyond plate boundaries`，Export 保持禁用。
- **m8e/#129 弱冷分支（已定案，按当前值移植）**：2.4.2 安装包模板的
  `{else}` 弱冷分支是 `MODE=1 DESIRE_TEMP=45 ALARM_TEMP=51
  FAN_SPEED=0.6 DELAY_OFF=0`（强冷 `==2` → `MODE=1 DESIRE_TEMP=42
  ALARM_TEMP=48`；保温 `==0` → `MODE=3 DESIRE_TEMP=45 DELAY_OFF=600`）。
  用户用本机 Orca 2.4.2 跑 #114 生成的 gcode 与我们的输出**逐字节一致**；
  Windows 侧 2.4.2（MD5 D472049F…）核对结论同样是这三行——因此不是
  Windows/macOS 差异，而是仓库旧注释/旧基线文档与 vendored
  `resources/` 旧模板（20260128 单分支版）滞后。m8e 已按当前值注册
  （证据 `artifacts/mac/pilot/m8e/{work/m8e_weak.gcode,
  user_case114_weak.gcode}`）。同理 m8x_123 的强冷 `ALARM_TEMP` 在
  2.4.2 上应为 48（仓库里的 45 是旧值）；m8f 的双档数组比较也需按
  2.4.2 实际输出重新定口径。

### 22.11 装配视图与单字符对象行（m8z）

- **工具栏右端会被裁掉**：1200pt 宽时 Assembly View 图标在窗口外，菜单/
  导轨里也没有入口，容易误判成“当前 build 没有该功能”。用
  `ORCA_BB_WINDOW_FRAME="180; 40; 1512; 982; 0"`（seeded
  `window_mainframe`）重开即可，图标在窗口相对 (1470,70)；点击后视口
  diff≈0.35，并出现 Section View / Explosion Ratio / Selection Mode。
- **单字符对象行 OCR 不可见**：夹具盘 1 的对象名就是 `"1"`，Vision 不把
  树行识别成词（截图里肉眼可见）。可靠做法：OCR 到 `Plate 1` 行后，按树
  行高 23px 点第一个子行 `(25, plate1.y+23)`；右侧信息面板出现
  `Object name: 1` 与 `Size: …` 即为真实选中证据。
- **应用内 Error toast 不是弹窗**：加载该夹具会浮出
  `Error: Relative extruder addressing…` 红色通知，它画在主窗口内，
  Windows 的 `#32770` 与 macOS 的窗口枚举都不会算成对话框。macOS 侧
  “无错误弹窗”判据 = 主窗口无 `AXSheets` 且无其它 layer-0 屏幕窗口。

### 22.12 盘侧导轨按钮与 Save 面板跨用例记忆（m8x_194/197）

- **导轨标定**：1200x800、双盘布局下，当前盘右上角的斜排图标列是
  (920,251) Remove current plate / (933,261) Auto orient / (952,271)
  Arrange / (972,281) Lock / (992,291) Customize / (1012,302) Move to
  front。tooltip 渲染在**光标右侧**（裁剪右侧 260x80 可读），点击前必须
  用 tooltip 验证；找不到时 ±40/±30 网格兜底，绝不盲点。Add plate 的
  tooltip 则在下方（`tooltip_below`）。
- **Lock 语义**：锁定后同一图标 tooltip 变 `Unlock current plate`，导轨
  Arrange 被拒并在右下角 toast 出现
  `This plate is locked. Cannot auto-arrange on this plate.`；解锁后
  Arrange 让两个重叠立方体分开（保存 3mf 对比 build-item 平移）。与
  Windows 断言同口径（锁定拒绝整理 / 解锁恢复整理）。
- **Save Project as 面板记住全局最近目录**（NSSavePanel recent places，
  跨 datadir 共享）：m8x_197 的保存实际落到 m8x_194/work，驱动按目标
  路径找不到文件（日志 `not found after save`，第二次出现 Replace 提示）。
  `mac_common.recover_saved_file` 在 `artifacts/mac/pilot` 下按文件名前缀
  + 新 mtime 找到文件并移回目标路径。m8x_204 的 STL 导出也有同样现象
  （`accept_anywhere` 已处理）。
- **toast OCR 带脏字符**（`… printina. Jump to [Cubel!`）：用关键字子串
  判定，别要求全文精确。

### 22.13 多模型导入 + 切片导出（m8x_158）

- **空盘判定必须看视口**：整窗 `colored_fraction` 会被侧栏彩色耗材块拉到
  1.78%（>1.5% 门限）；空盘判据用 m7h 的视口区域
  `(430,100)-(1080,700)` + spread>24，实测 0.11%。
- **导入的落点**：空工程连续导入 Prusa.stl / cube20.stl / prism12.stl，
  三者 xy 平移完全相同（135.5,136.0），应用弹 "… is too close to others"
  警告 —— 天然构成“待整理”布局，不需要 Windows 那种拖拽构造。
  按 A 整理后三者各移动 ≥9mm、两两 AABB 间距恰好 2.0mm、均在 U1 打印区。
- **切片 + 导出 G-code**：Slice 按钮 (1200 宽时 1000,45)；轮询
  File > `Export G-code...` 从 disabled 变 enabled 即切片完成（≈20-40s）；
  导出面板会开在**模型所在目录**，且 **AXPress Save 不落盘** —— 必须
  `save_file_dialog(accept_anywhere=True, search_roots=[work, pilot, ...])`
  走真实点击 + 新文件发现。Prusa+3 对象导出 ≈1.06MB，`; filament used [g]`
  可读（[1]）。
- `mac_gcode.py` 是 `tests/m8_common.py` 里 `used_filaments` /
  `purifier_params` 的 macOS 副本（后者模块级 import win32，macOS 不能
  直接复用）；正则需与 Windows 版保持同步。

### 22.14 耗材预设下拉与 Change Filament（macOS 可用）

- **侧栏预设下拉是自绘两级菜单**（无 AXMenuItem），用 OCR + 真实点击：
  1200x800 下槽 1 组合框在 `(58,414)`、槽 2 在 `(242,414)`；点开后出现
  厂商菜单（窗口相对 ≈(236,442)，含 `Generic` / `FDplast` / `Snapmaker`），
  点 `Generic` 后子菜单在 ≈x=516 列出 `ABS`/`ASA`/`PC`/`PLA` 等；点击后
  槽位行文本立即变为 `~ Generic ABS`（实测 `(244,414)`）。
- **对象换耗材槽**：画布右键模型 → 上下文菜单是真实 AXMenuItem 列表，
  `Change Filament` 的 AXPress 会展开子菜单（同为 AXMenuItem，如
  `Snapmaker PLA Silk`），点击即可把对象指到该槽。MIXED 夹具的模型点
  在 1200x800 下约 `(814,396)`（Delete All + Add Cube 后仍在盘心附近）。
- 这两条通道足够覆盖 m8c/m8d 的“换耗材预设/换槽”步骤，无需 Windows 的
  消息级菜单技巧。
- **Snapmaker 子菜单要滚动**：切成 Generic ABS 后再开 Snapmaker 厂商子菜单，
  `PLA Silk` 不在首屏（列表按类型排序、窗口只显示 ~8 行）；在子菜单窗口
  中心滚轮向下，实测 **7 步**（每步 -3 notch）后出现于窗口相对 (518,654)。
  厂商/类型菜单都是自绘、无 AX 项，OCR 定位后真实点击。
- **切片后 app 自动切到 Preview**；盘侧/门禁操作前先点回 Prepare。
  切片完成后的 Slice 按钮是“done 态”（teal≈0），只有盘面发生变化才会
  重新渲染为可点的 teal 药丸（实测 0.68）。因此 **不能只靠 teal 判定门禁**：
  m8c 的硬判据 = 混用横幅 OCR + 点击 Slice 后按钮区域像素 diff≈0（被拦）；
  解除混用后同一区域 diff=0.71（切片启动）。

### 22.15 双模型重合、原生取色器与文件名陷阱（m8x_153）

- **导入文件名别带小写 x**：open panel 的 OCR 会把 `m8x_153_...` 读成
  `m8×_153_...`（×），`_pick_file_word` 的 alnum 归一化后与 stem 不匹配 →
  明明行就在屏幕上却报 "not visible"。案例把导入文件改名为
  `prusa153.stl` / `cube153.stl` 后一次通过。另外导入面板的列视图偶尔会
  点错文件夹，用例已加 3 次重试 + 关闭残留面板。
- **导入会自动避让**：CLI 载入的 Prusa 在 (100,100)，再导入的 cube20 落在
  (135.5,136)，两者不重合、无碰撞提示。Windows 用 Move X=Y=0 构造重合；
  macOS gizmo 不可靠 → 直接改 3mf：把 cube 的 build-item transform 的
  tx/ty 写成 Prusa 的 (100,100) 后重载，载入即出现 "too close to others"，
  3mf 世界中心距 0.00mm；按 A 后两对象分开到 21.85mm。
- **原生 Colors 面板换色**：点耗材色块打开 title='Colors' 的 layer-8 面板。
  顶部 5 个 44x33 AXButton 中第 2 个是滑杆模式；模式下拉的当前值可能是
  `Grayscale Slider`，点开后选 `RGB Sliders`（AXMenuItem 有 rect；菜单
  枚举会混入主菜单项，必须过滤 rect 非空）。RGB 模式下有 Red/Green/Blue
  三个 AXSlider + 数值框 + 十六进制框。**AXSetValue 能改值但不触发面板
  action**；用真实点击滑杆轨道两端即可（Red/Green 左端、Blue 右端），实测
  取到 `#0303FC`，侧栏色块变为 (3,3,252)，gcode 的
  `; filament_colour` 与十六进制框逐位一致。

### 22.16 官方色卡弹窗与自绘预设菜单滚动（m8b）

- **官方色卡弹窗**：点 Snapmaker 预设槽（如槽 2 PLA Silk）的色块，打开
  无标题 layer-8 窗口，约 (788,484,380,376)。内容靠 OCR：卡片名 + `sku N`
  在顶部，`Official Filaments` 是列表标记，卡片是 5x3 自绘网格（对话框
  相对中心 x=29/77/125/173/221，行 y=166/194/222），底部 `Cancel`/`OK`
  在对话框相对 (120,348)/(259,348)。背景画布点击**不会**关闭弹窗（模态）。
- **#46/#47 口径**：选卡后 SKU 变化 → OK 关闭且侧栏色块像素变化；重开
  SKU 保持。再选另一张卡 → Cancel 关闭，色块不变，重开仍保持 OK 所选。
  非官方预设（Generic PETG）点色块回退到原生 `Colors` 面板（#44 反向对照）。
- **自绘预设子菜单滚轮会被吞**：打开 Snapmaker 厂商子菜单后，wheel 事件
  只滚动一格，随后全部丢失（type-ahead 也无效）。可靠做法是 **CGEvent
  拖拽子菜单右侧滚动条**：鼠标 press 于 (right-5, y+30)，拖到
  (right-5, bottom-20)，release；一次即可让 `PLA Rainbow` 出现在
  (520,618)。这是解决 m8f/m8g 预设选择的关键通道。
- **槽位行文本会截断**：选中后行只显示 `~ Snapmaker PLA Ra...`，不能用
  `rainbow in row` 判定；最终以 gcode 的 `filament_settings_id` 列表含
  `Snapmaker PLA Rainbow` 为准。
- **Delete All 后右键点会漂**：m8d 在 (814,396) 能命中 cube，m8b 同一状态
  却要 (790,430)。右键找 Change Filament 时用 7 个点的小网格
  (814,396/430/460、850/790,430、814,380、780,400) 逐点试。
- **Rainbow 切片会用满 5 个槽**（渐变/混色），不要断言 `used==[2]`；
  断言 `2 in used` + `filament_settings_id` 含 Rainbow。实测 #56 渲染
  主色 hue=15°、声明色 `#EB6232`（15°）、140px 裁剪内饱和占比 0.272。

### 22.17 高流量预设与 Nozzle Flow（m8f/m8g）

- **工艺用户预设顺序**（空工程 + cube，1200x800）：进程下拉的 User presets
  三行在 y=616/640/668，依次是 **HF-TEST / STD-TEST / FLOW-TEST**。
- **耗材用户预设**：槽 1 下拉 → **悬停** `Custom`（点击不会展开）→ 右侧
  变体行 y=474/500/526，依次是 **FLOW-TEST / HF-TEST / STD-TEST**。行文本
  被截断成 `Snapmaker PLA SnapSpe...`，无法按名字识别；判定必须靠
  **保存工程后读 `print_settings_id` / `filament_settings_id`**（UI 的
  combo 文本同样截断，gcode 里的同名配置块也可读）。
- **Nozzle Flow 下拉**：`Standard` 在 (310,324)、`High Flow` 在 (312,349)
  （窗口相对，点击前 combo 在 (308,288)）。
- 切到 **High Flow** 后切片会弹 `Custom Filament Grouping` 模态窗口
  （772x362）：OCR 可见 `Standard Nozzle` / `High Flow Nozzle` 与
  `Confirm`。默认 PLA 芯片在 Standard 列；**用 CGEvent 拖拽把 PLA 拉到
  High Flow 列**（窗口相对 246→642，y 不变）再点 Confirm（窗口相对
  (890,535)），否则高流量喷嘴不生效。
- **#136（m8g）可绿**：FLOW-TEST 两档值相同，两个独立会话各自切片，
  compare_gcode 报告 **mode=1、numeric=0** → PASS。
- **#135（m8f）在 macOS 上不可按原口径变绿**：STD-TEST+Standard 与
  HF-TEST+High Flow 的 gcode 配置数组保留了**两档值的固定顺序**
  （如 inner_wall_speed A=550,600、B=300,550），官方脚本按位置比较 →
  `mode=2、numeric=39`。实际生效档的值是同一个 550，但对比工具不按
  “当前档”取值。这是构建/模板差异，已记录；m8f 保留为 m8g 的共享
  helper 模块，不注册进 MACOS_BASELINE。
- **普通预设切换（m3e）**：MIXED（0.8 喷嘴）的 process combo 在
  (42,646)，平铺菜单的系统行 0.24/0.32/0.40 在 y=704/730/756；点 0.24
  后重新切片，gcode `; layer_height` 0.4→0.24、`print_settings_id`
  同步为 0.24mm。切片后 app 在 Preview，切换前先点回 Prepare。

### 22.18 耗材 Material settings 编辑器（m8x_123 预研）

- **入口**：耗材行右侧小按钮（槽 1 行 y=418 时点 `(196,418)`）弹出 Edit /
  Delete / Merge with；点 `Edit`（窗口相对 `(198,446)`）打开
  `Material settings` 窗口（约 `(585,122,750,600)`，layer 0）。
- **字段是 AXTextField**：PETG (834,269)、Diameter 1.75 (818,297)、
  Softening temperature 70 **(833,325)**、Idle 0 (833,353)、
  Recommended nozzle 220/270 (933/1177,389) 等（均为屏幕坐标）。
- **提交值的关键是 `AXConfirm`**：该 AXTextField 的 actions 是
  `('AXShowMenu', 'AXConfirm')`。只做 `AXSetValue` 再关窗会丢弃修改
  （切片后 vitr 仍是 70）；`AXSetValue` 之后对同一元素执行
  `AXConfirm`（`harness.platform.macos._ax_perform(field.handle,
  "AXConfirm")`）才会触发 wx 的 change 事件，再点红点关闭即把覆盖值带进
  工程。真实键入/Cmd+V 在本机不可靠（合成键盘事件可能被吞），不要依赖。
- **m8x_123 已打通**：栏 1 软化温度 45 → `vitr=45,45,45,45,45` + 强冷
  `MODE=1 DESIRE_TEMP=42 ALARM_TEMP=48`；改 80 → `vitr=80,45,45,45,45`
  + 保温 `MODE=3 DESIRE_TEMP=45 DELAY_OFF=600`（无 ALARM）。仓库 Windows
  用例文本里的 `ALARM_TEMP=45` 是 2.4.2 之前的旧值（Windows 2.4.2 核对
  为 48）；macOS 端口按 48 断言。

### 22.19 混色批量对话框（m3k 已打通）

- 侧栏 `Color Mixing Match` 打开的是**独立窗口**（title 相同，layer 8，
  约 500x728）。OCR 时注意：`recognize_text(capture_screen().crop(win.rect),
  Rect(dlg_rel...))` 返回的是**主窗口相对坐标**，不是对话框相对坐标；点击
  必须加 `win.rect.x/y`（本项目因此多花了一轮探针）。
- 关键坐标（主窗口相对）：Match Mode 组合框 `(482,119)`；下拉的
  Auto/Manual 在 y≈153/179；`Start Matching (650,117)`；`Cancel (458,761)`；
  `Confirm (690,761)`。
- Manual + Start Matching 后：Matched 预览由灰色占位变为彩色（饱和占比
  实测 **0 → 0.557**），Color Mapping 行与 → 出现，并弹
  `The mix ratios for 7 ... outside the recommended ranges` 横幅。
  Confirm 关闭窗口。该窗口是 m3l/m3m/m3r/m3s/m4b 等批量对话框用例的共用面。
- 映射行 tooltip（m3l）：wx system tooltip 在 macOS 上需要**约 2.5s**
  才弹出（1.2s 时读不到）；悬停窗口相对 (400,725) 后 OCR
  `Color Difference: Good (AE=0.0)`，等级带 Good<=4 / Fair<=8 / Poor>8
  与值一致。
- **m3m 预研**：Manual 的 Filament Setup 卡片在 macOS 默认就是 **4 行**
  （Generic PETG + 3× PLA Silk，= min(4, n_physical)），不是 Windows 用例
  预期的 2 行；卡片右上角候选点 (664/682/700, 210/228) 悬停只读到行文本，
  未定位到 add/remove 图标。m3m 暂缓，后续需重新标定按钮几何。
