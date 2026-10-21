#!/usr/bin/env python3
# m8x_156.py — 飞书基线 #156: 模型快速调整与局域网打印（**本地段**）
# feishu: baseline#156
# 行文步骤: 启动Orca→导入模型→旋转缩放移动→切片→[局域网设备绑定→发起打印
#           →监控打印→解绑设备]→关闭软件
#
# 本用例覆盖方括号之前的电脑端步骤；设备链需真机 → 飞书「部分自动化」。
#
# **每变换一个新会话**（与 m8x_152 同一结构，原因同源）：2.4.1 上同一会话内
# 第二个及以后的 gizmo 面板对所有输入通道失聪（实测 10-15/16 多轮），台架以
# "重开"绕行。会话映射：
#   s1  空盘启动 → File→Import 导入 Prusa.stl → Rotate Z=45（回读）
#   s2  CLI 载入 → Move X=60（回读）
#   s3  CLI 载入 → Scale 120（回读）
#   s4  CLI 载入 → 切片 → 导出 gcode（"G-code 生成正常"）
#
# **与 #152 的覆盖区分**：#152 三个变换都是"面板输入数值"；本用例的**移动走
# 鼠标拖拽**（激活 Move 后拖对象本体，断言=面板数值变化 100.00→154.77），这是
# #152 没覆盖的输入通道。
# 拖拽的具体形态（用户口径 10-19）与**两台不同的判据**：
#   * 移动 = 按住对象本体拖动 → 面板位置数值变化（100.00 -> 154.77）
#   * 缩放 = 点住模型上的方块控制点拖动 → 面板 Scale 变化（100.00 -> 83.35）
#   两者都用"应用状态数值"作证，与相机无关。
#   * 旋转 = **输入值**。鼠标拖蓝箭头已实证可转（Z 0.00 → 171.54、热床不动），
#     但命中位置每轮漂移（环像素/尖端/包围盒角/相对偏移四套定位都只有个别轮次
#     命中，命不中时拖床面 = 相机环绕）；稳定化需要箭头模板视觉标定，另开任务。
#
# 录像：artifacts/shots/<stem>_<tag>/<stem>_<tag>_run.mp4

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))
sys.path.insert(0, str(HERE / "tests" / "mainflow"))

LOG = "[m8x156]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
SESSIONS = ("s1", "s2", "s3", "s4")


def run_s1(args, results):
    """空盘启动（首次安装语义）→ File→Import 导入模型 → Rotate Z=45。"""
    import m7_common as m7
    import m8x_152 as base
    from harness import export_util
    from m3_common import boot_session

    base.patch_archiver("s1")
    args.model = None
    session = boot_session(args, model=None)
    ok = False
    try:
        frac0 = m7.model_colored_frac(session)
        results["启动 Orca（空盘）"] = (
            "PASS" if frac0 < m7.EMPTY_BED_FLOOR else f"FAIL ({frac0:.3%})")
        if frac0 >= m7.EMPTY_BED_FLOOR:
            return False
        dispatched, dlg = m7.file_menu_dispatch(session, "stl",
                                                expect_dialog=True, via="Import")
        results["导入入口派发"] = "PASS" if dispatched else "FAIL"
        if not dispatched or not dlg:
            return False
        edit = export_util.find_edit(dlg[3])
        if edit is None:
            results["文件名输入框定位"] = "FAIL"
            return False
        import ctypes
        from harness import winutil
        winutil.select_all(edit)
        winutil.msg_text(edit, str(STL))
        ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)  # IDOK
        deadline = time.monotonic() + 90
        frac = m7.model_colored_frac(session)
        while frac < 0.0025 and time.monotonic() < deadline:
            time.sleep(1.0)
            frac = m7.model_colored_frac(session)
        arrived = frac >= 0.0025 and m7.blob_count(session) >= 1
        print(f"{LOG} import arrives: frac={frac:.3%}")
        results["导入模型落盘"] = "PASS" if arrived else f"FAIL ({frac:.3%})"
        if not arrived:
            return False
        pt = base.select_small_then(session, results)
        if not pt:
            results["旋转（拖拽）生效"] = "FAIL (model not selectable)"
            return False
        x, tip = m7.find_slot(session, lambda t: "rotate" in t)
        print(f"{LOG} rotate slot @{x} tip={tip!r}")
        if x is None:
            results["旋转（拖拽）生效"] = "FAIL (slot not found)"
            return False
        # 旋转：**先鼠标拖箭头锥**（用户口径）；命中不了再退化为输入值，
        # 并在结果里如实标注走的是哪条路。箭头锥几何见 rot_drag 的 docstring。
        if not open_gizmo(session, 1108, "rotate"):
            results["旋转（鼠标拖拽箭头）"] = "FAIL (rotate tool never active)"
            return False
        z0 = panel_value(session, "rotate", -1, timeout_s=3.0)
        live = m7.find_centroid(session) or pt
        print(f"{LOG} rotate: Z0={z0!r} live={live}")
        z1, how = rot_drag(session, live, z0)
        if how:
            results["旋转（鼠标拖拽箭头）"] = f"PASS ({how})"
            return True
        results["旋转（鼠标拖拽箭头）"] = "FAIL (arrow sweep missed)"
        ok, text = m7.op_gizmo_field(session, lambda t: "rotate" in t,
                                     "rotate", -1, "45")
        results["旋转 Z=45（退化·输入值）"] = (
            "PASS" if ok else f"FAIL (now {text!r})")
        return ok
    finally:
        session.close()
        print(f"{LOG} session closed (s1)")


