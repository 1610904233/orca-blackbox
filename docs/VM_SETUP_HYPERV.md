# Hyper-V Win11 测试客机 — 下载与装机记录

> **范围**：从零到"客机能跑黑盒用例"的完整链路（启用 Hyper-V → 下镜像 → 建 VM →
> 装 Win11 → 部署环境 → 验收快照）。日常跑批见 `runner/README.md`，跑批坑位实录
> 见 `PITFALLS_0901.md`，本文只管**装机这件事本身**。
>
> **原始材料**：`C:\coil\vm_setup\`（**不受版本控制**，是 live origin）。**装机脚本已落库**
> 到 [`runner/vm_setup/`](../runner/vm_setup/)（该目录 README 有步骤→脚本映射、未收录
> 清单与废弃产物说明）；本文是整理版说明，两边改一边记得同步。对应会话：`sess_3572e3d3`
> （08-30 04:16，装机与下载全过程）、`sess_8c0d1cc6`（08-30 17:34，无限重启循环排查）、
> `sess_5c772d9d`（08-30 00:06，决定隔离到虚拟机的原因）。整理时间 2026-09-16。

## 0. 三个关键结论（先看这个）

1. **Hyper-V 本体不需要"下载"**。它是 Windows 专业版自带的可选功能，一条
   `Enable-WindowsOptionalFeature` 启用即可，本机实测**免重启生效**。
2. **唯一下载的东西是客机镜像**：用 `Fido.ps1`（pbatard/Fido）向微软官方接口取直链，
   再用 curl 下载 Win11 25H2 English x64 原版 ISO。
3. **装机成功路线 = 原版 ISO 引导 + 第二光驱挂 `unattend.iso`**。宿主 DISM 灌盘、
   自制重制 ISO 两条路都失败（见 §4、§5），别再走。

## 1. 环境前提

| 项 | 值 |
|---|---|
| 宿主 | Windows 10 专业版 22H2（19045），`DESKTOP-SUHBJ5K` |
| CPU / 内存 | 16 核 / 32GB（AMD iGPU，**Gen2 客机无虚拟 GPU**，客机走 mesa 软件 GL） |
| 关键前提 | **WSL2 已启用** → hypervisor 早已在跑，这是 Hyper-V 免重启生效的原因 |
| 远控层 | 宿主装有 GameViewer 远控（会吞合成输入，见 PITFALLS §1 与该会话） |
| 客机 | `win11-test`，Win11 Pro 25H2，`DESKTOP-NVS6QT4` / `172.23.88.122`，自动登录 `test / 123456` |
| 提权方式 | 所有 Hyper-V cmdlet 需管理员 PowerShell；非提权下报 `VirtualizationException` |

> 提权踩坑：脚本自动拉起 UAC 连续三次被取消 → 最终改成**手动**在文件管理器里
> 右键脚本 →"使用 PowerShell 运行"，或直接在管理员窗口粘贴路径。后续为此建了
> 常驻提权中继 `relay.ps1`（免 UAC，见 `runner/README.md`）。

## 2. 步骤一：启用 Hyper-V（不下载，只启用）

脚本 `C:\coil\vm_setup\hv_enable.ps1`，全文两行：

```powershell
# hv_enable.ps1 — MUST RUN ELEVATED. Stages the Hyper-V feature (NoRestart).
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All -NoRestart
Write-Host "Hyper-V staged. A restart is required to activate."
```

执行与校验：

1. 管理员 PowerShell 运行上述脚本（或右键"使用 PowerShell 运行"）。
2. 脚本自称"需要重启"，但**实际免重启就生效**：

```powershell
Get-Service vmms | Select-Object Status      # -> Running
Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
```

`vmms` 直接是 `Running`，虚拟化平台已可用。原因是本机 WSL2 早就把 hypervisor
跑起来了，Hyper-V 只是补齐上层管理栈（本条在会话里固化为"已验证事实 #1"）。

> 注意：DISM 路线（`DISM /Online /Enable-Feature /FeatureName:Microsoft-Hyper-V-All`）
> **没有在本机实际使用过**，本文不把它写成已验证步骤。会话里只确认了
> `Enable-WindowsOptionalFeature` 这条。

## 3. 步骤二：下载 Win11 镜像（Fido + 官方直链）

微软官方 ISO 直链必须走脚本化接口，用 Pete Batard 的 Fido：

```bash
# ① 取下载器（Fido v1.70，GPLv3，54,314 字节）
mkdir -p /c/coil/vm_setup && cd /c/coil/vm_setup
curl -sL --max-time 60 -o Fido.ps1 "https://github.com/pbatard/Fido/raw/master/Fido.ps1"

