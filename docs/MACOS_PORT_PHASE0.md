# macOS 移植 Phase 0/1 — 原语盘点与最小 driver 接口

日期：2026-11-15
状态：Phase 0/1 已落地（Windows 后端 + 接口 + 契约用例）；Phase 2 等待 macOS 运行环境与 2.4.2 mac 构建。

## 0. 结论先行

1. **macOS 构建可得**：Snapmaker 在 GitHub `Snapmaker/OrcaSlicer` 的 v2.4.1 发布页提供
   `Snapmaker_Orca_Mac_universal_V2.4.1.dmg`（261 MB，universal：Apple Silicon + Intel）。
   本地 2.4.2 验收包只有 Windows 版；未找到公开的 2.4.2 mac 包。
2. **macOS 运行环境不可得**：本机是 Windows 10 宿主 + Hyper-V `win11-test` 客机，没有
   Mac、macOS VM 或远程 Mac。Phase 2（真实启动、AX 驱动、TCC 权限、截图）无法验证。
3. **Phase 0/1 已完成**：
   - `harness/platform/{base,factory,windows,macos}.py`：平台无关契约 + Windows 后端 +
     macOS fail-fast 占位。
   - `cases.py`：新增 `platforms` 元数据（默认 `("windows",)`）与按平台过滤；
     原 126 条注册、启用 74 条不变；另新增 1 条契约用例（按软关闭规则默认
     `enabled=False`），不改变基线口径。
   - `tests/engine/m0_platform_contract.py`：驱动后端端到端契约用例（新用例按软关闭
     规则默认 `enabled=False`，用于显式跑，不改变基线口径）。
4. **移植的真正门槛不是构建，而是 UI 驱动层**：现有套件有 529 处直接
   `winutil.user32` 调用、135 处 `#32770` 对话框假设、45 处 `SendMessageW`、
   34 处 `PrintWindow`。macOS 没有 HWND、窗口消息、PrintWindow、Win32 对话框类名，
   这些必须按语义重写，不能逐点替换。

## 1. Win32 原语盘点（证据 2026-11-15）

统计命令（仓库根）：

```bash
grep -rhoE 'winutil\.user32' --include='*.py' . | wc -l        # 529
grep -rn '#32770' --include='*.py' . | wc -l                   # 135
grep -rhoE '\b(SendMessageW|PrintWindow|SendInput|WM_CHAR|WM_COMMAND)\b' \
  --include='*.py' . | sort | uniq -c                          # 45/34/30/27/26
```

| 指标 | 数量 |
|---|---:|
| 用例注册 / 启用基线 | 原 126 / 74；新增契约用例后 127 / 74 |
| 导入 `winutil` 的测试脚本 | 89 |
| 导入 `winutil` 的 harness 模块 | 13 |
| 直接 `winutil.user32.*` 调用 | 529 |
| `ctypes.WinDLL` 构造 | 97 |
| 导入 `ctypes` 的 Python 文件 | 117 |
| `#32770`（Win32 对话框类）假设 | 135 |
| `SendMessageW` / `PrintWindow` / `SendInput` | 45 / 34 / 30 |
| `WM_CHAR` / `WM_COMMAND` / `WindowFromPoint` | 27 / 26 / 11 |
| `EnumChildWindows` / `BM_GETCHECK` | 9 / 9 |

这些数字说明：黑盒驱动不是“截图 + 点击”两件事，而是深度依赖 wxMSW 的窗口树、
消息路由、原生控件类名和模态对话框循环。

## 2. 模块分层与可移植性

| 层 | 模块 | 平台依赖 | 移植策略 |
|---|---|---|---|
| 眼睛/手 | `harness/winutil.py` | Win32：`PrintWindow`、`SendMessage`、`WindowFromPoint`、DPI | 收进 Windows 后端；macOS 用 AX + Quartz/CGEvent |
| 启动 | `harness/launcher.py` | `subprocess` + HWND 发现 + 更新提示 WM_CLOSE | `driver.launch()`；macOS 用 `open`/`NSWorkspace` + AX 窗口发现 |
| 顶栏/菜单 | `harness/topbar_util.py` | HMENU、原生 popup、坐标带 | Phase 3 重写为 AXMenuBar 遍历 |
| 导出/对话框 | `harness/export_util.py` | `#32770`、Save 对话框、按钮枚举 | Phase 3 用 AXSheet/AXDialog |
| 混色 | `harness/mixing_util.py`、`mix_dialog_util.py` | 原生 combo、owner-draw 复选、像素探针 | Phase 3 语义化重写 |
| 工艺面板 | `harness/process_panel.py` | 窗口树、滚动、OCR 带 | Phase 3 重写；OCR 可复用 |
| 视觉锚点 | `harness/anchors.py` | 匹配逻辑可复用，但捕获走 `winutil` | Phase 2 先迁 `capture_bgr` 到 driver |
| 共享 oracle | `gcode_check.py`、`ocr_util.py`、`fixture_util.py`、`profile.py` | 基本纯 Python/OpenCV/Tesseract | 直接复用；路径/资源布局做小改 |
| 录屏 | `harness/shot_archive.py` | GDI 屏幕抓取 + 多显示器 | 切到 `driver.capture_screen()` |
| 跑批 | `runner/hv_go.ps1` 等 | Hyper-V、PowerShell Direct、计划任务 | 新建 `runner/mac/`；Windows runner 保留 |
| 用例门禁 | `tests/conftest.py` | 1920x1080、96 DPI、远控检测 | macOS 另建门禁（Retina/缩放/TCC） |