def open_gizmo(session, x, row_label, tries=3):
    """点工具栏槽打开 gizmo 面板，并**验证面板真的开了**（gizmo_row_boxes
    能读到行）。点击被吞时用键盘快捷键再切一次（rotate→R / move→M 已验证；
    scale 没有已证实快捷键，只能再点一次）。

    10-19 实测：直接点槽就读值，s1 的 rotate 读到 ''（面板没开）、s3 的
    scale 反而开了——同一条点击路径结果不稳定，必须判+重试。"""
    import m7_common as m7
    for attempt in range(tries):
        m7.click_slot(session, x)
        time.sleep(1.2)
        diag = {lab: len(m7.gizmo_row_boxes(session, lab))
                for lab in ("position", "rotate", "scale")}
        print(f"{LOG} panels after click @x{x}: {diag} (want {row_label})")
        if m7.gizmo_row_boxes(session, row_label):
            return True
        print(f"{LOG} {row_label} panel not open (attempt {attempt + 1})")
        if attempt == 0:
            m7.toggle_gizmo_key(session, row_label)   # rotate/move 有验证过的键
            time.sleep(1.0)
            if m7.gizmo_row_boxes(session, row_label):
                return True
    return False


def panel_value(session, row_label, index, timeout_s=8.0):
    """读 gizmo 面板某行的第 index 格（index<0 = 行末列）。

    直接用 gizmo_row_boxes 的文本：`read_gizmo_field` 在这条链上对未聚焦的
    Rotate Z 会返回 ''（10-19 实测），而 boxes 里本来就有数值（m8x_152 的
    'grid attempt1' 打印即此来源）。"""
    import m7_common as m7
    deadline = time.monotonic() + timeout_s
    while True:
        boxes = m7.gizmo_row_boxes(session, row_label)
        if boxes:
            i = index if index >= 0 else len(boxes) + index
            if 0 <= i < len(boxes):
                txt = (boxes[i][2] or "").strip()
                if txt:
                    return txt
        if time.monotonic() >= deadline:
            return ""
        time.sleep(0.8)


