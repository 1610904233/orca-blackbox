# 242_RUN_REPORT — Orca 2.4.2（orca242d）全量复跑分类报告

- 日期：2026-11-10 晚（全量 18:55 启动，约 21:40 完成 + 补跑）
- 包：`C:\coil\apps\orca242d\Snapmaker_Orca\snapmaker-orca.exe`（exe md5 8ae99da…）
- 宿主 HEAD：a33213b；客机 checkout 与 origin 同步（全量经 hv_go 正常 sync）
- 对比：2.4.1 基线 57/57 GREEN；2.4.2c 首轮 6/51

## 结果总览

**最终：57/57 GREEN**（全量 46/57 -> 逐项修复/重标定；11-11 深夜 m8x_152 经
对象标签页通道转绿，全部功能面自动化覆盖）：
m8x_191 的红是批次内进程中止（stdout 管道堵塞误判挂起后被杀，rc=-1；
归档帧显示其实跑到 s4），单例补跑 GREEN，如实记录。

## 11 红分类

### 产品侧（6 例——见 242_FINDINGS.md）

| 用例 | 发现 |
|---|---|
| m3m_mixing_filaments | F-6 色域警告文案不再含「0%-70%」（功能正常） |
| m8d_purifier_gcode | F-7 PLA strong ALARM_TEMP 默认 45→48 |
| m8e_purifier_weakcool | F-7 PETG 默认模式弱冷→强冷（MODE=3/DESIRE=0 → MODE=1/DESIRE=45/ALARM=51） |
| m8x_123_softening_temp | F-7 + F-8：UI 行显示「弱冷」但 gcode 仍强冷（UI/gcode 脱钩，疑似回归） |
| m8x_190 | F-3 WM_CHAR 丢字间歇发作（'100'→'1' 静默提交，3 次运行 2 红；字段级拒绝门 PASS 但 3mf tz=1.00） |
| m2_slice_chain | 初判 F-5 已**改判测试侧**（取证后定案，见下） |

### 测试侧标定（11-11 重标定会话后：2 绿 2 改判产品侧）

| 用例 | 结果 |
|---|---|
| m8x_153 | **GREEN**——chip 弹的其实是 Windows 标准取色器（F-9 行为变更），加标准取色器回退（1cc8d46） |
| m8x_156 | **GREEN**——Move 拖拽加质心邻位阶梯（rotate 3 点/scale 13 点同款容差，1cc8d46） |
| m8a_fit_view | #16/#17/#18 修复（标题栏授焦 + 整块采样，1cc8d46/4497734/93ee3de）；**#19 保持 RED = F-11**（Select All 疑似只选当前盘，全选后 Fit 无变化，三轮取证） |
| m8x_152 | **保持 RED = F-10**（gizmo 面板用过关闭后五通道均无法选中，确定性复现，测试侧不绕过） |

### 基础设施（1 例）

| 用例 | 说明 |
|---|---|
| m8x_191 | 批内 stdout 管道堵塞 → 误杀（rc=-1）；补跑 GREEN |

## 本轮适配提交（全部经单例红→绿验证）

- `12d0275` m7.find_slot 固定几何回退 + 无 tooltip 选中判定
- `51ffbba` File 菜单 GetSubMenu 直读（去掉 hover）
- `464799f` dropdown 子菜单加速键路由（WM_COMMAND 双目标实证死亡）+ boot 150s
- `663d56b` 归档节流旋钮（ORCA_BB_SHOT_INTERVAL，批量 10s，DWM 风暴缓解）
- `a33213b` m2 工具路径比值门 2.0→1.5（F-5 取证定案）
- `fe9b5f8/b55f5f7/88ccf51` 242_FINDINGS.md F-1..F-8

## 过程要点

1. **客机 checkout 对账**：2.4.1 时代的 base64 叠加层（59216ff+46 文件）
   经 blob-hash 逐文件核实后清理对齐 origin；2 个与 origin 不同的探针已
   备份宿主 artifacts/guest_probe_backup/。
2. **DWM 风暴**：本会话一次发作（客机 uptime 25h，dwm/python/orca 全
   hung）→ 重启 + 归档节流后全量 ~3h 未再复发。
3. **黑屏/挂起处置**：m8x_191 的空日志曾误判挂起（stdout 管道堵塞，
   归档帧显示实际在跑）——教训：判断挂起前先查 shots 目录有没有新帧。

## 飞书写回判断

