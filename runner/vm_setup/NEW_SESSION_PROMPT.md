# 新会话排查任务：Hyper-V Win11 自动装机无限重启循环（对抗性复盘）

## 你的首要任务
我（前一个会话）在 Hyper-V 上建 Win11 自动装机 VM 时陷入**无可见错误的重启循环**，多轮修复未果。请：
1. 先通读下面的"完整排查史"和"我的可疑决策清单"，**对抗性地审查我的每条假设**——我的 several 结论可能根本就是错的
2. 优先执行"决定性诊断"（读 VHDX 里的 Panther 日志——这条我没来得及做，它能直接揭示安装器死因）
3. 修复装机，然后继续后续自动化（脚本全部已备好）

## 大背景（为什么做这件事）
宿主机（Win10 专业版 22H2 / AMD iGPU / 32GB / 16 核 / WSL2 已启用即 Hyper-V 平台已激活 / 装有 GameViewer 远控层）上已经有一套**在宿主桌面运行且 27/27 全绿**的 GUI 黑盒测试套件（Snapmaker Orca 混色功能，视觉+真实输入驱动）。目标：把这套测试迁进 VM 无感运行。选定了 Hyper-V 原生路线（用户确认）。VMware 26H1 路线已因 ULM 共存崩溃潮放弃（社区有大量同款报告）。

## 当前卡点
Hyper-V Gen2 VM `win11-test` 从重制的 Win11 安装 ISO 引导后**无限重启循环，无可见错误提示**。循环表现：WinPE 转圈/黑屏 → 重启 → 循环。用户观察不到任何错误画面。CPU 占用有 7-8% 波动后归零的循环模式。

## 关键文件（C:\coil\vm_setup\）
- `Win11_25H2_English_x64.iso` — 微软官方原版 ISO（未修改）
- `win11-setup.iso` — 我重制的 ISO（8.42GB）：mkisofs -J -r -udf、BCD 大写、efisys 换 noprompt、install.wim 已拆分为 install.swm+install2.swm（<4GB）、autounattend.xml 在根目录（XML 已校验合法）
- `autounattend.xml` — 完整应答：windowsPE（LabConfig 绕过 TPM/SecureBoot/CPU/RAM/Storage 检查 + GPT 分区 EFI200/MSR16/主分区 + Win11 Pro index 6 apply）+ specialize + oobeSystem（本地账号 test/Passw0rd! 自动登录、跳 OOBE、powercfg 禁睡眠、marker C:\setup_done.txt）
- `win11.vhdx` — 100GB 动态磁盘（已 GPT 分区：S:=EFI 200MB / W:=Windows；dism apply 从未成功过，所以磁盘是空的或只有残迹）
- `hv_hyperv_setup.ps1` / `hv_create_vm.ps1` / `hv_apply_continue.ps1` / `hv_orchestrate.ps1` / `hv_provision.ps1` / `hv_run_all.ps1` — 各阶段脚本（hv_provision 在客户机内运行：解包 guest_bundle.zip → 装 Python 3.11/Tesseract/mesa 软件 GL → GL 探针 → 完成 marker）
- `guest_bundle.zip`（879MB）— 客户机全部资产（app Release + 黑盒工作树 resources/tests/vision_gui + python/tesseract 安装器）
- `NEW_SESSION_PROMPT.md` — 本文件

## 完整时间线与证据
1. VMware Workstation 26H1 路线：多层崩溃（LSI 控制器移除 / VNC 服务 / HW19+ 设备初始化 0xc0000005 / 自制 ISO 触发 CD init 崩溃）→ 社区证实 25H2/26H1 有崩溃潮 → 放弃。**教训：VMware 需 WHP/ULM 共存模式（本机 WSL2 强制），AMD 主机是重灾区**
2. 改 Hyper-V 原生。用户手动执行 hv_enable.ps1 成功（vmms Running，免重启）
3. 宿主 dism /Apply-Image Win11 25H2 install.wim → **Error 87 / 0x80070057**：
   - 我先猜"PowerShell 引号转义尾反斜杠"→ 用户手动输入带尾反斜杠仍 87 → **该猜测已被证伪**
   - 当前最可能：**Win10 19041 的 DISM/wimgapi 不支持 Win11 25H2 的 WIM 格式**（未验证）。DISM 日志：C:\Windows\Logs\DISM\dism.log（genericimagingmanager.cpp InternalCmdWimApply hr=0x80070057）
4. 改走媒体引导安装：Gen2 VM 挂原版 ISO + autounattend 数据 ISO
   - Secure Boot 模板问题已修（默认模板报 "boot loader failed"；处理后出现 Press any key 提示）
   - 用户按空格 → WinPE 转圈 → 又退回提示 → **无可见错误**
