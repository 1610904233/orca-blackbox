# runner/vm_setup/ — Hyper-V Win11 客机装机脚本（快照）

`C:\coil\vm_setup\` 里的**装机**脚本（与跑批脚本 `runner/` 分开放置）：从零把一台
Win11 客机装起来并部署黑盒测试环境。步骤说明与坑位见
[`../../docs/VM_SETUP_HYPERV.md`](../../docs/VM_SETUP_HYPERV.md)。

> **来源与同步**：本目录是 2026-08-30 装机工具链的快照（2026-09-16 落库）。live origin
> 仍是 `C:\coil\vm_setup\`——两边当前都能用；改任何一边记得同步。与 `runner/` 一样，
> 本目录**只收录装机与部署脚本**，日常跑批看 `runner/README.md`。

## 步骤 → 脚本

| 步骤（对应文档章节） | 脚本 |
|---|---|
| 启用 Hyper-V（§2） | `hv_enable.ps1`（提权；`Enable-WindowsOptionalFeature`）+ `hv_run_all.ps1`（提权合并入口） |
| 下载 Win11 ISO（§3） | **不在本目录**：`Fido.ps1` 是第三方（pbatard/Fido，GPLv3），按文档 §3 的 curl 命令现取 |
| 创建 VM（§4 路线 A，**生效**） | `hv_hyperv_setup.ps1` |
| 创建 VM（§4 路线 B，**失败，留作对照**） | `hv_create_vm.ps1` + `dp_create.txt` + `hv_apply_continue.ps1` |
| 应答盘与装机（§5） | `autounattend_schneegans.xml`（**生效**）/ `autounattend.xml`（手写失败版，对照）、`make_iso.ps1`、`hv_boot_presskey.ps1`、`hv_switch_to_disk.ps1`（装机后切回硬盘，**必做**）、`hv_diag_panther2.ps1`（读 Panther 日志） |
| 客机环境部署（§6） | `hv_orchestrate.ps1`（编排）、`hv_provision4.ps1`（**生效**）/ `hv_provision.ps1`（首版对照）、`hv_swap_dvd5.ps1` + `hv_push_dvd4.ps1`（bundle 递送盘）、`hv_gl_and_smoke.ps1`、`hv_fix_mesa.ps1`、`hv_layout_fix.ps1`、`hv_fix_tree_smoke.ps1` |
| 验收与快照（§7） | `hv_orchestrate.ps1` 末段（`Checkpoint-VM`）、`hv_run_suite.ps1` |
| 提权中继 / 推文件（§1、§6） | `relay.ps1`、`send_to_guest.ps1`、`fetch_from_guest.ps1` |
| 控制台辅助（§5 按键、§6 分辨率） | `max_vmconnect.ps1`、`hv_sendkey.ps1`、`hv_check.ps1`、`hv_diag_app.ps1` |
| 客机侧执行 | `guest_run_suite.ps1`、`guest_run_failed.ps1`、`guest_fix_and_rerun.ps1`、`guest_shot.ps1`、`poll_rerun.txt`（轮询命令模板） |
| 原始交接材料 | `SESSION_SUMMARY_20260830.md`、`NEW_SESSION_PROMPT.md` |

带序号的脚本（`hv_provision1..4`、`hv_push_dvd1..4`、`hv_diag_panther/2`）**只有最终
生效版进了本目录**，中间迭代留在 live origin。

## 未收录内容及原因

| 未收录 | 原因 |
|---|---|
| `Fido.ps1` | 第三方 GPLv3 工具，不入本仓；文档 §3 给了获取命令 |
| `*.iso`（Win11 原版 8.47GB、`unattend.iso`、`guest_dvd*.iso`、`windows-tools.iso`） | 二进制大文件 |
| `guest_bundle.zip`（坏包）/ `bundle.7z` / `mesa-dist-win.7z` / `7zr.exe` | 二进制大文件；`bundle.7z` 由工作树打包而来，应可重建 |
| `*.log` / `relay_out.txt` / `relay_alive.txt` / `grun_*.txt` / `hv_go_out.txt` | 运行产物，非源 |
| `hv_test1/2.ps1`、`hv_probe*.ps1`、`run_hv*.ps1`、`hv_dbg.txt` | 一次性实验残留 |
| `zfind/zlog/zprog/zraw/zshots/zstate.ps1`、`hv_go.ps1`、`clean_guest.ps1` | 已在 `runner/` |
| `*.vmem` | Hyper-V 运行时内存转储 |

## 凭据与环境（照抄自 live origin，注意风险）

- 客机自动登录：`test` / `123456`（Schneegans 应答里是 `test` / `Passw0rd!`，
  后期在客机内改为 `123456`，见 `guest_fix_and_rerun.ps1`）。
  **一次性隔离测试 VM，非机密**；换真机/复用环境务必覆盖。
  参考 `runner/README.md` 的 `ORCA_BB_GUEST_USER` / `ORCA_BB_GUEST_PASS`。
- 脚本里 VM 名 `win11-test`、"Default Switch"、`C:\coil\vm_setup\` 等**全部硬编码**，
  与 `runner/` 那套参数化（`_common.ps1` + 环境变量）**不是同一风格**。
  **待办**：要复用请先参数化，或直接以文档 §11 清单为准则重写。

## 已判定废弃、勿复用的产物

- `win11-setup.iso` / `win11-setup-udf.iso`（mkisofs 2.01 重制，引导层不可信）
- `win11-noprompt.iso`（损坏）、`Win11_patched.iso`、`Win11_25H2_English_x64.iso`（保留可用）
- `guest_bundle.zip`（839MB 坏包，7z 打不开 → 已被 `bundle.7z` 取代）
- 宿主 DISM 灌盘路线（`hv_create_vm.ps1`，Error 87）与手写 `autounattend.xml`
  ——两者仅作对照留存，**生效路线见文档 §4 路线 A / §5**。