本轮**无新增自动化覆盖**（57 例在 2.4.1 收尾时已全部写回「已自动化」），
自动化状态无变化，未执行写回。产品侧 5 项发现（F-1/F-3/F-6/F-7/F-8）
建议转交开发侧确认后再决定是否在飞书另开问题跟踪。

## 11-12 增补二：#196/#197/#198 盘侧工具栏三条（用户逐条确认）

- **#196 排列零件**（m8x_196）：自定位斜排线 arrange 图标
  （tooltip 'Arrange objects on current plate'）+ 双零件分离判定
- **#197 锁定当前板**（m8x_197）：lock 图标（'Lock current plate'）→
  锁定态点整理：右下角 toast 原文 'This plate is locked. Cannot
  auto-arrange on this plate.' + **3mf 几何回读立方体坐标未动** →
  tooltip 状态核验解锁 → 再整理：坐标分离（29mm）
- **#198 编辑盘名**（m8x_198）：Customize current plate → Plate Settings
  的『Plate name』字段；三态按用户更新后的基线：全空格/100 字符
  **当前无限制（接受）**、特殊字符 'B@#1' 存盘回读逐字一致
- 飞书三条已写回「已自动化」并回读验证
- **覆盖更新：61 个自动化脚本 / 83 行基线**

## 11-12 增补：#20 导入含装配关系（新用例 m8z_assembly_import）

- 用户提供 3mf 夹具（下沉式宝可梦纸巾盒，8 对象/3 盘，装配关系完整），
  已入库 fixtures/assembly_pokemon_box.3mf
- 用例：载入（先点掉 'Snapmaker Orca information' + 'Customized Preset'
  两道提示框——不点则 Loading 永挂、视口为空，实测）+ 对象行证据 +
  Assembly View 切换（视口 mad 35.45）→ **GREEN**
- 飞书 #20 自动化状态已写回「已自动化」并回读验证
- **覆盖更新：58 个自动化脚本 / 80 行基线**（套件当前 57+1）

## 11-11 深夜终局：全量 57/57 GREEN（单批背书）

**最终全量复跑（21:35 启动，约 3 小时，含热身轮）：SUMMARY: PASS=57 FAIL=0**
——这是所有共享原语改动与用例重写之后的**单批**结果，非拼凑重跑。

## 11-11 深夜终局（m8x_152 转绿）

- 用户指路的关键通道：**工艺→对象标签页**的行点击选中 + 行右键
  Change Filament——画布选中在 2.4.2 程序化输入下不可达，此按钮面通道
  完全可用（probe_242_objlist3 实证）
- s4 合并链全自动化 GREEN：指定末位槽（切片用量 [4]）→ '...' Merge
  with 1 → 物理槽 4→3 → 切片用量 [1]（重映射）
- 产品语义确认：缺省耗材=1 号丝；Merge-with 保低槽

## 11-11 重标定会话补记（探针 diag/probe_242_recal{,2,3,4}）

- 测试侧 backlog 清零：m8x_153/m8x_156 转绿；m8a 3/4 门转绿
- 新增产品发现：F-9（非 Snapmaker 预设 chip 开标准取色器）、
  **F-10（gizmo 面板关闭后无法选中，最高优先级回归嫌疑）**、
  F-11（Select All 疑似只选当前盘）

## 11-12 收口：台账状态与校准 13 行的更正

### 更正：校准 13 行（#206–#222）不是「真机依赖」，可自动化

第一版收口把「校准」整组按交接口径标成「不适用」，这是**错标**——逐条
核对步骤后确认这些用例全部是本地操作：展开校准菜单 → 看弹窗默认值 →
确认后从安装包自带 `resources/calib/*` 模板生成模型 → 本地切片 → 读
gcode/对象列表，不需要连接打印机（与套件里全部切片用例同一环境）。

离线探针实证（`diag/probe_242_calibmenu{,2}.py`，客机 orca242d）：

- 入口是顶栏自绘工具，位于 topbar **offset 250**（截图 `artifacts/p242cm_top.png`）；
  `GetMenu(frame)=0`，说明走的是 BBLTopbar 自绘菜单，不是原生菜单栏。
- 点开后 HMENU 树完整可读（id 可直接用于 `WM_COMMAND` / 加速键路由）：
  ```
  Temperature 378
  Flow rate (sub): Pass 1=379, Pass 2=380, YOLO (Recommended)=381,
                   YOLO (perfectionist)=382
  Pressure advance 383 / Retraction test 384 / Max flowrate 385
  Cornering (sub): Junction Deviation 386
  Input Shaping (sub): Frequency 387, Damping/zeta factor 388
  VFA 389 / Tutorial 390
  ```
  与 #206 预期条目逐项对应（「粗调/细调」= UI 的 `Pass 1/Pass 2`）。
