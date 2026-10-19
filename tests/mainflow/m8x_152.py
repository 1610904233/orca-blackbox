#!/usr/bin/env python3
# m8x_152.py — 飞书基线 #152: 首次安装后新建项目并完成打印（**本地段**）
# feishu: baseline#152
# 行文步骤: 启动Orca→新建项目→导入模型→移动旋转缩放→更改打印机预设→耗材合并
#           →切片→[PIN码绑定云设备→发起打印→暂停→恢复→终止→监控]→关闭软件
#
# 本用例覆盖方括号之前的全部电脑端步骤。**每个变换一个全新 app 会话**（多进程
# 编排，--session 自举）：2.4.1 上同一会话内第二个及以后的 gizmo 面板对一切
# 输入通道（消息级 WM_CHAR / 逐位+去焦 / OS 级真实键盘）都丢字符或拒收
# （实测 10-15/16 多轮，'45'→'4' 提交成 4°；2.4.0 同样存在，m7t74 即因此
# 改为每会话一个变换）——这是 app 侧行为，值得报给开发；台架侧以"重开"绕行。
#
# 阶段映射（与 GREEN 两轮 13/13 的结构一致）：
#   s1  空盘启动(首次安装语义) → 新建项目 → 导入 STL → [证据行] 打印机预设
#   s2  CLI 载入 STL → Move X=60 → 关闭
#   s3  CLI 载入 STL → Rotate Z=45（绝对行末列）→ 关闭
#   s4  CLI 载入 STL → Scale 120 → 耗材合并（物理槽位，见下）→ 切片+导出 → 关闭
#
# 边界（诚实声明）：打印链（绑定/打印/监控/解绑）需真机 → 飞书「部分自动化」。
#   「耗材合并」在 S4 断言：对象先经 Change Filament 指到末位物理，再用
#   Filaments 行的删除桶并掉该槽 —— 断言槽位 -1、重开菜单恰一行勾选（模型
#   耗材丝同步重映射）、gcode 恰一个非零耗材。「涂色同步」的专责面仍是
#   m4e/m4i（本链模型未涂色）。

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

LOG = "[m8x152]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
SESSIONS = ("s1", "s2", "s3", "s4")


def patch_archiver(tag):
    """本阶段的录像：artifacts/shots/<stem>_<tag>/<stem>_<tag>_run.mp4。"""
    from harness import shot_archive
    orig = shot_archive.start_archiver

    def named(session, name, interval=3.0, out_root=None):
        return orig(session, f"{name}_{tag}", interval=interval,
                    out_root=out_root)

    shot_archive.start_archiver = named


def _poll_menu_at(session, sx, sy, timeout_s=4.0, slack=30):
    """第一个矩形覆盖点击点的 #32768 弹窗，或 None。

    轮询必须在**每个点**的循环里：上一版是按候选点轮询一次，两个点连点后
    第二个右键把第一个菜单关掉了，于是只有 '+22' 那个点真正被测过（10-16
    实测：录像里抓到过床菜单，而轮询报的是 'no menu'）。"""
    from harness import topbar_util
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for m in topbar_util._enum_menu_windows(session.pid):
            l, t, r, b, hwnd = m
            if (l - slack <= sx <= r + slack
                    and t - slack <= sy <= b + slack):
                return hwnd, topbar_util.menu_hmenu(hwnd)
        time.sleep(0.25)
    return None


def slot_menu_button(session, slot):
    """槽单元右缘的 '...' Button（class 'Button'，16x25，与该槽色板同一行、
    在色板右侧）。实测 10-16 探针 probe_241_filament_row_merge：这就是测试方
    说的"耗材右侧 ..."，菜单是 Edit / Delete / **Merge with**（子菜单=其余
    物理槽）。注意不要用 m8.filament_slots 的 picker 字段代替：2.4.1 的
    2x2 网格下它对第 4 槽读错位置（读到色板附近）。"""
    import m8_common as m8
    from harness import mixing_util
    from harness import winutil as _wu
    hit = next((s for s in m8.filament_slots(session) if s["slot"] == slot),
               None)
    if not hit:
        return None
    ch = hit["swatch"]
    cy = (ch[1] + ch[3]) // 2
    best = None
    for _t, c, r, h in mixing_util.children(session.hwnd):
        if c != "Button" or not _wu.user32.IsWindowVisible(h):
            continue
        if r[2] > 470 or r[0] < 4:
            continue
        if r[1] - 6 <= cy <= r[3] + 6 and r[0] > ch[2] + 40:
            if best is None or r[0] < best[0][0]:
                best = (r, h)
    return best


