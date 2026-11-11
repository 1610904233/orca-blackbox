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

## 下一步（建议）

1. **F-10、F-8 优先给开发侧**——最像真回归（选中失效 / UI-gcode 脱钩）；
2. F-7/F-9/F-11 与产品确认是否有意变更；F-1/F-2 人工真机确认；
3. F-3 丢字间歇发作（m8x_190 两红一绿），开发侧查文本输入消息泵。