- 安装包侧证据：`resources/calib/{temperature_tower, pressure_advance,
  retraction, volumetric_speed, input_shaping, vfa}` 全部存在；
  `i18n/en/Snapmaker_Orca.mo` 含 `Calibration` 字符串。
- 结论：#206–#222 可按本地 UI+切片路径自动化，无真机/云依赖。

因此 13 行已从「不适用」改回「未覆盖」并回读验证（`reopen_calib_13`），
待后续逐条实现；真正不适用的只有 5 行：#184（人工验证）、#223/#224
（卸载安装器，范围外）、#225/#226（局域网/云联机）。

### 当前台账（145 行实时回读）

**90 已自动化 + 4 部分自动化 + 2 未覆盖 + 49 不适用 = 145**

- 覆盖口径：**94 行 = 72 个脚本**（90 已自动化 + 4 部分自动化）
- 本轮入库：2.4.1/2.4.2 适配期探针 46 个与两份历史交接文档（`36b397d`）；
  校准菜单探针 `probe_242_calibmenu{,2}.py`、dismiss 探针一并入库

## 11-12 增补三：#206 校准菜单存在性落地（62 脚本 / 84 行）

- 用例 `m8x_206`（新增）：空床 boot → 顶栏 Calibration（offset 250）→
  HMENU 直读一级/子菜单 → 按飞书步骤 3 真实悬停展开三条子菜单（录屏可见）
- 判定 10/10 PASS（客机 orca242d）：一级 8 项齐全、流量/转弯/输入整形
  子菜单内容齐全（HMENU + 视觉展开双证据）、无灰置、菜单可关闭、app alive
- 实测一级菜单比飞书多一项 `Tutorial`（「包含」口径不判红）；
  UI 文案 `Pass 1/Pass 2` = 飞书「粗调/细调」
- 2.4.2 关闭通道实测（`probe_242_calibdismiss{,2}`）：自绘顶栏 popup 不响应
  `WM_CANCELMODE`；`m7.dismiss_menus` 的右击兜底会在画布另开右键菜单
  （被误判为「菜单未关」）；可靠通道 = 主窗前台下真 ESC×2
  → 固化 `topbar_util.close_calibration_menu()`
- 录屏 `artifacts/m8x_206_run.mp4`（3.69 MB，用户确认）；飞书 #206 已写回
  「已自动化」并回读一致
- 提交：`4a23595`（用例+入口原语）、`0877dd9`（关闭通道+探针）、
  `115e244`（lint）、`0257ec2`（视觉展开子菜单）

## 11-12 增补四：#207 压力提前弹窗非法输入落地（63 脚本 / 85 行）

- 用例 `m8x_207`（新增）：Calibration > Pressure advance（#32770
  'PA Calibration'）→ Start PA 三步非法输入（abc / 清空 / 粘贴 1a！@）→
  每步点 OK 都必须弹 'Snapmaker Orca info' 警告并保持对话框、不生成模型
- 实测警告正文：`Please input valid values: Start PA: >= 0.0 /
  End PA: > Start PA / PA step: >= 0.001`
- 输入通道教训（**PITFALLS 21.21**）：客机中文输入法在系统层吞掉字母真实键
  （keybd_event / WM_CHAR / VK_PACKET / 摘 IME 上下文 / 切 en-US 全无效，
  probe_242_pa207d/e/f）；`abc` 改用 `EM_REPLACESEL` 写入并单独断言字段
  回读，视频可见；清空仍用真实键、粘贴用剪贴板+真 Ctrl+V
- 另一测试侧时序：首次真实点 OK 偶被吞（A 步两次复现）→ 用例内置一次重试
- 判定 12/12 PASS（客机 orca242d），录屏 `artifacts/m8x_207_run.mp4`
  （5.81 MB，用户确认）；飞书 #207 已写回「已自动化」并回读一致
- 提交：`504e126`（用例+三个标定探针）、`9b11312`（EM_REPLACESEL 修正
  + PITFALLS 21.21）

## 11-12 增补五：#208 温度塔落地（64 脚本 / 86 行）

- 用例 `m8x_208`（新增）：Calibration > Temperature（#32770
  'Temperature calibration'）→ 默认值 230/190/5（步长控件 disabled）→
  确定生成预置温度塔 → 模型落板（空床彩色占比 0.0638% → 1.3076%）→
  切片 + 导出 gcode