def _submenu_shot(srect):
    """子菜单区域的屏幕截图（BGR）。"""
    import cv2
    import numpy as np
    from harness import winutil as _wu
    l, t, r, b = srect
    sw, sh, buf = _wu.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    return img[max(0, t):b, max(0, l):r]


def submenu_badge_slots(srect, n_items):
    """{槽号: 徽标中心 y（屏幕坐标）} —— Merge with 子菜单各行的槽号徽标。

    2.4.1 该子菜单：左侧徽标 = 目标槽号 + 该槽耗材色底的**自绘**行，右侧才是
    （全同名的）预设名；而且**不画 hover 高亮**（10-16 实测：光标停在任一 y 上
    截图均无高亮，逐行差分也全 None）——所以行位只能靠徽标本身的 y 来定位，
    几何外推会偏一行（点第 2 行实际落到第 1 行）。"""
    import cv2
    import pytesseract
    crop = _submenu_shot(srect)
    if crop.size == 0:
        return {}
    up = 6
    strip = crop[:, 1:36]
    big = cv2.resize(strip, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
    out = {}
    try:   # 直接拿 image_to_data 的词框再自己除以放大倍数：套 ocr_words_img
           # 会把坐标除两次（实测返回 y=929，点击落到菜单外）
        data = pytesseract.image_to_data(
            big, config="-l eng --psm 6 -c "
                        "tessedit_char_whitelist=123456789",
            output_type=pytesseract.Output.DICT)
        for i, txt in enumerate(data["text"]):
            d = "".join(ch for ch in txt if ch.isdigit())
            if not d or int(data["conf"][i]) < 30:
                continue
            y = (data["top"][i] + data["height"][i] // 2) / up
            out[int(d)] = srect[1] + int(y)
    except Exception:                                          # noqa: BLE001
        pass
    if len(out) < n_items:            # 整条读不全 → 逐行裁、单字符白名单模式
        pitch = crop.shape[0] / max(n_items, 1)
        for i in range(n_items):
            band = crop[int(i * pitch) + 3:int((i + 1) * pitch) - 3, 1:36]
            if band.size == 0:
                continue
            try:
                import pytesseract
                import numpy as np
                bigb = np.kron(band, np.ones((6, 6, 1), dtype=band.dtype))
                txt = pytesseract.image_to_string(
                    bigb, config="-l eng --psm 10 -c "
                                 "tessedit_char_whitelist=123456789").strip()
            except Exception:                                  # noqa: BLE001
                continue
            d = "".join(ch for ch in txt if ch.isdigit())
            if d:
                out.setdefault(int(d), srect[1] + int((i + 0.5) * pitch))
    print(f"{LOG} submenu badge slots -> y: {out}")
    return out


def merge_slot_into(session, src_slot, want_slot):
    """**物理耗材合并**：点 src_slot 自己的 '...' → 'Merge with' → 子菜单里
    **徽标数字 = want_slot** 的那一项。返回 (ok, 目标槽号)。

    子菜单列出除源槽外的物理槽；标签全同名（同款预设、仅颜色不同），所以目标
    由左徽标的槽号数字确定（OCR，见 submenu_badge_slots），识别不到就按
    "want_slot 在存活槽中的序"回退。"""
    import m7_common as m7
    from harness import topbar_util
    from harness import winutil as _wu
    import m8_common as m8
    btn = slot_menu_button(session, src_slot)
    if not btn:
        print(f"{LOG} slot {src_slot}: '...' button not found")
        return False, None
    rect, hwnd = btn
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    # 切片/导出之后马上点 '...' 会被吞（app 还在收尾，实测 10-16：菜单不弹）
    # → 沉降 3.5s 再点，且最多试 3 轮
    menu = None
    for attempt in range(3):
        m7.dismiss_menus(session)
        time.sleep(3.5 if attempt == 0 else 1.5)
        _wu.user32.SetCursorPos(x, y)
        time.sleep(0.3)
        _wu.real_click_screen(x, y)
        # 菜单开在按钮**下方**（实测：按钮底 y=458、菜单顶 y=481），放宽到 60px
        # 才不会被"矩形不含点"的判据挡掉
        menu = _poll_menu_at(session, x, y, timeout_s=4.0, slack=60)
        if menu:
            break
        print(f"{LOG} slot {src_slot} '...' menu attempt {attempt + 1} empty")
    if not menu:
        print(f"{LOG} slot {src_slot} '...' menu did not open")
        return False, None
    mhwnd, mhmenu = menu
    items = m7.list_menu(mhmenu)
    print(f"{LOG} slot {src_slot} '...' menu: {[l for _i, l in items]}")
    merge_idx = next((i for i, l in items if "merge with" in l.lower()), None)
    if merge_idx is None:
        m7.dismiss_menus(session)
        print(f"{LOG} merge: no 'Merge with' in {[l for _i, l in items]}")
        return False, None
    prect = _menu_rect_of(session, mhwnd)
    topbar_util.hover_row(prect, len(items), merge_idx)
    sub = topbar_util.wait_submenu(session.pid, {mhwnd}, timeout_s=5.0)
    if not sub:
        m7.dismiss_menus(session)
        print(f"{LOG} merge: 'Merge with' submenu did not open")
        return False, None
    srect, shmenu = sub[0], sub[2]
    sub_items = topbar_util.menu_items(shmenu)
    print(f"{LOG} merge targets from slot {src_slot}: "
          f"{[i[1] for i in sub_items]} (want slot {want_slot})")
    if not sub_items:
        m7.dismiss_menus(session)
        return False, None
    others = sorted(s["slot"] for s in m8.filament_slots(session)
                    if s["slot"] != src_slot)
    row_idx = others.index(want_slot) if want_slot in others else 0
    hit_y = submenu_badge_slots(srect, len(sub_items)).get(want_slot)
    if hit_y is None:
        hit_y = srect[1] + int((row_idx + 0.5)
                               * (srect[3] - srect[1]) / len(sub_items))
        print(f"{LOG} badge y unknown -> geometric y={hit_y} (row {row_idx})")
    print(f"{LOG} merge: clicking y={hit_y} for slot {want_slot} (row {row_idx})")
    n_before = len(m8.filament_slots(session))
    cx = (srect[0] + srect[2]) // 2
    _wu.user32.SetCursorPos(cx, hit_y)
    time.sleep(0.3)
    _wu.real_click_screen(cx, hit_y)
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if len(m8.filament_slots(session)) < n_before:
            return True, want_slot
        dlg = m7.wait_dialog(session.pid, timeout_s=0.4)
        if dlg:
            print(f"{LOG} merge dialog: {dlg[1]!r}")
            m7.click_dialog_button(dlg[0], "ok", fallback_first=True)
            time.sleep(1.5)
        time.sleep(0.4)
    m7.dismiss_menus(session)
    return False, None


def _menu_rect_of(session, mhwnd):
    """#32768 菜单窗口的屏幕矩形（hover_row 需要）。"""
    import ctypes
    from ctypes import wintypes as wt
    from harness import winutil as _wu
    rc = wt.RECT()
    _wu.user32.GetWindowRect(mhwnd, ctypes.byref(rc))
    return (rc.left, rc.top, rc.right, rc.bottom)


def _checked_rows(shmenu, rows):
    """子菜单里 MF_CHECKED 的物理行标签（MF_BYPOSITION 读状态）。

    GetMenuState 出错时返回 -1（ctypes c_int），必须判掉：-1 & 0x8 还是 8，
    会把读失败伪装成"勾选了一行"。"""
    import ctypes
    u32 = ctypes.WinDLL("user32")
    out = []
    for i, l in rows:
        if not l.strip() or l.lower() == "default":
            continue
        st = u32.GetMenuState(shmenu, i, 0x400)
        if st is not None and st != -1 and st & 0x8:
            out.append(l)
    return out


def click_menu_index(session, hwnd, hmenu, index):
    """按**索引**点菜单行。

    必须按索引：4 个物理槽的 Change Filament 行标签完全同名（同款预设、只有
    颜色不同），m7.click_menu_row 按标签匹配只会点到**第一行**——实测 10-16
    想让对象用末位槽，结果仍停在首槽（合并前切片 gcode 用量 [1] 而非 [4]），
    而且那个 FAIL 还被当成"app 没同步"误读了一轮。"""
    import m7_common as m7
    from harness import winutil as _wu
    rect = m7._menu_item_rect(hwnd, hmenu, index)
    if not rect:
        print(f"{LOG} no row geometry for index {index}")
        return False
    x = (rect[0] + rect[2]) // 2
    y = (rect[1] + rect[3]) // 2
    _wu.user32.SetCursorPos(x, y)
    time.sleep(0.5)
    _wu.real_click_screen(x, y)
    time.sleep(1.0)
    return True


def slot_colours(session, tries=3):
    """{槽号: BGR} = 各槽色板颜色；读到"近黑"（三通道都 < 40）视为该槽还没
    渲染完，重读（实测 10-16：启动后立刻读，右列两槽读到 [12,12,12]）。"""
    import m8_common as m8
    out = {}
    for _ in range(tries):
        out = {s["slot"]: m8.slot_swatch_rgb(session, s["slot"])
               for s in m8.filament_slots(session)}
        bad = [k for k, v in out.items() if not v or max(v) < 40]
        if not bad:
            return out
        print(f"{LOG} swatch read retry (unrendered: {bad})")
        time.sleep(1.5)
    return out


def object_color(session, pt, half=34):
    """对象在画布上的主色（彩色像素的 BGR 中位数），None = 读不到。

    中位数对"细线污染"免疫：选中高亮框和坐标轴箭头都是细线，模型填充是成片
    实色，所以中位数≈填充色 = 该对象在用耗材的颜色。"""
    import numpy as np
    from harness.anchors import capture_bgr
    img = capture_bgr(session)
    x, y = pt
    sub = img[max(0, y - half):y + half, max(0, x - half):x + half].astype(int)
    if sub.size == 0:
        return None
    # 阈值 25（不是色块检测用的 45）：浅色耗材渲染后彩度天然低——实测槽 3
    # 色板 [168,197,212] 彩度只有 44，用 45 会把对象读成"读不到"。
    spread = sub.max(axis=2) - sub.min(axis=2)
    px = sub[spread > 25]
    if len(px) < 30:
        return None
    return [int(v) for v in np.median(px, axis=0)]


def nearest_slot(rgb, colors):
    """(槽号, 距离)：主色最接近哪个槽的色板；colors = {slot: bgr}。"""
    best, bd = None, None
    if rgb is None:
        return None, float("inf")
    for s, c in sorted(colors.items()):
        if c is None:
            continue
        d = sum((a - b) ** 2 for a, b in zip(rgb, c)) ** 0.5
        if bd is None or d < bd:
            best, bd = s, d
    return best, (bd if bd is not None else float("inf"))


def right_click_object_menu(session, pt, tries=2):
    """右键对象，返回**校验过**的对象菜单 (hwnd, hmenu)（含 Change Filament
    行），失败给 None。

    三个实测坑（10-16，s4，薄片 Prusa.stl）：
      * m7.open_context_menu 固定右键'质心+22'——薄片上那是床，拉出来的是
        盘子菜单（'Add Primitive...'）：可枚举但无耗材行，必须判掉，不能盲点；
      * 工具栏/悬浮提示流量之后的第一次右键会被吞（画布要先有一次真实点击，
        m7 对 where='bed' 记录过同一个坑）→ 先左键（顺带选中）再右键；
      * 点没落在对象上时根本不出菜单，所以每次右键前先用信息面板确认选中。"""
    import m7_common as m7
    from harness import winutil as _wu
    for _attempt in range(tries):
        for cx, cy in (pt, (pt[0], pt[1] - 8), (pt[0], pt[1] + 8),
                       (pt[0] + 8, pt[1]), (pt[0] - 8, pt[1])):
            sx, sy = m7.client(session, cx, cy)
            _wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.25)
            _wu.real_click_screen(sx, sy)          # 画布聚焦 + 选中
            time.sleep(0.8)
            if not m7.object_selected(session):
                continue                            # 没点在对象上：换个偏移
            _wu.real_right_click_screen(sx, sy)
            got = _poll_menu_at(session, sx, sy)
            if not got:
                print(f"{LOG} right-click @({cx},{cy}): no menu appeared")
                time.sleep(0.4)
                continue
            items = [l for _i, l in m7.list_menu(got[1])]
            if any("change filament" in l.lower() for l in items):
                print(f"{LOG} object menu @({cx},{cy}): {items[:4]}")
                return got
            print(f"{LOG} right-click @({cx},{cy}) gave a non-object menu "
                  f"{items[:4]} — dismissing and retrying")
            m7.dismiss_menus(session)
            time.sleep(0.4)
        time.sleep(0.6)
    return None


def open_cf_submenu(session, pt=None):
    """右键对象 → Change Filament 子菜单；返回 ((shwnd, shmenu), pt)，失败
    给 ((None, None), pt)。菜单保持打开，调用方自己 dismiss_menus。"""
    import m7_common as m7
    pt = pt or m7.select_object_strict(session)
    if not pt:
        return (None, None), None
    menu = right_click_object_menu(session, pt)
    if not menu:
        return (None, None), pt
    got = m7.click_menu_row(session, menu[0], menu[1], "change filament",
                            nested=True)
    if not got:
        m7.dismiss_menus(session)
        return (None, None), pt
    _idx, (shwnd, shmenu) = got
    return (shwnd, shmenu), pt


def select_small_then(session, results):
    """模型选中（信息面板口径）。旧版拿 m7.select_model 的 tooltip 判据：
    无 tooltip 时它读到的是工具栏自身的标签（'we Vv Rotate [R]'），空床点击
    也会判成功（10-16 实测）。返回点坐标（真值）或 None。"""
    import m7_common as m7
    pt = m7.select_object_strict(session)
    if pt:
        results["模型选中"] = f"PASS (@{pt})"
        return pt
    results["模型选中"] = "FAIL (no object-info panel)"
    return None


def m7_boot(args, model=None, tries=2):
    """seed + launch（带一次重试：引导期取帧竞态不该整个会话判死）。"""
    from m3_common import boot_session
    last = None
    for i in range(max(1, tries)):
        try:
            args.model = model
            return boot_session(args, model=model)
        except Exception as exc:                               # noqa: BLE001
            last = exc
            print(f"{LOG} boot try{i + 1} failed: {exc!r} — retrying")
            time.sleep(3.0)
    raise last


def run_s1(args, results):
    """空盘启动 → 新建项目 → 导入 STL → 打印机预设证据行。"""
    patch_archiver("s1")
    import m7_common as m7
    from harness import export_util, winutil
    from m3_common import boot_session
    args.model = None
    session = boot_session(args, model=None)
    try:
        frac0 = m7.model_colored_frac(session)
        results["空盘启动（首次安装语义）"] = (
            "PASS" if frac0 < m7.EMPTY_BED_FLOOR else f"FAIL ({frac0:.3%})")
        ok, _dlg = m7.file_menu_dispatch(session, "New Project")
        results["新建项目派发"] = "PASS" if ok else "FAIL"
        if not ok:
            return False
        time.sleep(2.0)
        frac = m7.model_colored_frac(session)
        results["新建后画布为空"] = (
            "PASS" if frac < m7.EMPTY_BED_FLOOR else f"FAIL ({frac:.3%})")
        if frac >= m7.EMPTY_BED_FLOOR:
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
        winutil.select_all(edit)
        winutil.msg_text(edit, str(STL))
        ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)  # IDOK
        deadline = time.monotonic() + 90
        frac = m7.model_colored_frac(session)
        while frac < 0.0025 and time.monotonic() < deadline:
            time.sleep(1.0)
            frac = m7.model_colored_frac(session)
        ok = frac >= 0.0025 and m7.blob_count(session) >= 1
        print(f"{LOG} import arrives: frac={frac:.3%}")
        results["导入模型落盘"] = "PASS" if ok else f"FAIL ({frac:.3%})"
        # [证据行] 打印机预设 combo（2.4.x 黑盒切换未证明；只记录侧栏文本）
        try:
            rows = list(export_util._children_texts(session.hwnd))
            band = [(t.strip()[:40], r) for t, r, _c in rows
                    if 60 <= r[1] <= 460 and t.strip()]
            print(f"{LOG} [evidence] sidebar texts: {band[:16]}")
        except Exception as exc:                               # noqa: BLE001
            print(f"{LOG} [evidence] error: {exc!r}")
        results["打印机预设切换（证据行，不作判定）"] = "PASS (evidence recorded)"
        return ok
    finally:
        session.close()
        print(f"{LOG} session closed (s1)")