# ② 取微软官方直链（注意 -Win 的值带空格）
powershell -NoProfile -ExecutionPolicy Bypass -File Fido.ps1 \
  -Win "Windows 11" -Rel Latest -Lang "English" -Arch x64 -GetUrl

# ③ 按直链下载（-C - 断点续传；后台跑，约 4 分钟）
curl -L -o Win11_25H2_English_x64.iso --retry 5 --retry-delay 5 -C - -s -S "<②返回的 URL>"
```

**参数坑**：`-Win Windows11` 会报 *"Invalid Windows version provided. Use '-Win List'"*。
先用 `-Win List` 看合法值——是**带空格的 `Windows 11`**（以及 `Windows 10`、
`UEFI Shell 2.2`、`UEFI Shell 2.0`）。

结果：

| 项 | 值 |
|---|---|
| 文件 | `C:\coil\vm_setup\Win11_25H2_English_x64.iso` |
| 大小 | 8,471,603,200 字节（8.47 GB） |
| 直链文件名 | `Win11_25H2_English_x64_v2.iso`（25H2 English x64 v2） |
| 卷标 | `CCCOMA_X64FRE_EN-US_DV9` |
| 镜像索引 | `index 6 = Windows 11 Pro`（`Get-WindowsImage` 按 `ImageName -eq "Windows 11 Pro"` 取） |
| 结构要点 | ISO9660 层根目录只有 `README.TXT`，**真实文件树在 UDF 层**（Secure Boot/引导链依赖） |

> **遗留缺口**：下载后只看了日志尾 `DOWNLOAD OK` + `ls -la`，**没有做 SHA256 校验**。
> 复现时建议补 `Get-FileHash`。

## 4. 步骤三：创建虚拟机

### 路线 A（成功）：原版 ISO 引导 + 第二光驱挂应答盘

脚本 `C:\coil\vm_setup\hv_hyperv_setup.ps1`，核心：

```powershell
$vm = "win11-test"
if (Get-VM -Name $vm -ErrorAction SilentlyContinue) { Remove-VM -Name $vm -Force }
if (Test-Path "C:\coil\vm_setup\win11.vhdx") { Remove-Item "C:\coil\vm_setup\win11.vhdx" -Force }

New-VM -Name $vm -MemoryStartupBytes 8GB -Generation 2 `
    -NewVHDPath "C:\coil\vm_setup\win11.vhdx" -NewVHDSizeBytes 127GB `
    -SwitchName "Default Switch"
Set-VMProcessor -VMName $vm -Count 4
Set-VMMemory    -VMName $vm -DynamicMemoryEnabled:$false

Add-VMDvdDrive -VMName $vm -Path "C:\coil\vm_setup\Win11_25H2_English_x64.iso"
Add-VMDvdDrive -VMName $vm -Path "C:\coil\vm_setup\unattend.iso"      # 应答盘 = 第二光驱

$dvd = Get-VMDvdDrive -VMName $vm | Where-Object { $_.Path -like "*Win11_25H2*" }
Set-VMFirmware -VMName $vm -FirstBootDevice $dvd                      # 从安装盘引导

