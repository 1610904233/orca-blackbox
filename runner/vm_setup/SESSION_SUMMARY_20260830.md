# Hyper-V Win11 自动装机 + GUI 测试迁移 — 会话总结（2026-08-30）

## 最终结果
- **27 个混色 GUI 用例：26 绿 / 1 红**（仅 m4d merge 菜单重开未解，harness 时序问题，非 app bug）
- 快照：`green-baseline`（冒烟后）、`suite-26of27-green`（最终）
- VM：`win11-test`，Win11 Pro 25H2，8 vCPU / 8GB / 1920×1080，自动登录 `test / 123456`

## 关键文件（C:\coil\vm_setup\）
| 文件 | 用途 |
|---|---|
| `relay.ps1` + `relay_cmd.txt` + `relay_out.txt` | **常驻提权中继**（写命令文件→自动执行→输出回 relay_out.txt，免 UAC） |
| `send_to_guest.ps1` | 经 PS Direct 推文件进客机（base64） |
| `guest_run_failed.ps1` / `run_failed` 任务 | 14 红用例批量重跑器 |
| `hv_provision3/4.ps1` | 客机环境部署（Python/Tesseract/mesa/GL 探针） |
| `hv_swap_dvd5.ps1` / `guest_dvd5.iso` | bundle.7z 递送盘 |
| `bundle.7z` | Unicode 安全的 bundle 压缩包（22770 文件，校验通过） |
| `autounattend_schneegans.xml` | Schneegans 生成的应答文件（装机成功的关键） |
| `unattend.iso` | 该应答的 ISO（挂第二光驱） |
| `poll_rerun.txt` | 套件进度轮询命令模板 |

## 根因链（全部实证，按时间）
1. **装机循环 = 重制 ISO 引导层坏**：mkisofs 2.01（本机唯一来源 = VMware 自带）产出不可信。UDF 版更糟：UEFI 层 5 秒三重复位循环（Hyper-V Worker 事件日志 18514/18601 每 5s 一对）。原版微软 ISO 从未有问题 → 放弃重制，**原版 ISO + 第二光驱挂 unattend.iso**（Schneegans 官方生成器产出，支持 24H2/25H2）
2. 手写 autounattend.xml 静默失败（setupact.log 显示"可以无提示安装"但停在语言屏）→ 换 Schneegans 生成版一次通过；但磁盘断言（无分区+容量）失败会退回磁盘选择向导，需手动删分区
3. **"Press any key" 一次性按键**：脚本 hv_boot_presskey.ps1（UAC 提权 + SendKeys）
4. **guest_bundle.zip 是坏包**（839MB，7z 无法打开）→ 重做 bundle.7z；mkisofs 铺 2 万+文件会损坏非 ASCII 目录名（robocopy ERROR 1392 卡死即此）→ ISO 内只放单个 7z
5. **Copy-VMFile 报 0x80070015**（Guest Service Interface 不就绪）→ 改 DVD 递送
6. **app 启动即退 0xC0000135** = 缺 VC++ 2015-2022 运行库（新 Win11 无）→ 客机内下载 vc_redist.x64.exe 静默安装
7. **mesa opengl32.dll 依赖不全** → 全套 x64 dll 拷入 Release；GL 探针需 `os.add_dll_directory(mesa\x64)` → GL 4.6 / D3D12 WARP
8. **PS Direct 无法跑 GUI**（非交互会话，窗口创建失败）→ `Register-ScheduledTask -GroupId "INTERACTIVE"`（不带 -User/-Password，-GroupId 与 -LogonType 互斥）
9. **批量红的最大根因 = VM 分辨率 1024×768**：harness 用宿主校准的固定屏幕坐标（如 map_region=(746,749,1173,780)）检测色块 → `Set-VMVideo 1920×1080`（需 VM 关机设置）后 14 红 → 12 绿
10. 零碎修复：GBK 控制台炸 print ©（`PYTHONIOENCODING=utf-8`）；自动登录密码注册表被 Windows 清空（AutoAdminLogon=0/pw 空）→ 重设 winlogon 三键；TurnOff 硬断电丢文件（用 Stop-VM 干净关机）
11. m4g（编码）绿、m4j（swatch_rows≥1 兜底判定）绿；**m4d 未解**：弹出菜单关闭后重开，同一点击第一次成功后续不弹（hover/排空/中性点击三个补丁均无效，中性点击已回滚）

## 客机内 harness 补丁（建议回流仓库）
- mixing_util.py：wait_match_done 默认 60→300s；各用例 90→420 / 40→240 / 25→180
- m4j_mixing_samecolor.py：`if rows and b_started: b_done = True`
- mix_dialog_util.py：entry_options_menu 行 hover 前置 + 菜单排空（debug 打印仍在，可清理）
- 运行环境：`PYTHONIOENCODING=utf-8`

## 日常跑套件（成熟路径）
1. 确认 relay 存活（`relay_alive.txt` 时间戳新鲜；死了在管理员窗口 `& C:\coil\vm_setup\relay.ps1`）
2. `cp poll_rerun.txt relay_cmd.txt` 轮询进度
3. 单用例：INTERACTIVE 计划任务模板（见 relay_cmd 历史）或 run_failed.ps1 改列表
4. 回滚点：`Restore-VMSnapshot -Name suite-26of27-green`

## 遗留
- m4d menu-reopen 需 VM 内交互调试（inspect_window.py 观察 wx 菜单捕获态）
- mix_dialog_util.py 中的 MDU DEBUG 打印待清理
- 分辨率依赖提示：harness 坐标耦合 1920×1080 + 窗口位置，换环境需重校准（长期应改坐标无关判定）
hv_go.ps1 -Cases @('m3j_mixing_entry')
