# Snapmaker Orca **2.4.1** 基线复跑报告 — 失败用例清单（8 条）

- 日期：2026-10-08
- 被测包：`D:\ruanjian\orca\orca版本\orca2.4.1\Snapmaker_Orca_Windows_V2.4.1_portable.zip`
  → 客机部署为 `C:\coil\apps\Snapmaker_Orca_Windows_V2.4.1_portable\`
  （`snapmaker-orca.exe` FileVersion/ProductVersion = **2.4.1**）
- 运行方式：Hyper-V 客机 `win11-test`，`runner/hv_go.ps1`（唯一入口）
  - 第 1 轮：`-Suite baseline`（36 例）→ **PASS=4 / FAIL=32**
  - 第 2 轮：`-OnlyFailed`（复跑 32 个失败项）→ **PASS=24 / FAIL=8**
- 结论：**首轮 32 个 RED 里 24 个是跑批顺序/状态污染造成的假红**（隔离复跑即转绿）；
  以下 8 条在两种条件下都失败，判定为**真失败**，按形态归成 3 簇。
- 证据：`artifacts/junit.xml`、`artifacts/failed_cases.txt`、
  客机 `artifacts/regress_<case>.log`（复跑那一轮）、`artifacts/videos/`（逐例录像）。

---

## 背景：2.4.1 耗材选择框的规格（产品文档《准备页——耗材分类管理》V0.1，9-29 更新）

需求把耗材下拉框从"一列平铺"改成 **三大分组 + 两级菜单**：

* **三大分组**：`项目预设` / `用户配置` / `系统配置`；其中「项目预设→项目」「用户配置→自定义」
  按"特殊供应商"处理，组内按字典序。
* **系统配置 = 两级菜单**（对齐 Bambu Studio）：
  1. 一级 **供应商**：`Snapmaker` → `Generic` → 其他厂商按字典序（当前仅 Polymaker 排第三）；
  2. 二级 **耗材类型**：按字典序；**供应商 = Snapmaker 时，以下 8 种固定排在最前**（产品给的表）：

     | 耗材 | 排序理由 |
     |---|---|
     | Snapmaker PLA Snapspeed | 销量大 |
     | Snapmaker PLA Matte | 销量大 |
     | Snapmaker PETG HF | 销量大 |
     | Snapmaker PLA Full Spectrum | 多色功能高度适配 |
     | Snapmaker TPU 95A HF | 软料护城河 |
     | Snapmaker PEBA 90A | 软料护城河 |
     | Snapmaker ABS | 顶盖协同，多材料方向 |
     | Snapmaker ASA | 顶盖协同，多材料方向 |

* **选中回显**：二次打开选择框要**自动定位到已选材料**，并去掉一级的高亮。

> 这解释了复跑日志里那串 OCR：
> `'PLA SnapSpeed PLA Matte PETG HF TPU 95A HF PEBA 90A ABS ASA PETG Translucent co'`
> —— 正是 **Snapmaker 供应商的二级列表**（8 个置顶项 + 字典序），说明打开选择框后应用已按
> "回显"停在 Snapmaker 这一层；而用例要找的 `Generic ABS` 在另一条一级分支下、我们自己的
> 测试包（`... - STD-TEST`）在「用户配置/自定义」分组里，**平铺行走永远走不到**。

## 进展（10-10）：换预设原语已按 2.4.1 改版重写

`m8_common.switch_filament_preset` 已支持**双栏两级导航**（保留 2.4.0 平铺兜底）：

- 弹层结构（实测）：左栏 = `------ System presets ------` + `Snapmaker`/`Generic >`/`Aliz >`/…/`eSUN >`
  + `------ Add/Remove filament ------`；右栏 = 该供应商的耗材（**按 ABS/PETG/PLA 类目分组**，
  Snapmaker 层 8 项置顶）；二次打开按"回显"定位到当前耗材。
- 关键点：弹层**必须真实点击**才能打开；**消息级滚轮无效、真实滚轮有效**；
  左栏顶部会被"当前耗材回显行"挤下去 → 找不到厂商时要**先向上滚**。
- 已实测通过：`Generic ABS`（16s，Generic→ABS）、`Snapmaker PLA Silk`（20s，Snapmaker→PLA Silk）。
- 待定：我们的**用户预设**（`Snapmaker PLA SnapSpeed @U1 - STD-TEST` 等）在这个弹层里的位置——
  左栏没有"用户配置/自定义"段、右栏（Snapmaker 供应商）滚动也没命中；datadir 里预设确实存在
  （`…\user\default\filament\…STD-TEST.json`，工艺侧切换也成功），需要测试方指一下它在 UI 里的落点。

## 进展（10-10 晚）：原语改造 + 首条复跑结果

- `m8_common.switch_filament_preset` 已改完（双栏两级导航 + 同厂商回显占位规则 + 2.4.0 平铺兜底），
  并把改后的 `m8_common.py` 投到客机（`-NoSync` 跑，因为它是手工投递、未入库）。
- **`m8c_temp_mix_gate` 已转 GREEN** ✓（`Generic ABS` 走 `Generic → ABS` 成功）。
- `m8b_official_color` / `m8d_purifier_gcode` 仍 RED，剩两类原因：
  1. **右栏耗材行的 OCR 不稳定**：同一栏有时读到预设行（`PLA Translucent/PLA Wood/…`），
     有时只读到类目标题（`ABS/PETG/PLA`）→ 目标行匹配不到（需要提高该栏位的 OCR 精度：
     `scale=3` / 换 psm）。
  2. **槽位行 16×25 按钮的语义变了**：2.4.0 时代它开 Edit/Delete/Merge 菜单（m8b 走
     “Material settings → 取色器”那条路），2.4.1 上它开的是**供应商列表**（实测），
     m8b 的取色链路因此断在第一步（`#48 dialog opens: FAIL (no popup)`）——属于用例级适配。