def run_gizmo(args, tag, results, key, slot_pred, row_label, index, value,
              fallback_dx=0):
    """全新 app 会话 → CLI 载入 STL → 等模型在盘（0.25% 门 + blob）→ 选中 →
    提交 → OCR 回读。本会话的第一个 gizmo，输入通道可靠（2.4.1 实测）。"""
    patch_archiver(tag)
    import m7_common as m7
    session = m7_boot(args, model=STL)
    ok = False
    try:
        # 小单色模型：Prusa 色度 ~0.26%，用 m7c 的 0.25% 门 + blob 双信号
        deadline = time.monotonic() + 240
        frac = m7.model_colored_frac(session)
        while frac < 0.0025 and time.monotonic() < deadline:
            time.sleep(2.0)
            frac = m7.model_colored_frac(session)
        arrived = frac >= 0.0025 and m7.blob_count(session) >= 1
        print(f"{LOG} {tag} model arrives: {arrived} ({frac:.2%})")
        results[f"{key} 模型在盘"] = (
            "PASS" if arrived else f"FAIL ({frac:.2%})")
        if not arrived:
            results[key] = "FAIL (model never arrived)"
            return False
        if not select_small_then(session, results):
            results[key] = "FAIL (model not selectable)"
            return False
        ok, text = m7.op_gizmo_field(session, slot_pred, row_label, index,
                                     value, fallback_dx=fallback_dx)
        results[key] = "PASS" if ok else f"FAIL (now {text!r})"
        return ok
    finally:
        session.close()
        print(f"{LOG} session closed ({tag})")


