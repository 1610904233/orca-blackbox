# HANDOFF — Orca 2.4.1 基线第二批（#184–#204）交接

生成时间：2026-10-20 21:5x（宿主）
上一份交接：`HANDOFF_241.md`（第一批 #152/153/156/158 + 预设选择，已全部落地）

---

## 0. 一句话现状

第一批 4 条 + 第二批 10 条用例已 GREEN、用户逐个看过录像、提交并写回飞书；
**只剩 `m8x_187`（#187 自动定位/调整对象）没跑通**（s1 PASS，s2 的判定口径有 bug），
它已写好但**未提交**（`tests/mainflow/m8x_187.py` untracked，`cases.py` 有一行未提交注册）。
第二批其余 8 条（#188/#189/#191/#194/#195/#196/#197/#198）未开工；#184 建议人工。

---

## 1. 立刻要做的事（按顺序）

1. **取回上一次整跑的结果**（21:24:12 启动，交接时 s1 已 PASS、s2/s3 未取回）：
   - `jobs/j657_187detail.ps1` → 读 `m8x_187_s2.json` / `m8x_187_s3.json`
   - `jobs/j663_187all.ps1`（artifacts/进程）、`jobs/j664_187proc.ps1`（python/orca 命令行+启动时间）
   - 若还有 python/orca 在跑，先等结束，**不要并发**跑第二个 suite
2. **修 s2 的选中 bug**（见 §2），重跑 `m8x_187`
3. GREEN 后：拉 3 段视频 → **贴给用户确认** → 用户点头再 commit+push → 飞书写回"已自动化"
4. 然后按 §4 一条一条做剩余行（一次一个，跑完拉视频等确认）

---

## 2. #187 现状与已确诊的 bug

**行文要求**（飞书 tblWFGvJ5KQGVInq）：≥2 个盘、**每盘都有倾斜模型**；
Shift+Q 只调整当前盘、Q 调整所有盘；模型摆到较优朝向、仍在盘内、尺寸不变。
用户明确：**Shift+Q 需要先切英文输入法**。

**三会话结构**（同会话第 2 个 gizmo 面板会失聪，所以一变换一进程）：

| 会话 | 动作 | 产物 |
|---|---|---|
| s1 | 启动 Prusa → 选中 → Rotate **absolute X=45**（`op_gizmo_field(..., "rotate", 3, "45")`，index 3 = absolute 行第 1 列）→ 点 x=756 加盘 → 导入 `cube20.stl` → 另存 `P` | `m8x_187_proj.3mf` |
| s2 | 打开 P → 选中 → 倾斜 → 另存 P（覆盖） | 同上 |
| s3 | 打开 P → `english_layout()` → Shift+Q → 另存 `PA` → Q → 另存 `PB` | `m8x_187_after_shiftq.3mf` / `_after_q.3mf` |

**已确诊 bug（s2）**：`s2 基线：两模型均倾斜 = FAIL (1/2 倾斜)`。
打开 P 后 `m7.select_object_strict()` 用最大色块，选中的是 **1 号盘已经倾斜过的 Prusa**；
再设 **absolute** X=45 是幂等空操作，cube20 一动不动 → 只有 1 个 item 倾斜。
（s1 的 PASS 反过来证明"倾斜本身是有效的"。）

**修复方案（推荐 A）**：

- **A. `Ctrl+A` 全选 + absolute X=30**（换角度，能证明"真的变了"，不依赖哪个模型可见/被选中）：
  ```python
  def select_all(session):
      from harness import winutil as wu
      wu.user32.keybd_event(0x11, 0, 0, 0)      # Ctrl down
      wu.user32.keybd_event(0x41, 0, 0, 0)      # A
      wu.user32.keybd_event(0x41, 0, 2, 0)
      wu.user32.keybd_event(0x11, 0, 2, 0)
      time.sleep(0.6)
  ```
  断言改成：`item_mats(P)` 前后 **≥1 个 item 变化** 且 **2/2 非轴对齐**；
  注意 `op_gizmo_field` 内部先 `_already_selected()`，多选状态下不会重复点选，安全。
- **B. 按名选 cube20**：遍历 `m7.model_candidates()` 点进去读 `m7.object_info_text()`，
  含 `cube` 才继续。风险：若项目打开时相机停在 1 号盘，2 号盘的 cube 不可见 → 直接失败（不会假绿）。

**其它已修**（勿回退）：
- `boot_retry()`：上一会话 app 未释放文件锁时 `profile.seed_profile` 会抛
  `shutil.Error [WinError 183] ... machine`（实测 10-29，s2 因此 0 字节日志）；现在重试 3 次、间隔 6s，
  s2/s3 前另有 `time.sleep(5.0)`。
- 三处无用的 `from m3_common import boot_session` 已删，`pyflakes` 干净。

**s3 判定口径**（已实现，待数据）：
`item_mats()` 解析所有 `.model` 里的 `<item transform>`（行主序 3×4，`m[0:9]` 旋转、`m[9:12]` 平移）；
`is_axis_aligned()` 每行恰一个 ≈±1；断言：Shift+Q 后**恰 1 个 item 变化**、
Q 后**全部轴对齐**、缩放行范数 ≈1（尺寸不变）、tz 不增（底面贴合）。