- 仍待测试方指认：**用户预设**（`Snapmaker PLA SnapSpeed @U1 - STD-TEST` 等）在 2.4.1
  耗材栏里的选入路径（`用户配置→自定义` 只在槽位本身已是用户预设时出现，属于鸡生蛋）
  —— #137 / #125 / m8f / m8g 都卡在这一步。

## 簇 A：换耗材预设失败（5 条）——**最主要的根因**

| 用例 | 飞书 | 失败断言 |
|---|---|---|
| `m8c_temp_mix_gate` | #111 · #112 | `slot2 switches to ABS: FAIL ('Snapmaker PLA Silk')` |
| `m8d_purifier_gcode` | #113 · #122 · #126 · #127 · #128 | `slot2 -> Generic ABS: FAIL ('Snapmaker PLA Silk')` |
| `m8b_official_color` | #44 · #46 · #47 · #48 · #55 · #56 · #58 | `#55 rainbow preset selectable: FAIL ('Snapmaker PLA Silk')`、`cube added: FAIL` |
| `m8x_137_flow_param_tabs` | #137 | `耗材预设 = 流量测试包: FAIL ('Snapmaker PLA SnapSpeed @U1 - FLOW-TEST')`（拿不到 `- STD-TEST` 包） |
| `m8x_125_aux_mix_pref` | #125 | `槽1 = Generic ABS（辅材源）: FAIL ('Generic PETG')` |

**证据（复跑日志原文，`regress_m8c_temp_mix_gate.log` / `m8d` / `m8b`）**

```
[m8] slot2 popup OCR (0 words): ''
[m8] slot2 target 'Generic ABS' not found by OCR (attempt 1/30)
[m8] slot2 popup OCR (16 words): 'PLA SnapSpeed PLA Matte PETG HF TPU 95A HF PEBA 90A ABS ASA PETG Translucent co'
[m8] slot2 target 'Generic ABS' not found by OCR (attempt 2/30)
[m8] slot2 popup OCR (16 words): 'PLA SnapSpeed PLA Matte PETG HF TPU 95A HF PEBA 90A ABS ASA PETG Translucent co'
...（attempt 4 / 6 / 8 的 OCR 文本完全相同）
```

```
# m8x_137：目标 '- ST'（流量测试包后缀）同样读不到
[m8] slot2 popup OCR (8 words): '~ Snapmaker PLA Snapmaker PLA SnapS...| Snapmaker PLA'
[m8] slot2 target '- ST' not found by OCR (attempt 8/30)
```

**判读**：弹窗能打开，但

1. 每次尝试 OCR 到的都是**同一批顶部行**（attempt 2→8 完全一致）→ **列表没有滚动**，
   所以 "Generic ABS" / "Rainbow" / "- STD-TEST" 这些**较深的行根本走不到**；
