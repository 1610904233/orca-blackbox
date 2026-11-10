# 242_RUN_REPORT — Orca 2.4.2（orca242d）全量复跑分类报告

- 日期：2026-11-10 晚（全量 18:55 启动，约 21:40 完成 + 补跑）
- 包：`C:\coil\apps\orca242d\Snapmaker_Orca\snapmaker-orca.exe`（exe md5 8ae99da…）
- 宿主 HEAD：a33213b；客机 checkout 与 origin 同步（全量经 hv_go 正常 sync）
- 对比：2.4.1 基线 57/57 GREEN；2.4.2c 首轮 6/51

## 结果总览

**全量 57 例：PASS=46 / FAIL=11**；补跑后有效结果 **47/57 GREEN**：
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

### 测试侧标定（4 例，下一会话工作项）

| 用例 | 待修 |
|---|---|
| m8a_fit_view | Fit 按钮固定点击位（VP_X0+152, h-44）在 242d 疑漂移（#18 证明 Fit 功能本身有效）+ 多盘盘面检测为空 |
| m8x_152 | 缩放提交 + ESC 后 strict select 点击预算耗尽（需看归档帧定位抑制源） |
| m8x_153 | 舱 1 官方色 chip 定位器坐标 (23,425) 落空 ×3（同批 m8b 同流程绿 → 定位器分支问题） |
| m8x_156 | Move 拖拽箭头偶发脱靶（同会话 rotate/scale 拖拽均 PASS） |

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

## 下一步（建议）

1. F-8（UI 显示弱冷但 gcode 强冷）优先给开发侧——最像真回归；
2. 4 例测试侧标定（m8a/m8x_152/m8x_153/m8x_156）逐个探针重标后 -OnlyFailed 补跑；
3. F-1/F-2（tooltip 劣化、Add 下拉抑制）需人工在真机确认用户路径是否受影响。