## 3. 最小 driver 接口（已实现）

文件：`harness/platform/base.py`。设计约束：

- 坐标统一为**物理像素、左上原点**；`Rect` 右/下开区间。
- 帧统一为 **BGRA、top-down、紧密排列**，与 `winutil.capture_window()` 一致，
  OpenCV/Tesseract 代码可原样复用。
- 不导入 `ctypes`、`winreg`、PyObjC；任何平台都能 import。
- `Driver.message_input` 明确后端是否支持“无焦点消息注入”（Windows=True）。
- `AppHandle` = pid + 主窗口 + 生命周期回调，屏蔽 `AppSession`。

接口方法（语义层，非 Win32 镜像）：

```text
launch / windows_for_pid / find_main_window / window_title / window_class
window_rect / client_rect / client_to_screen / screen_to_client
screen_size / dpi_scale
capture / capture_screen
click / wheel / send_text / read_text / send_key
set_foreground / close_window
controls / find_control / click_control / control_text / set_control_text
```

选择入口：

```python
from harness.platform import get_driver
driver = get_driver()          # win32 -> WindowsDriver；darwin -> MacOSDriver
```

## 4. Windows 后端映射（已实现）

文件：`harness/platform/windows.py`。它只是 `winutil` / `launcher` 的薄适配，
**不引入新的时序、重试或坐标策略**，因此对 74 条基线没有行为改变。

| Driver 方法 | Windows 实现 |
|---|---|
| `launch` | `launcher.launch()`（清 env、datadir、模型自动加载、boot blocker sweep） |
| `windows_for_pid` | `winutil.enum_windows()` 按 pid 过滤 |
| `find_main_window` | `winutil.find_main_window()` |
| `window_*` / `client_*` | `GetWindowRect` / `GetClientRect` / `ClientToScreen` / `ScreenToClient` |
| `capture` / `capture_screen` | `winutil.capture_window()` / `winutil.screen_grab()` |
| `click(real=False)` | `winutil.msg_click_screen()`（`deepest_child_at` 防 WebView2 吞点击） |
| `click(real=True)` | `winutil.real_click_screen()` / `real_right_click_screen()` |
| `wheel` | `winutil.real_wheel_screen()`（消息级滚轮未实现，显式报错） |
| `send_text` / `read_text` | `msg_text()` / `edit_text()`（跨进程 Edit 用 WM_GETTEXT） |
| `send_key` | `winutil.msg_key()`；键名/修饰键做语义映射 |
| `controls` / `find_control` | `EnumChildWindows` + 文本/类名/role 归一化 |
| `click_control` | 控件矩形中心 -> `click(screen=True)` |
| `close_window` / `set_foreground` | `PostMessage(WM_CLOSE)` / `force_set_foreground` |

## 5. macOS 后端映射（Phase 2 计划）

文件 `harness/platform/macos.py` 目前是 fail-fast 占位，防止在非 darwin 上
静默走 Win32 假设。计划映射：

| Driver 方法 | macOS 实现 |
|---|---|
| `launch` | `NSWorkspace.openApplication` 或 `open -a`；等待 AX 主窗口 |
| `windows_for_pid` | `AXUIElementCreateApplication(pid)` -> `kAXWindowsAttribute` |
| `window_title/class` | `kAXTitleAttribute` / `kAXRole` + `kAXSubrole` |
| `window_rect/client_rect` | `AXPosition` + `AXSize`；统一成左上物理像素 |
| `capture` | ScreenCaptureKit（macOS 14+）或 CGWindowListCreateImage；转 BGRA |
| `click` | AXPress/AXSetValue；必要时 CGEvent 鼠标事件 |
| `send_text` | AXValue 设置；必要时 CGEvent 键盘事件 |
| `send_key` | `CGEventCreateKeyboardEvent` + modifier flags |
| `controls` | AXChildren 递归 -> `ControlRef(role, title, frame)` |
| `close_window` | AXClose / AXCancel，兜底 Cmd+W |
| `message_input` | `False`：没有 `SendMessage`，`real=False` 也走 OS 事件 |

## 6. 刻意未纳入最小接口（Phase 2/3 backlog）

这些是 74 条用例的主要工作量，不能低估：