2. 可见行的文案是**短名/类型名**（`PLA SnapSpeed`、`PLA Matte`、`ABS`、`ASA`…），
   用例按 `Snapmaker PLA Silk` / `Generic ABS` 这类**全名**匹配，口径也不完全对得上。

同一套代码在 2.4.0 上 33/33 全绿，因此这是**2.4.1 上才出现的**现象：
要么弹窗列表的滚动在该版本失效（滚轮事件/滚动条行为变了），
要么预设列表被重排/改名，使目标落在首屏之外。
> 判定影响面：这一簇直接导致 5 条用例失败，且是 #125/#137 这两条新用例失败的主因。

---

## 簇 B：High-Flow 切换后切片被拒（2 条）

| 用例 | 飞书 | 失败断言 |
|---|---|---|
| `m8f_nozzle_flow` | #133 · #135 · #136 | `B slice: FAIL (slice click rejected)` |
| `m8g_flow_single` | #136 | `#136 hf slice: FAIL (slice click rejected)` |

**证据（`regress_m8f_nozzle_flow.log`）**

```
[m8] popup OCR row 'standard'   -> click (344,334)
[m8] popup OCR row 'high flow'  -> click (329,363)
[m7] done-template not found (0.837)
[m3] === verdict ===
  B slice: FAIL (slice click rejected)
```

**判读**：喷嘴 Flow 切到 High Flow 之后，点 Slice 未进入切片（按钮模板既不在 idle 也不在
done），2.4.0 上同一步是绿的。关联事实：2.4.0 时代这一步会先弹一个"确认切片分配喷嘴"的
提示框（`m8_common.confirm_flow_dialog`），本版可能改了提示/门控时机。

---

## 簇 C：变换字段提交失败（1 条）

| 用例 | 飞书 | 失败断言 |
|---|---|---|
| `m7t74` | #152 · #156 · #164 | `move X commits 60: FAIL (now '')`；`rotate Z commits 45: FAIL (now '445559')`；`scale commits 120: FAIL (now '100.00')` |

**判读**：gizmo 数值框在 2.4.1 上"填写 → 回车提交"的结果不对：
move 读回空、rotate 读回 `445559`（像是旧值未清空后拼接）、scale 停在 `100.00`
（输入未生效）。属于**控件行为/焦点差异**，与簇 A 的"鼠标事件在该版本变敏感"可能同源。

---

## 另附：与本轮无关但需要知道的两件事

1. **`Memory Usage Warning` 弹框**：`m8x_125` 复跑日志里出现
   `[m8x125] pref OFF: slice started=True dialog=Memory Usage Warning page=preview`
   —— 该版本在**内存吃紧时会弹"内存占用警告"并继续切片**。它既会打断用例的"按钮应被门禁挡住"判定，
   也说明台架（客机 4GB 级内存）在本轮已接近上限，建议下轮前重启客机、单例复跑时避免长时间连续跑批。
2. **跑批顺序污染是真实存在的**：同一条用例（如 `m3e_preset_switch`、`m4a_mixing_gates`）
   在"整轮连跑"里红、`-OnlyFailed` 单跑就绿。后续若要复现问题，**先单跑**再连跑，
   免得把假红当成构建缺陷。

---

## 复现/取证入口

```powershell
# 宿主（提权或经 relay）
& D:\code\orca_blackbox\runner\hv_go.ps1 -Suite baseline      # 全量 36 例
& D:\code\orca_blackbox\runner\hv_go.ps1 -OnlyFailed         # 只跑 artifacts\failed_cases.txt 里的
& D:\code\orca_blackbox\runner\hv_harvest.ps1                # 拉失败清单 + junit
```
- 每条用例的完整输出：客机 `C:\coil\orca-blackbox\artifacts\regress_<case>.log`
- 逐例录像：客机 `C:\coil\orca-blackbox\artifacts\shots\<case>\<case>_run.mp4`
- 2.4.1 界面只读体检探针：`diag/diag_241_uicheck.py`（菜单/工具条提示均在，排除"界面被删"）

---

# 收敛结论（10-12 会话）：8 条真失败全部转绿

**状态：8/8 GREEN**（逐条在客机复跑确认；全量 36 例基线复跑见下）。