**英文布局实现**（已写入 s3）：
```python
hkl = user32.LoadKeyboardLayoutW("00000409", 0x00000001)  # KLF_ACTIVATE
user32.PostMessageW(session.hwnd, 0x0050, 0, hkl)         # WM_INPUTLANGCHANGE
```
再 `press(session, 0x51, shift=True)`；按 Q 前先 `focus_canvas()`（点视口左上空白）。

---

## 3. 已完成、已写回飞书（不要重做）

| 用例 | 飞书行 | 状态 | 提交 |
|---|---|---|---|
| m8x_152 旋转/移动/缩放/耗材合并 | #152 | 部分自动化 | 06fd324 等 |
| m8x_153 全盘整理+改官方颜色+切片 | #153 | 部分自动化 | 2b6a858 |
| m8x_156 三段鼠标拖拽变换 | #156 | 部分自动化 | 1f30d08/3e8dc12/7c5aac5 |
| m8x_158 全盘整理（多模型） | #158 | 部分自动化 | 56c65b1/8829d20 |
| m8x_199 新建项目（未保存确认） | #199 | 已自动化 | b5aca43 |
| m8x_200 打开项目 | #200 | 已自动化 | 86aaedc |
| m8x_201 保存项目 | #201 | 已自动化 | 239bf36 |
| m8x_202 项目另存为 | #202 | 已自动化 | e96bfde |
| m8x_204 导出 STL | #204 | 已自动化 | 0d981a1 |
| m8x_185 添加（工具栏） | #185 | 已自动化 | 27560f9 |
| m8x_186 添加新盘 | #186 | 已自动化 | 83742e5 |
| A 类 #190/#192/#193/#203 | — | 已自动化 | 写回已验证 |

加入这 11 条之前的 **40 条基线全绿**（junit tests=40 failures=0）；
新增用例加完后建议再跑一次全盘回归。飞书 select 字段选项里已新增 **部分自动化**。

---

## 4. 剩余行（第二批）

| 行 | 内容 | 落点 / 已知难点 |
|---|---|---|
| #188 | 全局整理（**多盘 + 空盘删除**） | 全盘整理入口已知（工具栏图标 → 面板 `[Arrange]`，见 m8x_158）；空盘删除的入口**未标定**（盘标签右键？） |
| #189 | 单盘整理（Shift+A） | 可用 `arrange_all` 的键盘路径做对照：Shift+A 只影响当前盘 → 用两盘对象的 3mf 平移证明 |
| #191 | 旋转（X/Y + 相对/绝对） | 纯 gizmo 面板 + 3mf 矩阵最稳：absolute 设值、relative 连设两次看叠加 |
| #194 | 移除当前板 | **盘侧图标无 tooltip/文字**，三次探针（probe_241_plate2..5）都没命中 |
| #195 | 调整零件朝向 | 同上，属盘侧图标列 |
| #196 | 排列零件 | 同上 |
| #197 | 锁定当前板 | 同上 |
| #198 | 编辑盘名称 | 同上（可能双击盘标签，未验证） |
| #184 | 检测内存占用 | **建议不做黑盒自动化**，按人工/性能专项覆盖（已向用户建议过） |

**盘侧图标标定**是 #194–#198 的共同前置，建议下一步单独开探针：
对盘条/右侧栏区域整幅截图 + 网格点击 + 截图差分（图标按下会有高亮/面板变化），
而不是继续靠猜坐标；也可先查 View 菜单里是否有对应可文字识别的命令项作为入口。

---

## 5. 硬纪律（AGENTS.md / README）

1. 批量回归、用例、探针**一律在客机 `win11-test` 跑**，唯一入口 `runner/hv_go.ps1`；
   宿主直跑须 `ORCA_BB_ALLOW_HOST=1`（`harness/host_guard.py` 会 exit 2）。
2. **一个用例一个用例跑，不要并行**；每条跑完**先拉视频给用户确认**，用户确认后才 commit。
3. 收尾三步：`hv_harvest.ps1` 拉结果 → commit+push（状态如实，未验证不许写 GREEN）→
   `tools/feishu_writeback.py` 写回飞书（仅 GREEN/已覆盖，宿主 lark-cli，**不准把扫码 URL 甩给用户**）。
4. 上游源码 `C:\coil\Projects\SnapmakerOrca` **只读**；任务范围外的事不做。
5. 提交前把变动内容讲给用户确认；任何 token / app secret / user_access_token 不进对话。

---

## 6. 运行 / 取证命令