def _drag_candidates(session, pt, delta, row_label):
    """拖拽起点→终点的候选序列。

    Move/Rotate：整体拖对象本体（质心起拖）。
    Scale：2.4.1 的缩放手柄画在对象包围盒的角/边中点（实测 10-19：从质心
    拖**不会**改数值，before==after==100.00），所以从四角与四条边中点向外拖，
    由"数值是否变化"来判定命中。"""
    out = []
    if row_label == "scale":
        # 缩放面板右侧有一条竖滑块（帧里 x≈cells[0]-62、y 跨整行）：拖它比
        # 找 3D 角柄稳（实测四角/边中点都没命中）。
        import m7_common as m7
        cells = m7.gizmo_row_boxes(session, "scale")
        if cells:
            sx = cells[0][0] - 62
            sy = cells[0][1] + 6
            out.append(((sx, sy), (sx, sy + 64)))
    out.append((pt, (pt[0] + delta[0], pt[1] + delta[1])))
    if row_label != "scale":
        return out
    try:
        import m8_common as m8
        from harness.anchors import capture_bgr
        st = m8.blob_stats(capture_bgr(session))   # m7 没有 blob_stats（10-19 踩过）
    except Exception as exc:                                   # noqa: BLE001
        print(f"{LOG} scale bbox unavailable: {exc!r}")
        st = None
    if not st:
        return out
    bx, by, bw, bh = st["bbox"]
    cx, cy = bx + bw // 2, by + bh // 2
    corners = [(bx, by), (bx + bw, by), (bx, by + bh), (bx + bw, by + bh),
               (cx, by), (cx, by + bh), (bx, cy), (bx + bw, cy)]
    for sx, sy in corners:
        # 从该角/边中点**向外**拖（远离质心）
        ox = 1 if sx >= cx else -1
        oy = 1 if sy >= cy else -1
        out.append(((sx, sy), (sx + ox * abs(delta[0] or 30),
                               sy + oy * abs(delta[1] or 30))))
    print(f"{LOG} scale handle candidates: bbox={(bx, by, bw, bh)} "
          f"n={len(out)}")
    return out


def _plate_bbox(session):
    """热床投影的包围盒（视口内最大的**暗色**区域）。相机环绕会让它变形，
    所以它是"视角有没有动"的判据。"""
    import cv2
    import numpy as np
    import m7_common as m7
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = m7.VIEWPORT_X0 + 10, 110, w - 10, h - 60
    roi = img[y0:y1, x0:x1]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    dark = ((hsv[:, :, 2] < 130) & (hsv[:, :, 1] < 90)).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, _l, stats, _c = cv2.connectedComponentsWithStats(dark, 8)
    if n <= 1:
        return None
    i = max(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA])
    if stats[i, cv2.CC_STAT_AREA] < 20000:
        return None
    return (int(stats[i, 2]), int(stats[i, 3]))


def _shape_signature(session):
    """(对象 bbox, 热床 bbox)。旋转生效 = 对象 bbox 变了而热床 bbox 基本不变。"""
    import m8_common as m8
    from harness.anchors import capture_bgr
    st = m8.blob_stats(capture_bgr(session))
    obj = tuple(st["bbox"]) if st else None
    return obj, _plate_bbox(session)


def _sig_delta(a, b):
    """相对变化（%）。a/b 可以是对象 bbox (x,y,w,h) 或热床 (w,h)。"""
    if not a or not b or len(a) != len(b):
        return None
    if len(a) == 4:
        a, b = (a[2], a[3]), (b[2], b[3])
    return max(abs(b[0] - a[0]) / max(a[0], 1),
               abs(b[1] - a[1]) / max(a[1], 1)) * 100.0