5. 为免按键+合一媒体，重制了 win11-setup.iso（noprompt 引导 + autounattend 内置 + swm）→ **循环重启**至今
6. 期间发现并修过：autounattend.xml 曾非法（wcm 前缀未声明，已修+校验通过）；BCD 文件名大小写（bcd→BCD，已修）
7. 尝试过 Set-VMFirmware -SecureBootTemplate MicrosoftWindowsTemplate → 报"matches none of the secure boot templates"（这台 Hyper-V 的模板枚举名不同，未深究）；**当前 VM 的 Secure Boot 状态未知**

## 决定性诊断（请最先做这个）
**重启循环几轮后，从宿主挂载 VHDX 读安装器日志**（此时客户机没系统也能读）：
```powershell
# 管理员 PowerShell
Stop-VM win11-test -TurnOff
Mount-VHD -Path C:\coil\vm_setup\win11.vhdx
# 找到挂载盘符（Get-Volume），然后：
Get-ChildItem <盘>:\ -Force          # 看是否已有 Windows 目录/分区内容
Get-Content <盘>:\$WINDOWS.~BT\Sources\Panther\setupact.log -Tail 50 -ErrorAction SilentlyContinue
Get-Content <盘>:\$WINDOWS.~BT\Sources\Panther\setuperr.log -Tail 50 -ErrorAction SilentlyContinue
Get-Content <盘>:\Windows\Panther\unattend.xml -ErrorAction SilentlyContinue  # 应答是否被读到
Dismount-VHD -Path C:\coil\vm_setup\win11.vhdx
```
- 若盘是空的/无 Panther → 说明 autounattend 根本没被读到（Media/枚举问题），或 setup 在 WinPE 早期就挂
- 若有 setuperr.log → 错误码直接定位
- 顺带确认：win11.vhdx 的 GPT 分区结构（EFI/MSR/主分区）是否被应答文件的 DiskConfiguration 正确创建

## 我的可疑决策清单（对抗重点）
1. **我认定 dism 87 = WIM 格式不兼容**——只排除了引号转义，未验证格式假设本身。也许 87 另有原因（如 /ApplyDir 盘符状态、wim index 选择、SWM 与 wim 混用），若 DISM 可用则宿主 Apply-Image 路线反而更简单
2. **我重制的 ISO 可能结构性不兼容**：老版 mkisofs 的 -J -r -udf 组合产出的 El Torito/UDF 结构，Hyper-V 的 cdboot/WinPE 链条可能读一半就断（症状：WinPE 转圈后无提示重启）。备选：用微软 ADK 的 oscdimg 重建（-bootdata 双引导 + -u2 -udfver102），或干脆不重制 ISO
3. **bootOrder 理论（DVD 优先导致安装重启循环）未证实**——我据"noprompt 媒体会无限重进 setup"推理，但没有实证看过第二次重启后的行为
4. **autounattend 的 DiskConfiguration/RunSynchronous 细节**：LabConfig reg add 命令、GPT 分区脚本、/IMAGE/NAME 元数据选择（对 install.swm 是否生效）——都可能出错且静默
5. **根本方向质疑**：Win11 25H2 媒体在"Win10 宿主的 Hyper-V Gen2"上是否本来就有引导兼容问题？换 Win11 23H2/24H2 ISO 或 Win10 ISO 对照一次即可分辨
6. 用户侧 UAC 弹窗多次被取消（原因不明，可能与远控层有关）——需要提权的操作尽量让用户在管理员窗口手动粘贴

## 可用资产与正确性
- 宿主黑盒套件（vision_gui 沙盒）27 用例已全绿——迁移目标就是把它们跑进 VM
- guest_bundle.zip 已含：app Release（snapmaker-orca.exe + 全部 DLL）+ 黑盒工作树（resources 预设源 / tests\data fixtures / vision_gui 沙盒含全部用例与 harness）+ python3.11/tesseract 安装器
- 客户机内的路径镜像宿主：C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\... 与 C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe，用例脚本无需改动即可在客户机运行
- GL：Gen2 无虚拟 GPU → 客户机用 mesa 软件 GL（C:\coil\vm_setup\mesa-dist-win.7z + 7zr.exe 已备，opengl32.dll 放 app exe 旁即可；llvmpipe GL 4.5 满足应用 3.3 需求）

## 成功标准
1. win11-test VM 无人值守完成 Win11 安装并自动登录（test/Passw0rd!）
2. GL 探针显示可用 GL（llvmpipe 也算）
3. 冒烟用例 m3j 在客户机内 GREEN
4. Checkpoint-VM 快照 green-baseline
5. 之后回归 = 回滚快照 → 跑 27 用例 → 宿主零干扰

## 风格约束
- 所有宿主 VM 操作需管理员 PowerShell（用户可手动粘贴命令，或你触发 UAC 由用户点确认——注意 UAC 弹窗曾被多次取消，尽量合并提权操作）
- 不要动 C:\coil\vm_setup 之外的宿主状态；不要卸载 WSL2；不要卸载 VMware（已停用即可）
- 每个实验先写假设与判据，执行后如实回报；卡死时优先补可见性（日志/截图）而不是继续盲改
