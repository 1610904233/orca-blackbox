# plate 重构专项包验收报告（win-x64_plater_b04c365）

- 日期：2026-11-13
- 包：`C:\Users\snapmaker\Desktop\plate重构专项测试\win-x64_plater_b04c365_20261111144353_portable.zip`
  - zip MD5 `06b61f7c5ac69fbb6a2b4dd25c1df3a2`（167,554,039 B），已传客机并校验一致
  - 客机解压路径：`C:\coil\apps\plate_b04c365\Snapmaker_Orca\snapmaker-orca.exe`
  - 版本：2.4.2；`Snapmaker_Orca.dll` 72.6 MB；`resources/calib` 含新增 `filament_flow`
- 环境：客机 win11-test 于跑前重启（uptime 11:59:29），交互会话 1920x1080，
  无残留 orca/python 进程；套件任务 `suite` 由 hv_go 以 INTERACTIVE 计划任务启动
- 范围：**baseline 全量 74 例**（含热身轮 m2_slice_chain 结果丢弃）
- 执行：`hv_go.ps1 -Suite baseline -Exe <plate exe>`（自动 sync 到 0c69f5f）
- 结论：**52 PASS / 22 FAIL（通过率 70.3%）**
- **本次只跑不改**：未修改任何用例、harness 或产品文件；失败项只做证据与根因分类。

## 一、失败分类（22 例）

### A. 建模入口变化：工具栏 Add 槽不弹菜单 / 热床右键不弹（11 例）

日志证据（多例一致）：
```
[m7] toolbar Add slot opened no menu
[m7] bed right-click ... no menu (menu windows seen: [])
```
- 直接表现：无法通过既有通道添加立方体/第二个模型，后续业务步骤无法执行。
- 涉及：m7b_new_project、m7h_context_delete、m7t73、m7t75、m7t89、
  m8b_official_color、m8d_purifier_gcode、m8e_purifier_weakcool、
  m8x_137_flow_param_tabs、m8x_196、m8x_197
- 备注：m8b 的官方色/彩虹/取色器全部子项均 PASS，仅"cube added"失败——
  该例的**颜色功能本身正常**，红在建模入口。

### B. 导出模式入口变化（1 例）

- `m3e_preset_switch`：
  `switch_to_export_mode FAILED (topbar print button never reached Export mode)`；
  预设组合框也未找到（`preset NOT found`），后续重切/头部断言随之失败。

### C. 选中/对象列表几何变化（5 例）

- `m8c_temp_mix_gate`：cube B「not selectable」（cube A 经回退通道添加成功）
- `m8x_125_aux_mix_pref`：主材=对象耗材丝，`model not selectable`
- `m8x_153`：两模型重合检测取到 3 个 blob（含 (1082,194) 小 blob，
  疑似新 UI 元素被当成模型）；move 面板字段 0→'136.00'、字段 1 为空
- `m8x_214`：`点击 Outside 行清除选择: FAIL (still selected)`（对象行 y 位移）
- `m8x_222`：`V 形模型对象行可单独选中: FAIL (info panel empty)`（同上）
- 均为对象列表/画布选中面的坐标或行位置变化，未触及被测功能断言。

### D. 测试脚本自身异常（2 例，非产品）

- `m8f_nozzle_flow`：
  `TypeError: cannot unpack non-iterable bool object`（`ok_b, g_b = ok_a and slice_with(...)`）
- `m8g_flow_single`：
  `ValueError: too many values to unpack (expected 3)`（`confirm_flow_dialog`
  对 kids 三元组解包）
- 这两条是脚本内既有潜在缺陷被本次代码路径触发，按用户要求**未修**。

### E. 输入/字段通道（2 例）

- `m8x_190`：`Z 不变: FAIL (tz 10.00->1.00)`——已知 F-3（WM_CHAR 丢字，
  '100'→'1' 静默提交）的间歇伪象，非产品。
- `m8x_191`：s5 绝对 Y=45 失败，日志显示字段一直读 `'135.00'`，
  逐字符输入 '4' 未落字段（未清空/未聚焦），矩阵 Δ=180°；s6 因前置保存
  缺失（A2/A3 未生成）失败。**疑似测试输入通道问题，非确证产品回归**。

### F. 保存提示阻断（1 例）

- `m8x_217`：推荐版 11 块与切片均 PASS；清场后加载完美主义者版时出现
  `Snapmaker Orca - Save` 对话框，加载失败（`loaded=False dialogs=['Snapmaker Orca - Save']`）。
  plate 构建新增/改变了保存提示行为，用例未识别该弹框；属**测试侧适配缺口**。

## 二、通过面（52 例，功能面正常）

- 颜色/耗材：m8b 的官方色、彩虹、取色器、颜色应用/取消全部 PASS；
  m3j..m4i 混色族全 GREEN
- 合并链：m8x_152 GREEN（对象标签页行选中 + Change Filament + Merge 全链路）
- 校准族：#206、#207、#208、#209、#210、#211、#212、#213、#218、#221 GREEN；
  #214/#217/#222 仅红在对象行选中/保存提示，功能步骤本身 PASS
- 工程：m8x_199/200/201/202/204/185/186 GREEN（新建/打开/另存/保存/导出 STL/导入）
- 盘操作：m8x_187/188/189/194/195 GREEN（整理/自动定位/移盘/朝向）
- 装配：#20 m8z_assembly_import GREEN
- 其它：m7a/m7c/m7t74、m8a_fit_view、m8x_123、m8x_156、m8x_158、m8x_198、
  m8x_206/207/208/209/210/211/212/213 等 GREEN

## 三、验收结论

1. **本次不判定为通过**：22/74 红；其中 17 例是 plate 重构后的 UI 自动化面
   变化（Add 菜单不弹、右键菜单不弹、导出模式、对象行/选中几何），
   既有基线无法有效覆盖该构建，需要先做自动化适配（本次按要求未改）。
2. **未发现明确的功能回归证据**：已实际执行到的功能面（颜色/混色、合并链、
   校准对话框与切片、工程读写/导出、盘整理/移盘、装配导入）均正常。
3. **需产品/人工复核的 2 点**（自动化不能定论）：
   - m8x_191 绝对 Y 旋转字段 `135.00` / Δ=180° 的行为；
   - m8x_217 新出现的 `Snapmaker Orca - Save` 保存提示是否为新预期行为。
4. 建议顺序：先适配 A（Add/右键菜单）与 B（导出模式）两个入口面，
   再适配 C（对象列表行位置），然后重跑本套件；m8f/m8g 的脚本异常
   与本次构建无关，可单独处理（本次未动）。

## 附：证据位置

- junit：`artifacts/junit.xml`（74 tests / 22 failures）
- 失败清单：`artifacts/failed_cases.txt`
- 逐例日志：客机 `C:\coil\orca-blackbox\artifacts\regress_<case>.log`
- 录屏/归档：客机 `C:\coil\orca-blackbox\artifacts\shots\<case>\`