def rot_drag(session, live, z_before):
    """旋转：点住**蓝色箭头锥**水平拖动，以面板 Z 值变化为判据。

    几何来源 = 取证帧放大图（artifacts/m8x156_gizmo_zoom.png，带刻度）：
    Rotate 激活后，箭头锥在对象中心**右侧 ~85-95px**（实测锥的可见范围
    x 1255-1300、y 545-595，对象中心 1186,578）；两次实证命中点 (1266,563)、
    (1259,584) 都落在锥内。此前按颜色找"蓝块"抓到的是锥左边的**方块手柄**
    （fill 0.27 的那个 44x52 分量），拖它无效——这是前几轮全部落空的原因。
    锥约 45x50px，这里在 live+(78..100, -14..+14) 上取 12 个点，命中即停；
    若某次拖拽把视角带偏（view 变化 >3%），立即反向拖回，录像不留相机转动。
    """
    import m7_common as m7
    plate0 = _plate_bbox(session)
    # 起点顺序 = 实证命中优先：上一轮命中在 live+(78,+14)（Z 176.36），
    # 另一轮在 live+(86,0)（Z 33.79）；方向先试 -45（命中方向）。
    # 命中点放第一位（两轮实证 live+(78,+14)：Z 150.57 / 176.36），
    # 这样第一次拖拽就命中，录像里不会出现相机晃动。
    pts = [(live[0] + dx, live[1] + dy)
           for dy, dx in ((14, 78), (0, 86), (14, 86), (-14, 78), (0, 78),
                          (0, 94), (-14, 86))]
    zs = []
    for (hx, hy) in pts:
        for ddx in (-45, 45):
            m7.real_drag_screen(session, (hx, hy), (hx + ddx, hy))
            time.sleep(0.7)
            z_now = panel_value(session, "rotate", -1, timeout_s=1.5)
            dplate = _sig_delta(plate0, _plate_bbox(session))
            print(f"{LOG} rot drag ({hx},{hy}) d({ddx},0) -> Z={z_now!r} "
                  f"view={dplate}")
            # 接受条件必须严格：模型初始 Z=0.00，所以 **Z 仍是 '0.00' 就是
            # 没转**（上一轮把"相机转了 31% + Z=0.00"当成了命中 = 假阳性，
            # 录像里只看到视角转动）。真旋转后 Z 必然非 0。
            if z_now and z_now not in ("0.00", "0", "0.0"):
                zs.append((hx, hy, ddx, z_now))
                a = zs[-1]
                return a[3], (f"arrow({a[0]},{a[1]}) drag ({a[2]},0): "
                              f"Z {z_before!r} -> {a[3]}")
            if z_now:
                print(f"{LOG}   Z still {z_now!r} = no rotation")
                continue
            # 落空且把相机转走了 → **立刻反向拖回**（实测反向拖能把视角复原），
            # 否则后面所有点的坐标都跟着偏移，录像里还会连续出现相机转动。
            if dplate is not None and dplate > 3.0:
                print(f"{LOG}   miss: view moved {dplate:.1f}% -> drag back")
                m7.real_drag_screen(session, (hx + ddx, hy), (hx, hy))
                time.sleep(0.5)
    return "", ""


