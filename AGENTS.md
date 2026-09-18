# AGENTS.md — orca-blackbox 会话纪律（指针，非条文）

条文以 `README.md`「跑批纪律与收尾（新会话必读）」小节为唯一权威；`PITFALLS_0901.md` 是证据库。任何跑批、用例、探针工作开始前，先读这两处。

硬纪律（此处只做指针，条文见 README 小节）：

1. **执行位置**：批量回归/用例/探针默认在 Hyper-V 客机 `win11-test` 跑（唯一入口 `runner/hv_go.ps1`）；宿主直跑仅限 dev 调试/用户明令，且必须 `ORCA_BB_ALLOW_HOST=1` 显式放行——`harness/host_guard.py` 会机械拦截（exit 2）。
2. **收尾三步**：`hv_harvest.ps1` 拉结果 → commit+push（状态如实，禁止把未验证写成 GREEN）→ `tools/feishu_writeback.py` 写回飞书（仅 GREEN/已覆盖，宿主 lark-cli，禁止甩扫码 URL 给用户）。
3. **边界**：上游源码 `C:\coil\Projects\SnapmakerOrca` 只读，禁止修改；任务范围外的事不做。