- gcode oracle：M104/M109 的 S 值九档 {230,225,...,190} 齐全，首现顺序
  230→190 递减（机器 start gcode 的 140/180 等已过滤）
- 判定 13/13 PASS（客机 orca242d），录屏 `artifacts/m8x_208_run.mp4`
  （5.58 MB，用户确认）；飞书 #208 已写回「已自动化」并回读一致
- 提交：`2e5033a`（用例+Temperature 对话框标定探针）

## 11-12 增补六：#209 流量粗调落地（65 脚本 / 87 行）

- 用例 `m8x_209`（新增）：Calibration > Flow rate > **Pass 1**（hover 展开
  子菜单 + 真点首行，无参数弹窗）→ 9 块校准件落板（0.0638% → 3.0243%）
- 对象名精确 oracle：存盘 3mf `model_settings.config` 的 9 个 `<object>`
  name = `flowrate_0/5/10/15/20` + `flowrate_m5/m10/m15/m20`，逐字一致
- UI 证据：Objects 标签页滚到顶 OCR（面板高度只显示 6 行）+ 可见行点击
  选中；切片成功
- 判定 7/7 PASS（客机 orca242d），录屏 `artifacts/m8x_209_run.mp4`
  （5.81 MB，用户确认）；飞书 #209 已写回「已自动化」并回读一致
- 提交：`13bb6aa`（用例+Flow 子菜单/对象列表标定探针）

## 11-12 增补七：#210 流量细调落地（66 脚本 / 88 行）

- 用例 `m8x_210`（新增）：Calibration > Flow rate > **Pass 2**（hover
  展开子菜单 + 真点第 2 行，无参数弹窗）→ 金字塔形 10 块落板
  （0.0638% → 3.4135%）
- 对象名精确 oracle：存盘 3mf 的 10 个 `<object>` name =
  `flowrate_0` + `flowrate_m1~m9`（仅负向、整数步进 1），逐字一致
- UI 证据：Objects 标签页 OCR（可见 flowrate_0/m1~m5）+ 可见行点击选中；
  切片成功
- 判定 7/7 PASS（客机 orca242d），录屏 `artifacts/m8x_210_run.mp4`
  （6.21 MB，用户确认）；飞书 #210 已写回「已自动化」并回读一致
- 提交：`a667092`（用例+登记）

## 11-12 增补八：#211 压力提前默认 PA 塔落地（67 脚本 / 89 行）

- 用例 `m8x_211`（新增）：Calibration > Pressure advance → 默认
  Start 0 / End 0.1 / Step 0.002；Print numbers `BM_GETCHECK=0`；
  Accelerations/Speeds `enabled=0` 且为空（DDE + PA Tower 默认态）→
  确定生成 PA 塔（0.0638% → 2.0085%）、对话框关闭 → 对象行选中 → 切片成功
- 对象选中判定两轮修正（都已提交）：
  1. 首版按 OCR 文本挑行，塔行 OCR 不到时误点设置页签 → **假阳性**；
     改为 Plate/Outside 之间的几何行（截图 L007 确认行名 tower_with_seam.stl）
  2. `plate_y` 误取搜索框行（`Search plate...` 含 plate）→ 塔行 y=595 点空；
     排除 search 行后 y=611 命中；先用 Outside 行清选、再点塔行证明选中
- 判定 11/11 PASS（客机 orca242d），录屏 `artifacts/m8x_211_run.mp4`
  （5.49 MB，用户确认）；飞书 #211 已写回「已自动化」并回读一致
- 提交：`349ac7b`（用例）、`941ab8a` / `d918a6a` / `fd1ca06`（选中判定修正）

## 11-12 增补九：#212 回抽测试落地（68 脚本 / 90 行）

- 用例 `m8x_212`（新增）：Calibration > Retraction test（#32770
  'Retraction test'）→ 默认 Start 0 / End 2 / Step 0.1（mm）→ 确定生成
  回抽测试塔（0.0638% → 0.5265%）→ 对话框关闭 → 对象行选中 → 切片成功
- 一次 gate 修正：首版用「+0.5% 绝对增量」判模型，回抽塔只有 0.53% 被
  误判；改为相对阈值（>基线+0.3% 且 >2×基线）后 GREEN
- 判定 9/9 PASS（客机 orca242d），录屏 `artifacts/m8x_212_run.mp4`
  （5.23 MB，用户确认）；飞书 #212 已写回「已自动化」并回读一致
