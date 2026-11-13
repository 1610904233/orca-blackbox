# 最新 2.4.2 包 baseline 全量结果（2026-11-13/14）

- 包：`C:\Users\snapmaker\Desktop\2.4.2\Snapmaker_Orca_Windows_V2.4.2_portable (1).zip`
  - zip MD5 `a250cbbd66e011df9c81c7042fe20545`（167,903,846 B），客机校验一致
  - 客机路径：`C:\coil\apps\orca242_latest\Snapmaker_Orca\snapmaker-orca.exe`
  - 构建标识：exe MD5 `d472049f1c372feff9768eca605491c1`，
    DLL MD5 `0601dd3b11b7332380fefc7d93d530a2`（72,462,368 B），版本 2.4.2
  - 注意：与 orca242d 不是同一构建（exe `8ae99da…` / DLL `77a9225…`）
- 环境：客机 win11-test，1920x1080 交互会话；跑前无残留 orca/python/任务
- 范围：baseline 全量 **74 例**（warmup=True，热身 m2 结果丢弃）
- 结果：**56 PASS / 18 FAIL（通过率 75.7%）**
- 本轮仍遵守「只跑不改」：未修改任何用例、harness 或产品文件。

## 18 个 RED

### 1) 混色族 16 例（m3j–m4i）

对话框本身能打开（m3j `mixing dialog opens: PASS`，默认 Auto PASS），
但打开后的**控件交互**全部失败：

- m3k/m3l/m3m/m3r：`mode switch to Manual = False`，后续 match/rows 连锁失败
- m3s：filament/swatch tooltip 均未出现
- m3t：默认模式 Ratio 断言失败、行 combo/增删行失败
- m3u：配对选择/预设填充/确认登记失败
- m3v/m3x：Cycle/Match tab 切换、输入与手柄校验失败
- m3y：Gradient tab 切换与行选择失败
- m4a/m4b/m4d/m4i：门禁、批量行数、删除/方案登记失败
- m4e：模型选中 / Color Painting 工具提示 / gizmo / 调色板失败

→ 归类：**混色对话框自动化交互面变化**（控件位置/类/OCR 目标），
功能入口存在；m3j 的 `Auto mode gates on nozzle` 是行为断言，需人工确认
门禁是否真的未生效。

### 2) m3e_preset_switch（#159/#166/#182）

- 预设切换本身 PASS；但两次 `switch_to_export_mode` 都失败：
  `topbar print button never reached Export mode`，导致基线导出/重切/
  gcode 差异/头部跟随全部连锁失败。
- 归类：**导出模式入口的自动化面变化**（与 plate 包同症状），不是切片失败。

### 3) m8x_153（#153，部分自动化）

- 两模型重合检测 PASS（blobs intersect）；**整理后分离 FAIL**：
  `blobs=[(1169, 544, 1126, 516, 1203, 571, 1783)]`——整理后仍为单个 blob。
- 归类：可能是 Arrange 后未分离 / 检测面问题，需人工确认。

## 通过面（56 例）

- **校准 13 条 #206–#222 全部 GREEN**（含 #214/#217/#222）
- 工程：m8x_199/200/201/202/204/185/186 GREEN
- 盘操作：m8x_187/188/189/194/195/196/197/198 GREEN
- 建模/编辑：m7b/m7c/m7h/m7t73/m7t75/m7t89、m8x_190/191/192/193/203 GREEN
- 颜色/耗材：m8b/m8c/m8d/m8e/m8f/m8g/m8x_123/m8x_137/m8x_125 GREEN
- 合并链 m8x_152、装配 #20、Fit m8a 等 GREEN

## 结论

1. 该构建**未达到全绿验收**：56/74；18 红集中在混色对话框交互（16）、
   导出模式入口（1）、Arrange 后分离（1）。
2. 17/18 有明确的「自动化面」证据（对话框已开、预设切换已成功、
   失败在控件交互/导出入口），不能直接判为产品功能缺陷。
3. 需人工/产品复核 2 点：
   - m3j 的 Auto 模式喷嘴门禁是否真的未拦截（`warning: None`）；
   - m8x_153 整理后两对象是否仍未分离。
4. 证据：`artifacts/junit.xml`（74 tests / 18 failures）、
   `artifacts/failed_cases.txt`、客机 `artifacts/regress_<case>.log` 与
   `artifacts/shots/<case>/`。


## 重跑失败的 18 例（2026-11-14）

- 命令：`hv_go.ps1 -OnlyFailed -Exe <latest 2.4.2>`（无热身轮）
- 结果：**17 PASS / 1 FAIL**（junit 18 tests / 1 failure）
- 首轮 18 红中 **17 条重跑转绿**：m3e、m3j、m3k、m3l、m3m、m3r、m3s、m3t、
  m3u、m3v、m3x、m3y、m4a、m4b、m4d、m4e、m4i
  → 首轮混色族/导出模式的 RED 是**不稳定/交互时序**，不是稳定产品缺陷。
- 唯一稳定红：**m8x_153**（#153，部分自动化）
  - 两模型重合检测 PASS；Arrange 后仍只有 1 个 blob：
    `blobs=[(1169, 544, 1126, 516, 1203, 571, 1783)]`
  - 本构建 2/2 次一致；plate 包上也红 → 需人工确认 Arrange 是否真的未分离，
    或测试的 blob 分离判据（两对象投影粘连）是否过严。
  - 录屏：`artifacts/m8x_153_plate_run.mp4`（15,102,193 B，01:50:51）
- 结论修正：m3j 的 Auto 门禁在重跑中 PASS，不能据此判产品缺陷；
  m8x_153 是唯一需要在人工界面上复核的行为。