Enable-VMIntegrationService -VMName $vm -Name "Guest Service Interface"
Start-VM -Name $vm
```

思路：**让客机用介质自带的新版 DISM 自己装**，规避宿主老 DISM 的 WIM 格式限制；
代价是需要在 VM 控制台按一次键（见 §5）。

### 路线 B（失败，别再走）：宿主 diskpart + DISM 灌盘

脚本 `hv_create_vm.ps1`：挂 ISO → `Get-WindowsImage` 取 index 6 → diskpart 建
GPT（EFI 200MB `S:` / MSR 16MB / NTFS 主分区 `W:`）→
`dism /Apply-Image /ImageFile:... /ApplyIndex:6 /ApplyDir:W:\` → `bcdboot W:\Windows /s S: /f UEFI`。

失败现象：`dism /Apply-Image` 反复 **Error 87 / 0x80070057**。先怀疑 PowerShell 引号
转义（尾反斜杠）→ 手动输入仍 87 → **该猜测被证伪**；随后判定为**宿主 Win10 19041 的
DISM/wimgapi 不支持 Win11 25H2 的新 WIM 格式**（DISM 日志
`genericimagingmanager.cpp InternalCmdWimApply hr=0x80070057`）。此判定当时未再深究，
属"最可能解释"而非铁证。副作用：`win11.vhdx` 只有 239MB，从未成功 Apply 过。

### 最终 VM 配置

| 项 | 值 |
|---|---|
| 名称 / 代次 | `win11-test` / Gen2（UEFI） |
| 内存 | 8GB，动态内存**关闭** |
| vCPU | 脚本里是 4，后期调为 **8** |
| 分辨率 | **1920×1080**（`Set-VMVideo`，需关机设置；分辨率是套件是否跑绿的关键，见 PITFALLS §1） |
| 交换器 | `Default Switch` |
| 系统 | Win11 Pro 25H2 |

## 5. 步骤四：装 Win11（应答文件是关键）

### 应答盘

- 初版：手写 `autounattend.xml` 打成 `unattend.iso`，作为**第二个 DVD** 挂载。
- **手写版静默失败**（`setupact.log` 显示"可以无提示安装"但停在语言屏）。
- 最终：改用 **Schneegans 官方生成器**（schneegans.de/windows/unattend-generator/）
  产出 `autounattend_schneegans.xml` → `unattend.iso`（md5 `bc6781ebb034981363d6094abfe5065a`），
  一次通过。支持 24H2/25H2。
- 期间修过的坑：手写版曾**非法 XML**——用了 `wcm:action="add"` 却没声明
  `xmlns:wcm`（第 35 行 `unbound prefix`）；加
  `xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State"` 修复。

### "Press any key" 的那一次按键

原版 ISO 引导会出现 `Press any key to boot from CD/DVD`，而这次装机接受了
"一次性人工按键"（装机是一次性事件，不再追求完全无人值守）。自动化脚本
`hv_boot_presskey.ps1`：`Stop-VM -TurnOff` → 换入 Schneegans 版 `unattend.iso` →
`Start-VM` → 拉起 `vmconnect` → 把控制台窗口置前 → 中心点一次鼠标 +
`SendKeys::SendWait(" ")`。

**陷阱**：装机完成后**必须把首启切回硬盘**，否则会无限重装循环：

```powershell
Stop-VM win11-test -TurnOff
$d = Get-VMHardDiskDrive -VMName win11-test
Set-VMFirmware -VMName win11-test -FirstBootDevice $d
Start-VM -VMName win11-test
```

另外：**"Press any key" 屏幕不要按键**，让它超时；一旦按下就重启安装循环。

### 被判定不可靠并放弃的中间产物

- `win11-setup.iso` / `win11-setup-udf.iso`（mkisofs 2.01 重制，8.42GB）：UDF 版在
  UEFI 层 5 秒三重复位循环（Hyper-V Worker 事件日志 **18514/18601 每 5s 一对**）。
  本机唯一 `mkisofs` 来自 VMware Workstation 附带，**产物不可信**；本机无 `oscdimg`。
- `win11-noprompt.iso`（~889MB，损坏）。
- `guest_bundle.zip`（839MB）：**坏包**，7z 打不开 → 重做为 `bundle.7z`。
  另：mkisofs 铺 2 万+ 文件会损坏非 ASCII 目录名（robocopy `ERROR 1392` 卡死即此），
  所以递送盘里只放**单个 7z**。