1. **全局菜单栏**：`topbar_util` 依赖每窗口 HMENU/原生 popup；macOS 菜单在
   `AXMenuBar`，需要整套遍历/快捷键策略。
2. **`#32770` 对话框**：135 处假设；macOS 用 `AXSheet`/`AXDialog` + 标题，
   按钮/默认键行为也不同。
3. **原生 combo popup**：`CB_*` 消息、弹出列表定位、键盘选择；macOS 需要 AX
   menu/popup 操作。
4. **owner-draw 控件**：PA 对话框勾选靠像素颜色（teal/dark），macOS 渲染不同，
   需要重新标定或改 AX 状态读取。
5. **消息级输入**：Windows 可无焦点点击；macOS 的 CGEvent 需要前台/辅助功能权限，
   远控/无人值守场景要重新设计焦点策略。
6. **保存/文件对话框**：Win32 路径输入 + 保存按钮；macOS 是 NSSavePanel，
   需要 AX 或 AppleScript。
7. **UIA/进程内白盒**：现有 `runner/uia_probe.py`、`m1b_maa` 不在移植范围。

## 7. 验收门与当前状态

| 阶段 | 门 | 状态 |
|---|---|---|
| Phase 0 | 接口可在任意平台 import；Windows 后端满足 `Driver` 协议；`platforms` 默认值不影响 74 条基线 | ✅ 2026-11-15 |
| Phase 1 | Windows 后端契约用例在客机 GREEN；基线启用数仍 74 | ⏳ 契约用例待客机跑（见 §8） |
| Phase 2 | macOS 机器 + 2.4.2 mac 构建 + TCC 权限；`m0_platform_contract` macOS 版 GREEN | ⛔ 缺运行环境 |
| Phase 3 | 按用例批次迁移（先 m0/m1/m2，再 m3-m5，最后混色/顶盖） | 未开始 |

注意：Phase 1 的“74 例保持全绿”目前只做到**不改变现有调用路径**（后端是新增层，
没有替换 `winutil`）。真正的单批 74/74 背书仍是独立跑批事项；本轮未跑全量，
避免把“未验证”写成 GREEN。

## 8. 复现命令

宿主（只做接口/工厂自检，不启动 app）：

```bash
python -c "from harness.platform import get_driver; d=get_driver(); print(d.name, d.screen_size())"
```

客机（显式跑契约用例；先 commit+push，hv_go 会 pull）：

```powershell
& runner\hv_go.ps1 -Cases m0_platform_contract `
  -Exe 'C:\coil\apps\orca242_latest\Snapmaker_Orca\snapmaker-orca.exe'
```

客机 smoke（确认新增包不影响现有链路）：

```powershell
& runner\hv_go.ps1 -Suite smoke `
  -Exe 'C:\coil\apps\orca242_latest\Snapmaker_Orca\snapmaker-orca.exe'
```

## 9. 下一步建议

1. **用户侧**：提供一台 macOS 机器（Apple Silicon 优先）与 2.4.2 mac 构建；
   若只能用公开 v2.4.1 dmg，则先做 PoC，不作为 2.4.2 验收证据。
2. **Phase 2a**：实现 `macos.py` 的 launch/find/capture/click/text，先让
   `m0_platform_contract` 的 macOS 版 GREEN（TCC：辅助功能 + 屏幕录制）。
3. **Phase 2b**：把 `anchors.capture_bgr`、`shot_archive` 切到 `driver`，
   让 m0/m1/m2 三条链路在 macOS 跑通。
4. **Phase 3**：按用例族迁移菜单/对话框/混色；每族先在 Windows 回归 74/74，
   再在 macOS 跑对应子集，避免一次性重写 74 条。
5. **Runner**：新增 `runner/mac/`（launch + capture + TCC 检查 + 结果回收），
   Windows runner 保持不动。

## 10. 风险清单

- **版本错位**：公开 mac 包是 2.4.1，Windows 验收是 2.4.2；UI/行为差异会让
  “macOS 移植”与“2.4.2 验收”混在一起。必须明确 PoC 版本。
- **TCC 权限**：屏幕录制/辅助功能被拒时，PyObjC 可能返回空窗口或黑帧；必须
  在门禁里显式检测，不能把黑帧当产品缺陷。
- **Retina/缩放**：macOS 逻辑点 vs 物理像素；模板匹配对缩放敏感，需要固定
  显示器缩放并做坐标归一化。
- **输入模型**：没有消息注入，CGEvent 需要前台；与现有“无人值守、app 不抢焦点”
  的 Windows 策略冲突，需要新的焦点/窗口管理设计。
- **截图 API**：`CGWindowListCreateImage` 在新 macOS 已弃用，ScreenCaptureKit
  需要额外权限与异步 API；录屏链路要重写。
- **菜单/对话框差异**：大量用例依赖 Win32 类名、按钮文本和默认键行为；macOS
  的 AX 树与 wxOSX 实现可能不暴露同样的层级。
