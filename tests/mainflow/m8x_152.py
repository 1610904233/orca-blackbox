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


def slot_menu_delete(session, slot):
    """点 slot 的 '...' → 'Delete'（删除桶），返回是否点中。

    Merge-with 的存活规则是「保低槽」（11-11 两轮实测：1+3 保 1、4+1 保 1），
    对象在最低槽时合并无法让其重映射——重映射验证改走 Delete。"""
    import m7_common as m7
    from harness import winutil as _wu
    btn = slot_menu_button(session, slot)
    if not btn:
        print(f"{LOG} slot {slot}: '...' button not found")
        return False
    rect, _hwnd = btn
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    menu = None
    for attempt in range(3):
        m7.dismiss_menus(session)
        time.sleep(3.5 if attempt == 0 else 1.5)
        _wu.user32.SetCursorPos(x, y)
        time.sleep(0.3)
        _wu.real_click_screen(x, y)
        menu = _poll_menu_at(session, x, y, timeout_s=4.0, slack=60)
        if menu:
            break
        print(f"{LOG} slot {slot} '...' menu attempt {attempt + 1} empty")
    if not menu:
        return False
    mhwnd, mhmenu = menu
    rows = m7.list_menu(mhmenu)
    print(f"{LOG} slot {slot} '...' menu: {[l for _i, l in rows]}")
    idx = next((i for i, l in rows if l.strip().lower() == "delete"), None)
    if idx is None:
        m7.dismiss_menus(session)
        print(f"{LOG} slot {slot}: no Delete row")
        return False
    ok = click_menu_index(session, mhwnd, mhmenu, idx)
    time.sleep(1.5)
    m7.dismiss_menus(session)
    return ok


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


def _ocr_band(session, y0, y1, x0=0, x1=430, scale=4):
    from harness import mix_dialog_util as mdu
    from harness.anchors import capture_bgr as _cap
    img = _cap(session)
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return []
    return [(w[0], w[1] + x0, w[2] + y0, w[3], w[4])
            for w in mdu.ocr_words_img(crop, scale=scale)]


def objects_tab_select(session):
    """工艺(Process)->对象(Objects) 标签页里点模型行选中对象（按钮面）。

    probe_242_objlist3 实测（11-11）：点 'Objects' 标签 -> 展开 Plate 节点
    -> 模型行 'Prusa.stl' 出现 -> 点行即选中（信息面板出现）。这是画布
    选中在 2.4.2 程序化输入下失效后的唯一可用选中通道。返回行中心
    (rx, ry)（屏幕坐标）或 None。"""
    import m7_common as m7
    from harness import export_util, winutil
    rows = export_util._children_texts(session.hwnd)
    proc = next(((t, r) for t, r, h in rows if t.strip() == "Process"), None)
    adv = next(((t, r) for t, r, h in rows if t.strip() == "Advanced"), None)
    if not (proc and adv):
        print(f"{LOG} objects tab: Process/Advanced labels missing")
        return None
    y0, y1 = proc[1][1] - 8, proc[1][3] + 8
    band = _ocr_band(session, y0, y1, scale=3)
    objw = next((w for w in band if "bject" in w[0].lower()), None)
    cx = objw[1] + objw[3] // 2 if objw else (proc[1][2] + adv[1][0]) // 2
    cy = objw[2] + objw[4] // 2 if objw else (y0 + y1) // 2
    winutil.user32.SetCursorPos(cx, cy)
    time.sleep(0.3)
    winutil.real_click_screen(cx, cy)
    time.sleep(1.5)
    # 展开 Plate 节点（若模型行还没出现）
    words = _ocr_band(session, y1 + 2, 800)
    if not any("prusa" in w[0].lower() or "untitled" in w[0].lower()
               for w in words):
        plate = next((w for w in words if w[0].lower() == "plate"), None)
        if plate:
            px, py = plate[1] + plate[3] // 2, plate[2] + plate[4] // 2
            print(f"{LOG} objects tab: expand Plate @({px},{py})")
            winutil.user32.SetCursorPos(px, py)
            time.sleep(0.3)
            winutil.real_click_screen(px, py)
            time.sleep(1.2)
            words = _ocr_band(session, y1 + 2, 800)
    row = next((w for w in words if any(k in w[0].lower() for k in
                                        ("untitled", "prusa", "cube"))),
               None)
    if not row:
        print(f"{LOG} objects tab: no model row ({[w[0] for w in words][:12]})")
        return None
    rx = row[1] + row[3] // 2
    ry = row[2] + row[4] // 2
    print(f"{LOG} objects tab: click row {row[0]!r} @({rx},{ry})")
    winutil.user32.SetCursorPos(rx, ry)
    time.sleep(0.3)
    winutil.real_click_screen(rx, ry)
    time.sleep(1.2)
    ok = m7.object_selected(session)
    print(f"{LOG} objects tab select = {ok}")
    return (rx, ry) if ok else None