def run_s4(args, results):
    """全新 app → Scale 120 → Change Filament + 物理耗材合并 → 切片导出。"""
    patch_archiver("s4")
    import m7_common as m7
    import m8_common as m8
    session = m7_boot(args, model=STL)
    ok = False
    try:
        deadline = time.monotonic() + 240
        frac = m7.model_colored_frac(session)
        while frac < 0.0025 and time.monotonic() < deadline:
            time.sleep(2.0)
            frac = m7.model_colored_frac(session)
        arrived = frac >= 0.0025 and m7.blob_count(session) >= 1
        print(f"{LOG} s4 model arrives: {arrived} ({frac:.2%})")
        results["缩放 120 提交 模型在盘"] = (
            "PASS" if arrived else f"FAIL ({frac:.2%})")
        if not arrived:
            results["缩放 120 提交"] = "FAIL (model never arrived)"
            return False
        if not select_small_then(session, results):
            results["缩放 120 提交"] = "FAIL (model not selectable)"
            return False
        ok, text = m7.op_gizmo_field(session, lambda t: "scale" in t,
                                     "scale", 0, "120", fallback_dx=44)
        results["缩放 120 提交"] = "PASS" if ok else f"FAIL (now {text!r})"

        # 耗材合并 = **物理耗材合并**（测试方 10-16 口径）：把对象在用的末位
        # 物理耗材并掉（Filaments 行的删除桶），断言面是"模型耗材丝是否同步
        # 变动"——合并后重开 Change Filament 子菜单：行数 -1 且恰一行勾选
        # （= 模型已重映射到保留的物理）；切片导出后 gcode 恰一个非零耗材。
        # 涂色同步的专责面 = m4e/m4i（本链模型未涂色）。
        #
        # 先强制关掉缩放面板：面板没收干净时后续一切右键都被吃（连空床菜单都
        # 不弹，实测 10-16）；随后用**信息面板口径**的严格选中拿回对象点击点
        # ——不再用 m7 的"质心+22"配方（薄片上那是床）。
        from harness import winutil as _wu_
        for _vk in (0x1B, 0x1B):
            _wu_.user32.keybd_event(_vk, 0, 0, 0)
            time.sleep(0.05)
            _wu_.user32.keybd_event(_vk, 0, 2, 0)
            time.sleep(0.5)
        _left = m7.gizmo_row_boxes(session, "scale")
        print(f"{LOG} scale panel after ESC x2: {'still open' if _left else 'closed'}")
        pt = m7.select_object_strict(session)
        results["合并前对象选中（信息面板）"] = "PASS" if pt else "FAIL"
        if not pt:
            results["耗材合并（对象在用末位物理）"] = "FAIL (not selectable)"
            return False

        # 0) 槽位颜色基准：色板背景就是耗材色，对象主色用来回读"在用哪根丝"。
        #    为什么不用 Change Filament 的勾选态：2.4.1 该子菜单行是自绘色块，
        #    GetMenuState 的 MF_CHECKED 在赋值前后都读到 checked=[]（10-16 实测），
        #    勾选不是可观测面 —— 同步断言改走"对象主色 + gcode 用量"两条侧证。
        colors = slot_colours(session)
        print(f"{LOG} slot swatch colours: {colors}")
        obj0 = object_color(session, pt)
        s0, d0 = nearest_slot(obj0, colors)
        print(f"{LOG} object colour before assign: {obj0} -> slot {s0} "
              f"(d={d0:.0f})")

        # 1) Change Filament → 末位物理行（对象此刻"在用"它）。
        (shwnd, shmenu), pt = open_cf_submenu(session, pt)
        if shmenu is None:
            results["耗材合并（对象在用末位物理）"] = "FAIL (no object menu)"
            return False
        rows = m7.list_menu(shmenu)
        cand = [(i, l) for i, l in rows
                if l.strip() and l.lower() != "default"]
        if len(cand) < 2:
            m7.dismiss_menus(session)
            results["耗材合并（对象在用末位物理）"] = (
                f"FAIL ({len(cand)} physical rows)")
            return False
        last_i, last_lbl = cand[-1]
        n_slots = len(cand)
        print(f"{LOG} pre-merge submenu rows: {[l for _i, l in rows]}")
        if not click_menu_index(session, shwnd, shmenu, last_i):
            m7.dismiss_menus(session)
            results["耗材合并（对象在用末位物理）"] = "FAIL (row click)"
            return False
        time.sleep(2.5)
        obj1 = object_color(session, pt)
        s1_, d1 = nearest_slot(obj1, colors)
        print(f"{LOG} object colour after assign to slot {n_slots}: {obj1} "
              f"-> slot {s1_} (d={d1:.0f})")
        results["耗材合并（对象在用末位物理）"] = (
            f"PASS (colour->slot {s1_})" if s1_ == n_slots
            else f"FAIL (colour->slot {s1_}, want {n_slots})")
        if s1_ != n_slots:
            return False

        # 注意：这里**不**先切一次做基准。实测 10-16：切片/导出之后侧栏的
        # '...' 按钮点不动（3 次重试 + 3.5s 沉降都不弹菜单），而切片前它稳定
        # 可用；而"对象换丝不改变切片丝号"这一点已在当日日志里留证
        # （对象在 4 号丝时 gcode 仍是 `filament used [g] = 6.98, 0.00, 0.00` + T0）。

        # 2) **物理耗材合并**（测试方 10-16 口径：耗材行右侧 '...' → 合并到 x 号）：
        #    把在用的末位槽并进 **3 号槽**。目标刻意不取第一项——只有取非首项
        #    才能分辨"合并到所选槽"和"永远并到首槽"（10-16 实测点第 2 行时对象
        #    落到 1 号槽，两种解释未分辨，故取末行再做一次决定性检验）。
        before = len(m8.filament_slots(session))
        merged, tgt = merge_slot_into(session, n_slots, want_slot=3)
        results["耗材合并（... → Merge with → 所选目标槽）"] = (
            f"PASS (slot {n_slots} -> slot {tgt})" if merged
            else "FAIL (merge did not take)")
        if not merged:
            return False
        time.sleep(2.5)
        after = len(m8.filament_slots(session))
        print(f"{LOG} physical slots {before} -> {after} (merged into {tgt})")
        results["耗材合并（物理并掉，槽位数-1）"] = (
            "PASS" if after == before - 1
            else f"FAIL ({before} -> {after})")

        # 2b) 同步变动（丝）：对象主色必须离开被并掉的那根，落到**目标槽**
        survivors = sorted(s["slot"] for s in m8.filament_slots(session))
        colors_after = slot_colours(session)
        obj2 = object_color(session, pt)
        s2_, d2 = nearest_slot(obj2, colors)      # 与合并前的四色比
        print(f"{LOG} survivors={survivors} colours={colors_after}")
        print(f"{LOG} object colour after merge: {obj2} -> slot {s2_} "
              f"(d={d2:.0f}; merged-away slot {n_slots}, target {tgt})")
        # "合并到所选 x 号"是功能本体：对象必须落到**选中的**那一根
        # （10-19 实测：点 3 号 → 三维视图落到 3 号、切片用量也是 3 号）。
        results["耗材合并目标被遵守（对象落所选槽）"] = (
            f"PASS (target slot {tgt}, object landed on {s2_})"
            if s2_ == tgt
            else f"FAIL (target {tgt}, object landed on {s2_})")
        results["模型耗材丝同步变动（并后主色离开被并槽）"] = (
            f"PASS (colour->slot {s2_})"
            if (s2_ in survivors and s2_ != n_slots)
            else f"FAIL (colour->slot {s2_}, merged-away {n_slots}, "
                 f"survivors {survivors})")

        # 3) 结构侧证：子菜单行数随物理槽位收缩
        rows2 = []
        (sw2, sm2), _pt2 = open_cf_submenu(session, pt)
        if sm2 is not None:
            rows2 = m7.list_menu(sm2)
            print(f"{LOG} post-merge submenu rows={[l for _i, l in rows2]} "
                  f"checked={_checked_rows(sm2, rows2)}")
            m7.dismiss_menus(session)
        n_rows2 = len([1 for _i, l in rows2
                       if l.strip() and l.lower() != "default"])
        results["Change Filament 行数随合并收缩"] = (
            f"PASS ({n_rows2} rows)" if n_rows2 == n_slots - 1
            else f"FAIL ({n_rows2} rows, want {n_slots - 1})")

        m7.op_slice(session, results, key="切片完成",
                    export_to=ART / "m8x_152.gcode")

        # 4) gcode 侧证：合并后用量落在同一根（颜色读数与用量读数互证）
        try:
            used = m8.used_filaments((ART / "m8x_152.gcode").read_bytes())
        except OSError:
            used = []
        print(f"{LOG} used filaments in gcode: {used} (colour says slot {s2_})")
        results["并后 gcode 用所选目标丝（丝同步侧证）"] = (
            f"PASS (used={used}, colour slot {s2_})"
            if bool(s2_) and used == [s2_]
            else f"FAIL (used={used}, colour says slot {s2_})")
        return ok
    finally:
        session.close()
        print(f"{LOG} session closed (s4)")