def scale_drag(session, live, s_before):
    """缩放：点住模型上的**方块控制点**（红/绿/蓝色块）拖动，以面板 Scale 为判据。

    10-19 实测命中：红块 (1138,610) 拖 (50,30) → Scale 100.00 → 83.35。
    色块的真实极值像素都试一遍（控制点是立方体，任意角都可抓）；判据 =
    出现与拖动前不同的 Scale 值。"""
    import cv2
    import numpy as np
    import m7_common as m7
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(int)
    sat = hsv[:, :, 1].astype(int)
    val = hsv[:, :, 2].astype(int)
    ok = (sat > 110) & (val > 50)
    masks = (("red", ok & ((hue < 8) | (hue > 172))),
             ("green", ok & (hue > 45) & (hue < 75)),
             ("blue", ok & (hue > 100) & (hue < 130)))
    cands = []
    for name, m in masks:
        mm = cv2.morphologyEx((m.astype(np.uint8) * 255), cv2.MORPH_CLOSE,
                              np.ones((5, 5), np.uint8))
        n, _l, stats, _c = cv2.connectedComponentsWithStats(mm, 8)
        for i in range(1, n):
            if int(stats[i, cv2.CC_STAT_AREA]) < 120:
                continue
            bx, by = int(stats[i, 0]), int(stats[i, 1])
            bw, bh = int(stats[i, 2]), int(stats[i, 3])
            cx, cy = bx + bw // 2, by + bh // 2
            if max(abs(cx - live[0]), abs(cy - live[1])) > 220:
                continue
            sub = mm[by:by + bh, bx:bx + bw]
            ys, xs = np.nonzero(sub)
            if len(xs) < 20:
                continue
            for k in (0, len(xs) // 2, len(xs) - 1):
                cands.append((name, (int(xs[k]) + bx, int(ys[k]) + by)))
    print(f"{LOG} scale candidates: {[(c[0], c[1]) for c in cands][:10]}")
    for name, (hx, hy) in cands[:12]:
        for dx, dy in ((50, 30), (-50, 30), (50, -30), (-50, -30)):
            m7.real_drag_screen(session, (hx, hy), (hx + dx, hy + dy))
            time.sleep(0.9)
            now = panel_value(session, "scale", 0, timeout_s=2.0)
            print(f"{LOG} scale drag {name}({hx},{hy}) d({dx},{dy}) -> "
                  f"Scale={now!r}")
            if now and s_before and now != s_before:
                return now, f"{name}@({hx},{hy}) drag ({dx},{dy})"
    return s_before, ""


def drag_scale_session(args, tag, results):
    """缩放会话：激活 Scale → 点住控制点拖动 → 面板 Scale 值变化。"""
    import m7_common as m7
    import m8x_152 as base

    base.patch_archiver(tag)
    session = base.m7_boot(args, model=STL)
    try:
        deadline = time.monotonic() + 240
        frac = m7.model_colored_frac(session)
        while frac < 0.0025 and time.monotonic() < deadline:
            time.sleep(2.0)
            frac = m7.model_colored_frac(session)
        if not (frac >= 0.0025 and m7.blob_count(session) >= 1):
            results["缩放（手柄拖拽）模型在盘"] = f"FAIL ({frac:.2%})"
            results["缩放（手柄拖拽）生效"] = "FAIL (no model)"
            return False
        results["缩放（手柄拖拽）模型在盘"] = "PASS"
        pt = base.select_small_then(session, results)
        if not pt:
            results["缩放（手柄拖拽）生效"] = "FAIL (not selectable)"
            return False
        if not open_gizmo(session, 1108 + 44, "scale"):
            results["缩放（手柄拖拽）生效"] = "FAIL (panel never opened)"
            return False
        before = panel_value(session, "scale", 0, timeout_s=6.0)
        live = m7.find_centroid(session) or pt
        print(f"{LOG} scale: before={before!r} live={live}")
        after, how = scale_drag(session, live, before)
        ok = bool(how) and bool(after) and after != before
        results["缩放（手柄拖拽）生效"] = (
            f"PASS ({how}: {before!r} -> {after!r})" if ok
            else f"FAIL (Scale {before!r} -> {after!r})")
        return ok
    finally:
        session.close()
        print(f"{LOG} session closed ({tag})")


def drag_transform(args, tag, results, key, slot_pred, row_label, index,
                    delta, fallback_dx=0):
    """激活某个 gizmo（点工具栏槽）→ 读初始值 → **拖对象本体** → 读新值。

    断言 = 数值确实变化（拖拽生效），并把两次数值都打出来。用拖拽而不是输入
    数值是刻意的：这是"快速调整"的真实交互路径，与 #152 的输入式互补。
    delta 是屏幕像素位移（等距视图下屏幕位移映射到床面 X/Y 或绕 Z 角度）。"""
    import m7_common as m7
    import m8x_152 as base

    base.patch_archiver(tag)
    session = base.m7_boot(args, model=STL)
    try:
        deadline = time.monotonic() + 240
        frac = m7.model_colored_frac(session)
        while frac < 0.0025 and time.monotonic() < deadline:
            time.sleep(2.0)
            frac = m7.model_colored_frac(session)
        arrived = frac >= 0.0025 and m7.blob_count(session) >= 1
        results[f"{key} 模型在盘"] = (
            "PASS" if arrived else f"FAIL ({frac:.2%})")
        if not arrived:
            results[key] = "FAIL (model never arrived)"
            return False
        pt = base.select_small_then(session, results)
        if not pt:
            results[key] = "FAIL (model not selectable)"
            return False
        # 激活工具（面板打开 = 拖拽会即时反映到数值上）
        if fallback_dx:
            x = 1108 + fallback_dx
            print(f"{LOG} {row_label} slot via fixed geometry: {x}")
        else:
            x, tip = m7.find_slot(session, slot_pred)
            print(f"{LOG} {row_label} slot @{x} tip={tip!r}")
        if x is None:
            results[key] = "FAIL (slot not found)"
            return False
        if not open_gizmo(session, x, row_label):
            results[key] = "FAIL (gizmo panel never opened)"
            return False
        before = panel_value(session, row_label, index)
        print(f"{LOG} {key}: before drag = {before!r}")
        # 拖拽候选：对象质心（Move/Rotate 的整体拖动）+ 包围盒四角/边中点
        # 向外拖（Scale 的角柄）。每个候选拖完读值，变了就停——数值是判据。
        after = before
        for src, dst in _drag_candidates(session, pt, delta, row_label):
            print(f"{LOG} {key}: drag {src} -> {dst}")
            m7.real_drag_screen(session, src, dst)
            time.sleep(1.2)
            after = panel_value(session, row_label, index)
            print(f"{LOG} {key}: after drag = {after!r}")
            if after and after != before:
                break
        changed = bool(after) and after != before
        changed = bool(after) and after != before
        results[key] = (
            f"PASS (drag: {before!r} -> {after!r})" if changed
            else f"FAIL (value unchanged: {before!r})")
        return changed
    finally:
        session.close()
        print(f"{LOG} session closed ({tag})")


def run_s4(args, results):
    """CLI 载入 → 切片 → 导出 gcode（本地段的终点；上传/打印/监控需真机）。"""
    import m7_common as m7
    import m8_common as m8
    import m8x_152 as base

    base.patch_archiver("s4")
    session = base.m7_boot(args, model=STL)
    try:
        deadline = time.monotonic() + 240
        frac = m7.model_colored_frac(session)
        while frac < 0.0025 and time.monotonic() < deadline:
            time.sleep(2.0)
            frac = m7.model_colored_frac(session)
        arrived = frac >= 0.0025 and m7.blob_count(session) >= 1
        results["切片会话 模型在盘"] = (
            "PASS" if arrived else f"FAIL ({frac:.2%})")
        if not arrived:
            results["切片完成"] = "FAIL (model never arrived)"
            return False
        gcode = ART / "m8x_156.gcode"
        m7.op_slice(session, results, key="切片完成", export_to=gcode)
        try:
            used = m8.used_filaments(gcode.read_bytes())
        except OSError:
            used = []
        print(f"{LOG} gcode filaments used: {used}")
        results["G-code 生成（单耗材用量可读）"] = (
            f"PASS (used={used})" if used else "FAIL (no filament usage)")
        return bool(used)
    finally:
        session.close()
        print(f"{LOG} session closed (s4)")


def session_main(tag, args):
    results = {}
    if tag == "s1":
        ok = run_s1(args, results)
    elif tag == "s2":
        ok = drag_transform(
            args, tag, results, "移动（拖拽）X/Y 变化",
            lambda t: "move" in t, "position", 0, (80, 0))
    elif tag == "s3":
        ok = drag_scale_session(args, tag, results)
    else:
        ok = run_s4(args, results)
    out = ART / f"m8x_156_{tag}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return 0 if ok else 1


def main() -> int:
    import argparse
    import os
    from m3_common import add_common_args
    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    ap.add_argument("--session", choices=SESSIONS, default=None)
    ap.add_argument("--only", default=None,
                    help="debug: comma list of sessions; a partial run reports "
                         "RED on purpose")
    args = ap.parse_args()
    if args.session:
        return session_main(args.session, args)

    tags = [t for t in SESSIONS
            if not args.only or t in args.only.split(",")]
    results = {}
    rc = 0
    for tag in tags:
        out = ART / f"m8x_156_{tag}.json"
        out.unlink(missing_ok=True)
        r = subprocess.run(
            [sys.executable, "-u", str(Path(__file__).resolve()),
             "--session", tag,
             *(["--exe", str(args.exe)] if args.exe else []),
             "--datadir", str(args.datadir)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env={**os.environ,
                                   "PYTHONIOENCODING": "utf-8"},
            timeout=900)
        (ART / f"m8x_156_{tag}.log").write_text(
            (r.stdout or "") + (r.stderr or ""), encoding="utf-8",
            errors="replace")
        print(f"{LOG} === {tag} rc={r.returncode} ===")
        for ln in (r.stdout or "").splitlines()[-40:]:
            print(f"{LOG}   {ln}")
        if (r.stderr or "").strip():
            for ln in r.stderr.splitlines()[-6:]:
                print(f"{LOG}   E {ln}")
        if out.exists():
            results.update(json.loads(out.read_text(encoding="utf-8")))
        else:
            results[f"{tag} 会话结果缺失"] = "FAIL (no json)"
            if tag == "s1":
                rc = 1
                break
    if args.only:
        results[f"partial run (--only {args.only})"] = "FAIL (debug run)"
    print("\n[m3] === verdict ===")
    all_ok = bool(results) and all(str(v).startswith("PASS")
                                   for v in results.values())
    for k, v in results.items():
        print(f"  {k}: {v}")
    print("[m3] " + ("GREEN" if all_ok else "RED"))
    return 0 if all_ok else rc or 1


if __name__ == "__main__":
    raise SystemExit(main())