| 用例 | 结论 | 根因（都不是产品逻辑缺陷，是驱动层/环境） |
|---|---|---|
| `m8b_official_color` | ✅ | ① `#48 no popup` 是**坐标二次转换**：槽位色块 rect 来自子窗口 `GetWindowRect`（屏幕坐标），代码又走了一次 `client_to_screen`，点落到色块下方 20px（色块只有 20px 高，+31px 直接出界）。② `#55 rainbow` 上一会话的"Rainbow 默认未启用、需人工勾选"**结论作废**——弹层开在鼠标落点，光标恰好压着 `Generic` 行，右栏显示的是 Generic 的耗材；**Snapmaker 分支里本来就有 `PLA Rainbow`**（截图 `pscan2_Snapmaker_hover.png` 实证，不需要任何人工勾选）。 |
| `m8c_temp_mix_gate` | ✅ | 上一会话的双栏原语重写（`Generic → ABS`）。 |
| `m8d_purifier_gcode` | ✅ | 同厂商内切换（`Generic ABS → Generic PC`）**不能点厂商行**：那行正是"当前展开分支"（高亮渲染，OCR 读不到），插值坐标会点在回显行上把弹层点关；`combo 文本 startswith 厂商` 时直接扫右栏即可。 |
| `m8x_125_aux_mix_pref` | ✅ | 槽 1 `Generic ABS` 切换（当前值已是 Generic → 直接扫右栏）。 |
| `m8f_nozzle_flow` | ✅ | **2.4.1 行为变化**：喷嘴分配确认框从"切流量时"挪到"**点切片时**"——`Custom Filament Grouping`（'Slicing will follow the nozzle assignment below:' / Cancel / Confirm），Confirm 后切片才开始。旧提示查询扑空 → 点击被判 rejected。新增 `m7_common.confirm_filament_grouping()` 在 `op_slice` 失败回退里答框重试。 |
| `m8g_flow_single` | ✅ | 同 m8f；另**导出链静默失败**：3 次超时的消息点击迟到了、把确认框又弹了回来，而 `wait_save_dialog()` 原来"任意 #32770 都算保存框"抓到了这个残留框 → "no Edit child" 静默 False。修：保存框按标题匹配 + 导出前 `_dismiss_stale_prompts()` + 每个 early return 都有诊断打印。 |
| `m7t74` | ✅ | gizmo 网格的"两行合成"启发式被**跨面板的同名词**触发：选项面板的 `Seam position`（y≈830）也 `startswith('position')`，加上面板自身标签比数值行高 10px（>6px 阈值）→ 凭空合成一个**空行**顶到 index 0，用例输错格子/读错格子。修：合成要求"真行距（15~60px）+ 同面板（±60px）"。另 rotate 字段**聚焦渲染**把 OCR 打瞎（字段里明明是 `45`，聚焦态读成 `4`/`4|35`/`445559`）→ 加"点兄弟格去焦后复核再提交"的兜底。 |
| `m8x_137_flow_param_tabs` | ✅ | 用户预设的落点是 `------ User presets ------` → `Custom »` 分组（**只在槽位已是用户预设时出现**——种子的默认值恰好是 `... - FLOW-TEST`，所以门是开着的）；但该分组右栏行**被面板宽度截断**（三行都读成 'Snapmaker PLA'），目标后缀 `- STD-TEST` 永远匹配不到。修：加 **hover tooltip 全名消歧**（tooltip 给出 'PLA SnapSpeed @U1 - STD-TEST' 全名）→ 点中。 |

## 附：本轮固化的 2.4.1 事实（写进 `PITFALLS_0901.md` §21）

1. 探针的控制台窗口会吞掉真实点击（症状酷似"控件没反应"）→ 探针一律 `pythonw.exe` + 自写日志。
2. 子窗口 rect 是屏幕坐标，**不要再 client_to_screen**（m8b 的根因）。
3. 双栏选择框：**hover 即切换右栏**；右栏行文本是短名。
4. 右栏滚动必须 **-1 档 + 每档 OCR**（-3 档跨 ~7 行会跳过目标）；扫描先回顶再向下。
5. 同厂商内切换**不点厂商行**。
6. 行文本被截断时用 **hover tooltip** 拿全名。
7. `filament_allow_list.json` 只是置顶顺序 + high_flow 限制，**不是**可选材料白名单；
   `Add/Remove filament` 是 WebView（HTML，回归用例不碰）。
8. relay 守护只认 `token|脚本路径`（`push_verify.py`/`fetch_file.py` 因此是哑的）——
   文件投放/回传一律走 job 内 base64（字符串分块）。
9. job .ps1 带中文注释必须 **UTF-8 BOM**，否则 PS 5.1 解析崩。