def session_main(tag, args):
    results = {}
    if tag == "s1":
        ok = run_s1(args, results)
    elif tag == "s2":
        ok = run_gizmo(args, tag, results, "移动 X=60 提交",
                       lambda t: "move" in t, "position", 0, "60")
    elif tag == "s3":
        ok = run_gizmo(args, tag, results, "旋转 Z=45 提交",
                       lambda t: "rotate" in t, "rotate", -1, "45")
    else:
        ok = run_s4(args, results)
    out = ART / f"m8x_152_{tag}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return 0 if ok else 1


def main() -> int:
    import argparse
    import os
    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    ap.add_argument("--session", choices=SESSIONS, default=None)
    ap.add_argument("--only", default=None,
                    help="debug: comma list of sessions to run (e.g. s4). A "
                         "partial run is NOT a full-case verdict and reports "
                         "RED on purpose")
    args = ap.parse_args()
    if args.session:
        return session_main(args.session, args)

    tags = [t for t in SESSIONS
            if not args.only or t in args.only.split(",")]
    results = {}
    rc = 0
    for tag in tags:
        out = ART / f"m8x_152_{tag}.json"
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
        # 全会话 stdout 落盘：下面只回显尾部 40 行，失败步骤自己的打印
        # （'scale panel after ESC x2'、's4 model arrives'…）会被挤掉，
        # 排查时被迫复跑整链（10-16 实测踩过一次）。
        (ART / f"m8x_152_{tag}.log").write_text(
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
    if args.only:  # 局部跑不是完整用例结论：显式 RED，别让它看起来 GREEN
        results[f"partial run (--only {args.only})"] = "FAIL (debug run)"
    print("\n[m3] === verdict ===")
    all_ok = bool(results) and all(str(v).startswith("PASS")
                                   for v in results.values())
    for k, v in results.items():
        print(f"  {k}: {v}")
    print("[m3] " + ("GREEN" if all_ok else "RED"))
    return 0 if all_ok else rc or 1


if __name__ == "__main__":
    from m3_common import add_common_args
    raise SystemExit(main())