```bash
# 1) 提交一个 suite（宿主 relay，job 文件放 C:\coil\vm_setup\jobs\）
cd /c/coil/vm_setup && powershell -NoProfile -ExecutionPolicy Bypass \
  -File submit_job.ps1 -Job 'C:/coil/vm_setup/jobs/j654_run_187.ps1' -TimeoutSec 600

# 2) 轮询（客机 artifacts / json / 进程）
powershell -NoProfile -ExecutionPolicy Bypass -File submit_job.ps1 -Job 'C:/coil/vm_setup/jobs/j657_187detail.ps1'
powershell -NoProfile -ExecutionPolicy Bypass -File submit_job.ps1 -Job 'C:/coil/vm_setup/jobs/j663_187all.ps1'

# 3) 单会话调试（只重跑 s2，日志写到 C:\coil\s2only.log）
powershell -NoProfile -ExecutionPolicy Bypass -File submit_job.ps1 -Job 'C:/coil/vm_setup/jobs/j659_s2only.ps1'

# 4) 直跑 hv_go（job 内部实际调用）
& 'D:\code\orca_blackbox\runner\hv_go.ps1' -NoSync -Cases @('m8x_187')

# 5) 拉视频：套 j482_pull152.ps1 的模板（base64 分块 + MD5），
#    187 的路径是 artifacts\shots\m8x_187_s{1,2,3}\m8x_187_s{n}_run.mp4
#    （j656_pull187.ps1 里仍写着旧的 shots\m8x_187\... ，需要改）
```

**job 脚本注意事项**：
- 推送用例 = j654 的模板：`cases.py` + `tests/mainflow/m8x_xxx.py` base64 → 客机同名路径；
  末尾 `Stop-Process snapmaker-orca -Force` 再 `hv_go -NoSync -Cases @(...)`。
- job 文件**用 Write 工具写**，别用 heredoc（PS heredoc 会吃掉一层反斜杠）。
- 父进程只回显子进程最后 40 行（PITFALLS §21.14）；要看全量就单跑 `--session sN` 并用
  `Out-File C:\coil\xxx.log` 落盘再拉。

---

## 7. 复用 API 速查

```
m7_common:  ensure_maximized / select_object_strict / object_info_text / object_selected /
            model_candidates / find_centroids / op_gizmo_field(session, slot_pred, row_label, index, value) /
            read_gizmo_field(expect=...) / gizmo_row_boxes / toggle_gizmo_key('M'|'R') /
            real_drag_screen / save_project_as / click_slot / tooltip_text /
            wait_dialog / click_menu_row / list_menu / dismiss_menus
m8_common:  wait_arrival / wait_file / gcode_slot_colour(path, 0-based) / slot_swatch_rgb
m8b_official_color: click_official_color_popup / pick_official_card
m8x_158:    import_model / object_blobs(area>=400, aspect 0.3–4, 盘区 x 900–1450 / y 400–800)
harness:    export_util.find_edit / export_util.export_gcode（先 unlink，防旧文件假 PASS）/
            topbar_util.open_file_menu / shot_archive.start_archiver
```

`op_gizmo_field` 的 index：Rotate 面板两行（relative / absolute），`gizmo_row_boxes` 按
**全部以 rotate 开头的行**从上到下取，index 3 = absolute 行的 X，index -1 = absolute 行 Z。

---

## 8. 踩过的坑（详见 `PITFALLS_0901.md` §21.12–§21.16）

- **§21.12** 薄对象点击质心 +22px 会落到热床；工具栏 tooltip 不能当"已选中"判据 → 用右下角 object-info 面板。
- **§21.13** 换料菜单各行标签完全相同、MF_CHECKED 读不到 → 用"对象渲染色 + gcode `filament used`"双证据。
- **§21.15** 导出等文件要**先删旧文件**，否则 3 天前的 gcode 会让用例假 PASS。
- **§21.16** gizmo 命中区 ≠ 绘制像素；激活工具本身会把对象挪一小段；
  拖热床 = 转相机（曾把"转相机"误判成"模型旋转"）；**同会话第 2 个 gizmo 面板失聪** → 一变换一进程。
- 弹窗菜单 `BitBlt` 截不到 → 对菜单窗口做 `PrintWindow` 截图存档。
- 客机连跑多个 app 会话后 OOM（`pix_malloc fail` / 0 字节日志）→ 长批次前重启客机（j473：重启+等登录）。
- 宿主重启会杀掉 relay → `Start-ScheduledTask -TaskName orca_relay`。
- VMConnect 抢会话 → 通过 elevated relay + INTERACTIVE 任务拉起，用完关掉自己的窗口。

---

## 9. 本次新增文件

```
tests/mainflow/m8x_152.py  m8x_153.py  m8x_156.py  m8x_158.py
tests/mainflow/m8x_199.py  m8x_200.py  m8x_201.py  m8x_202.py  m8x_204.py
tests/mainflow/m8x_185.py  m8x_186.py
tests/mainflow/m8x_187.py            ← 唯一未提交、未 GREEN
fixtures/cube20.stl (20mm 立方体)  fixtures/prism12.stl (12 棱柱)
diag/probe_241_plate2..5.py         ← 盘侧图标标定的失败尝试（可复用截图逻辑）
diag/probe_241_merge_*.py  probe_241_rotate_drag.py  probe_241_rot_handle2.py
diag/probe_241_arrange.py  probe_241_filament_row_merge.py
C:\coil\vm_setup\jobs\j654/j656/j657/j659/j663/j664  ← 187 的运行/轮询/单跑脚本
```