- 提交：`b673508`（用例+探针）、`fc25e01`（gate 修正）

## 11-12 增补十：#213 最大体积流量落地（69 脚本 / 91 行）

- 用例 `m8x_213`（新增）：Calibration > Max flowrate（#32770
  'Max volumetric speed test'）→ 默认 5 / 20 / 0.5（mm³/s）→ 确定
- **发现**：该模板是 STEP 文件（SpeedTestStructure.step），点确定后先弹
  `Step file import parameters` 导入参数框，不点掉它模型不加载、主对话
  框不关（probe_242_maxflow213b 实证）。用例自动接受该框默认值。
- 模型落板 0.0638% → 4.1415%，对象行选中，切片成功
- 判定 10/10 PASS（客机 orca242d），录屏 `artifacts/m8x_213_run.mp4`
  （5.36 MB，用户确认）；飞书 #213 已写回「已自动化」并回读一致
- 提交：`088a677`（用例+探针）、`f2d8478`（STEP 导入处理）

## 11-12/13 增补十一：#214 输入整形频率落地（70 脚本 / 92 行）

- 用例 `m8x_214`（新增）：Calibration > Input Shaping > Input Shaping
  Frequency（子菜单 hover + 真点首行）→ 弹窗 X 15/110、Y 15/110、
  Damp 0.150；测试模型 Ringing Tower / Fast Tower 二选 → 确定生成扫频件
  （0.0638% → 0.9528%，非 STEP 模板）→ 弹窗关闭 → 对象行选中 → 切片成功
- 判定 10/10 PASS（客机 orca242d），录屏 `artifacts/m8x_214_run.mp4`
  （5.52 MB，用户确认）；飞书 #214 已写回「已自动化」并回读一致
- 提交：`5a378a0`（用例+子菜单/对话框标定探针）

## 11-13 增补十二：#217 YOLO 流量对比落地（71 脚本 / 93 行）

- 用例 `m8x_217`（新增）：Calibration > Flow rate > YOLO（推荐 /
  完美主义者）两版各自加载 → **各自切片** → 对比
- 推荐版 11 块（flowrate_0/±0.01~0.05），0.0638% → 2.9203%，切片 PASS
- **切片后 app 自动切到 Preview 页**：对象列表/删除只在 Prepare 页，
  故切片后先点 Prepare 页签再 Ctrl+A+Del 清场（frac → 0.1226%）
- 完美版 16 块（flowrate_0/±0.005~0.035，负向到 m0.04）；加载时弹
  "You have previously modified your settings" 合并框，选 **Discard**
  继续（probe_242_yolo217c）；0.0638% → 4.1793%，切片 PASS
- 命名实测为去尾零格式（0.01/0.02/0.03，非 0.010）；两版步进 0.005<0.01
- 判定 13/13 PASS（客机 orca242d），录屏 `artifacts/m8x_217_run.mp4`
  （9.63 MB，用户确认）；飞书 #217 已写回「已自动化」并回读一致
- 提交：`bdfc1cb`（用例+探针）、`1cdf656`/`1e799f0`（合并框/命名）、
  `a5888d2`（两版各自切片）、`fc9d7b0`/`41f722d`（Prepare 清场）

## 11-13 增补十三：#218 温度塔默认区间落地（72 脚本 / 94 行）

- 用例 `m8x_218`（新增）：Calibration > Temperature → Filament type 逐组
  点圆点，回读 Start/End/Step/可编辑态
- 六组实测与飞书逐字一致：ABS/ASA 270/230、PETG 250/230、PCTG 280/240、
  TPU 240/210、PA-CF/PET-CF 320/280、Custom/PLA 230/190；步长恒 5 且
  disabled；区间校验全部通过
- 每次切换后的数值都精确变化（无残留上一组数值）
- 判定 6/6 PASS（客机 orca242d），录屏 `artifacts/m8x_218_run.mp4`
  （4.27 MB，用户确认）；飞书 #218 已写回「已自动化」并回读一致
- 提交：`c5fe28c`（用例+六组切换探针）

## 下一步（建议）

1. **F-10、F-8 优先给开发侧**——最像真回归（选中失效 / UI-gcode 脱钩）；
2. F-7/F-9/F-11 与产品确认是否有意变更；F-1/F-2 人工真机确认；
3. F-3 丢字间歇发作（m8x_190 两红一绿），开发侧查文本输入消息泵。