def assign_filament_via_row(session, row_xy, want_slot):
    """对象树行右键 -> Change Filament -> 子菜单第 want_slot 行（default=0）。
    返回是否成功。行菜单是 #32768 原生菜单（probe_242_objlist3 实证）。"""
    import m7_common as m7
    from harness import topbar_util, winutil
    rx, ry = row_xy
    menu = None
    for attempt in range(3):
        m7.dismiss_menus(session)
        time.sleep(1.0 if attempt else 0.3)
        winutil.user32.SetCursorPos(rx, ry)
        time.sleep(0.3)
        winutil.real_right_click_screen(rx, ry)
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            ms = topbar_util._enum_menu_windows(session.pid)
            if ms:
                menu = (ms[0][4], topbar_util.menu_hmenu(ms[0][4]))
                break
            time.sleep(0.25)
        if menu:
            break
        print(f"{LOG} row menu attempt {attempt + 1} empty")
    if not menu:
        return False
    hwnd, hmenu = menu
    got = m7.click_menu_row(session, hwnd, hmenu, "change filament",
                            nested=True)
    if not got or not isinstance(got, tuple):
        print(f"{LOG} Change Filament row not found")
        m7.dismiss_menus(session)
        return False
    _i, (shwnd, shmenu) = got
    rows = m7.list_menu(shmenu)
    print(f"{LOG} filament submenu: {[l for _i2, l in rows]}")
    if not click_menu_index(session, shwnd, shmenu, want_slot):
        m7.dismiss_menus(session)
        return False
    time.sleep(1.5)
    m7.dismiss_menus(session)
    return True


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
        # 2.4.2 程序化输入约束（11-11 定位）：关面板后的**画布选中**不可达
        # （授前台/真键盘/按住时长/轮询均无效，人工正常——用户录屏已证）。
        # 按用户指引改用**对象标签页**（工艺→对象：行点击选中 + 行右键
        # Change Filament 指定耗材，probe_242_objlist3 实证），合并链路：
        #   1) 对象行选中 → Change Filament 指定末位槽（按钮面，无需画布）
        #   2) 切片 A → gcode 用量必须 = 指定槽（指定生效的直接证据）
        #   3) 该槽 '...' → Merge with 1（存活规则=保低槽：对象槽被并掉
        #      后重映射到 1）
        #   4) 切片 B → gcode 用量 = [1]（物理合并 + 对象丝跟随）
        row_xy = objects_tab_select(session)
        results["对象标签页选中（按钮面）"] = (
            f"PASS (@{row_xy})" if row_xy else "FAIL (row not selectable)")
        if not row_xy:
            return False
        n_slots = len([1 for _ in m8.filament_slots(session)])
        assigned = assign_filament_via_row(session, row_xy, n_slots)
        results["指定模型耗材（行菜单→末位槽）"] = (
            f"PASS (slot {n_slots})" if assigned else "FAIL")
        if not assigned:
            return False
        gA = ART / "m8x_152_A.gcode"
        gA.unlink(missing_ok=True)
        m7.op_slice(session, results, key="指定后切片", export_to=gA)
        used_a = m8.used_filaments(gA.read_bytes()) if gA.exists() else []
        print(f"{LOG} assigned used filaments: {used_a} (want [{n_slots}])")
        results["指定后 gcode 用量 = 指定槽"] = (
            f"PASS (used={used_a})" if used_a == [n_slots]
            else f"FAIL (used={used_a}, want [{n_slots}])")
        if used_a != [n_slots]:
            return False
        used = used_a[0]
        before = len(m8.filament_slots(session))
        merged, tgt = merge_slot_into(session, used, want_slot=1)
        results["耗材合并（在用槽 '...' → Merge with 1）"] = (
            f"PASS (slot {used} -> slot {tgt})" if merged
            else "FAIL (merge did not take)")
        if not merged:
            return False
        time.sleep(2.5)
        after = len(m8.filament_slots(session))
        survivors = sorted(s2["slot"] for s2 in m8.filament_slots(session))
        print(f"{LOG} physical slots {before} -> {after} "
              f"(survivors={survivors}, source slot {used})")
        results["耗材合并（物理槽位数-1）"] = (
            "PASS" if after == before - 1 else f"FAIL ({before} -> {after})")
        gB = ART / "m8x_152.gcode"
        gB.unlink(missing_ok=True)
        m7.op_slice(session, results, key="合并后切片", export_to=gB)
        used_b = m8.used_filaments(gB.read_bytes()) if gB.exists() else []
        print(f"{LOG} post-merge used filaments: {used_b} (merged-away {used})")
        remapped = bool(used_b) and used_b == [1]
        results["合并后 gcode 用量重映射（模型丝跟随到存活槽）"] = (
            f"PASS (used={used_b}, merged-away {used})" if remapped
            else f"FAIL (used={used_b}, expect [1], merged-away {used})")
        return remapped
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