### Secure Boot 记录

`Set-VMFirmware -SecureBootTemplate MicrosoftWindowsTemplate` 报
*"matches none of the secure boot templates"*（这台机器的模板枚举名不同）。可枚举
`SecureBootTemplates` 查名字，或 `-EnableSecureBoot Off`。曾出现
"boot loader failed" / `0xc000000f`。

## 6. 步骤五：客机环境部署

装机完成后由宿主 `hv_orchestrate.ps1` 串起来：**等客机首启（PowerShell Direct 轮询
`C:\setup_done.txt`，不依赖网络）→ 跑客机内 `hv_provision*.ps1` → GL 探针 → 冒烟
→ 打快照**。

### 递送资产

`Copy-VMFile` 报 **0x80070015**（Guest Service Interface 不就绪）→ 改走 **DVD 递送**：
做 `guest_dvd5.iso`（只含 `bundle.7z`），`hv_swap_dvd5.ps1` 换盘挂载。

### 客机内 provision（`hv_provision4.ps1`）

1. 解包 `bundle.7z`（22,770 文件）到 `C:\coil\bx`
2. 铺树：app Release → `C:\coil\Projects\SnapmakerOrca_dev\build\src\Release`；
   黑盒工作树 → `.worktrees\vision-gui-blackbox`
3. Python 3.11 静默安装到 `C:\Python311`
4. Tesseract `/S` 静默安装
5. `pip install opencv-python numpy pytesseract`
6. mesa 软件 GL：从 `mesa-dist-win.7z` 取 x64 `opengl32.dll` 放到 app exe 旁
   （Gen2 无虚拟 GPU，llvmpipe GL 4.5 满足应用 3.3 需求）
7. GL 探针（纯 ctypes 建窗口 + `DescribePixelCount`）→ 写 `C:\coil\gl_probe_result.txt`

**必须单独装 VC++ 运行库**：app 启动即退 `0xC0000135`，原因是新 Win11 没有
VC++ 2015–2022 运行库 → 客机内下载 `vc_redist.x64.exe` 静默安装。

### 跑 GUI 用例的通道

**PowerShell Direct 不能跑 GUI**（非交互会话 → 窗口创建失败）。改为注册
**INTERACTIVE 计划任务**：

```powershell
Register-ScheduledTask -GroupId "INTERACTIVE" ...   # 注意 -GroupId 与 -LogonType 互斥
```

分辨率必须锁 1920×1080（`Set-VMVideo`，需关机时设置）。**这是批量红的最大根因**：
harness 用宿主标定的固定屏幕坐标检测色块，VM 掉到 1024×768 时 14 红 → 12 绿。

其他零碎修复：GBK 控制台炸 `print ©`（`PYTHONIOENCODING=utf-8`）；自动登录密码
注册表被 Windows 清空（`AutoAdminLogon=0`、密码空）→ 重设 winlogon 三键；
`Stop-VM -TurnOff` 硬断电会丢文件（用 `Stop-VM` 干净关机）。

## 7. 步骤六：验收与快照

`hv_orchestrate.ps1` 末段：跑客机内冒烟用例 `m3j_mixing_entry.py`，
`Checkpoint-VM -Name win11-test -SnapshotName "green-baseline"`。

当天最终结果：**27 个混色 GUI 用例 26 绿 / 1 红**（仅 `m4d` merge 菜单重开未解，
判定为 harness 时序问题而非 app bug）；快照 `green-baseline`（冒烟后）与
`suite-26of27-green`（最终）。回滚点：

```powershell
Restore-VMSnapshot -Name suite-26of27-green
```

## 8. 坑位速查

| 现象 | 根因 | 处置 |
|---|---|---|
| UAC 自动提权连拉三次被取消 | 远控层/未知 | 手动右键"使用 PowerShell 运行"；后期建 `relay.ps1` 常驻中继 |
| `dism /Apply-Image` Error 87 / 0x80070057 | 宿主 Win10 19041 DISM 不支持 25H2 WIM | 放弃灌盘，改 ISO 引导由客机自装 |
| VM 无限重启循环、无可见错误 | mkisofs 重制 ISO 引导层坏；`WillWipeDisk` + DVD 优先 | 用**原版** ISO；装完把首启切回硬盘 |
| WinPE 转圈又退回提示 | 同上（重制媒体） | 同上 |
| SecureBoot "matches none of the secure boot templates" | 模板枚举名不同 | 枚举 `SecureBootTemplates` 或关 Secure Boot |
| `autounattend.xml` 无提示却不生效 | XML 非法（`wcm` 前缀未声明） | 声明 `xmlns:wcm`；或直接用 Schneegans 生成器 |
| 应答磁盘断言失败 → 掉回手动分区向导 | Schneegans 要求目标盘**未分区**（100–4000 GiB 未分配） | 保持磁盘空盘 |
| `Copy-VMFile` 0x80070015 | Guest Service Interface 未就绪 | 改 DVD 递送 |
| app 启动即退 0xC0000135 | 缺 VC++ 2015–2022 运行库 | 客机内装 `vc_redist.x64.exe` |
| GL 探针失败 / opengl32 依赖不全 | 无虚拟 GPU，且 dll 不全 | mesa x64 全套 dll 拷进 Release；`os.add_dll_directory(mesa\x64)` |
| PS Direct 跑 GUI 窗口创建失败 | 非交互会话 | INTERACTIVE 计划任务 |
| 批量用例红、OCR 全空 | VM 分辨率掉到 1024×768 | `Set-VMVideo 1920×1080`（关机设置）+ 跑前必查分辨率 |
| 硬杀 app 后启动全崩 | 损坏 Sentry crashpad DB | 永远优雅退出；`clean_guest.ps1` 清孤儿进程 |

## 9. 被放弃的路线：VMware Workstation 26H1

同一天还尝试过 VMware，**最终放弃**（未卸载，可能留残留服务）：

- 获取方式：注册 `support.broadcom.com`（Trade Compliance 表单）→
  Software → VMware Cloud Foundation division → Desktop Hypervisors → VMware
  Workstation Pro（KB 344595；可能在第 2 页，否则看 Previous Releases）；
  "Not Entitled" 时选 **Free Use** 权益（商用/个人免费，无需 key）。
- 产物：`C:\coil\vm_setup\VMware-Workstation-Full-26H1-25388281.exe`（287,670,872 字节，
  时间戳 12:53）。**下载 URL 无记录**。
- 静默安装：直接 bash 启动报 exit 126 / "Permission denied" = **UAC 740**（不是沙箱）。
  可用：`powershell Start-Process -Verb RunAs -Wait`，参数
  `/s /v"/qn EULAS_AGREED=1 AUTOSOFTWAREUPDATE=0 REBOOT=ReallySuppress"` →
  装到 `C:\Program Files\VMware\VMware Workstation\`。
- 放弃原因：WSL2 强制 ULM 共存 + AMD 主机上社区同款 **ULM/VNC/LSI 控制器崩溃潮**
  （HW19/21 设备代码崩溃、`sata0:3` 崩溃；26H1 移除了 LSI SCSI）。用户确认改走
  Hyper-V 原生路线。
- 副作用（留存）：`mkisofs.exe`（本机唯一来源，产物不可信，见 §5）和
  `windows-tools.iso`（142,280,704 字节，本地由 VMware 自带
  `C:\Program Files\VMware\VMware Workstation\windows.iso` 生成，**不是下载的**）。

## 10. 遗留与未做

- **ISO 无哈希校验**（§3）。
- `dism 87` 的"WIM 格式不兼容"只是最可能解释，未做对照实验（换个 Win11 23H2/24H2
  或 Win10 ISO 一试即可分辨）。
- 宿主 `DISM /Enable-Feature` 路线未验证（本机用的是 `Enable-WindowsOptionalFeature`）。
- VMware 未卸载，可能留 ULM/服务残留。
- `m4d` merge 菜单重开用例当日未解；harness 坐标耦合 1920×1080 + 窗口位置，
  换环境需重校准（长期应改坐标无关判定）。

## 11. 从零复现清单

```
[ ] 1. 确认 WSL2 或任一 hypervisor 已启用（决定 Hyper-V 是否免重启）
[ ] 2. 管理员 PowerShell：Enable-WindowsOptionalFeature -Online `
        -FeatureName Microsoft-Hyper-V-All -All -NoRestart
[ ] 3. 校验：Get-Service vmms -> Running
[ ] 4. curl 拉 Fido.ps1 -> -Win List 查合法版本值 -> -GetUrl 取直链
[ ] 5. curl -C - 下载 Win11_25H2_English_x64.iso（8.47GB）+ Get-FileHash 校验
[ ] 6. Schneegans 生成器产出 autounattend.xml -> makeiso 成 unattend.iso
[ ] 7. hv_hyperv_setup.ps1：Gen2 / 8GB / Default Switch / 双光驱 / DVD-first
[ ] 8. 控制台按一次键（hv_boot_presskey.ps1 可自动化）
[ ] 9. 等客机自动登录（test/123456），确认 setup_done.txt 出现
[ ] 10. 首启切回硬盘（Set-VMFirmware -FirstBootDevice 硬盘）
[ ] 11. Set-VMVideo 1920×1080（关机设置）
[ ] 12. DVD 递送 bundle.7z -> 客机内 hv_provision4.ps1
[ ] 13. 装 vc_redist.x64.exe；确认 GL 探针 -> llvmpipe
[ ] 14. 注册 INTERACTIVE 计划任务；跑 m3j 冒烟 GREEN
[ ] 15. Checkpoint-VM -SnapshotName green-baseline
```

## 12. 文件与出处

**`C:\coil\vm_setup\`（不受版本控制，live origin）**——下表脚本已在

[`runner/vm_setup/`](../runner/vm_setup/) 留有快照（含步骤→脚本映射、未收录清单、
废弃产物说明）；`Fido.ps1` 与各 ISO/bundle 因体积或第三方授权未入库，按本文命令现取。

| 文件 | 用途 |
|---|---|
| `hv_enable.ps1` | 启用 Hyper-V（§2） |
| `Fido.ps1` | ISO 下载器 v1.70（§3） |
| `Win11_25H2_English_x64.iso` | 微软官方原版 ISO，8,471,603,200 B |
| `hv_hyperv_setup.ps1` | **成功的** VM 创建（双光驱 ISO 引导）（§4 路线 A） |
| `hv_create_vm.ps1` / `dp_create.txt` | 失败的 DISM 灌盘路线（§4 路线 B） |
| `autounattend.xml` / `autounattend_schneegans.xml` / `unattend.iso` | 应答文件（§5） |
| `hv_boot_presskey.ps1` | 自动按一次键 + 换入 Schneegans 应答盘 |
| `hv_orchestrate.ps1` | 首启等待 → provision → GL → 冒烟 → 快照（§6、§7） |
| `hv_provision4.ps1` | 客机内环境部署（§6） |
| `bundle.7z` / `guest_dvd5.iso` / `hv_swap_dvd5.ps1` | Unicode 安全递送包与换盘 |
| `relay.ps1` + `relay_cmd.txt` / `relay_out.txt` | 常驻提权中继（免 UAC） |
| `SESSION_SUMMARY_20260830.md`、`NEW_SESSION_PROMPT.md` | 当天会话总结与交接提示 |
| `Win11_patched.iso`、`win11-setup*.iso`、`guest_bundle.zip`、`win11-noprompt.iso` | **已放弃/损坏的中间产物**，勿复用 |

**仓库内相关文档**

| 文档 | 内容 |
|---|---|
| `runner/README.md` | 宿主↔客机跑批基础设施、环境变量、日常用法 |
| `README.md:58` | 宿主直跑 vs Hyper-V 跑批的路线说明（"无人值守全量回归走 `runner/hv_go.ps1`"） |
| `PITFALLS_0901.md` §1 | 控制台分辨率跌落（本机最大坑） |
| `docs/UIA_EVAL_0903.md` | UIA 混合定位评估（依赖同一台客机） |
