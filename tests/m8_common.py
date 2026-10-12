#!/usr/bin/env python3
# m8_common.py — shared ops for the m8 batch (飞书「基线用例」base
# EDUAbYWcbaL2HOsgFM1cXmBpn5f, table tblvh0eGrID9JQ02: Fit view #16-#19,
# official color dialog #44-#48/#55-#59, temperature-mixing gate #111/#112,
# purifier gcode #113/#114/#122/#126-#129, high-flow nozzle #133/#135/#136).
#
# Ops are composed from the primitives the older milestones proved:
#   - filament slots are a 2-column grid of [chip][combo][picker] triples
#     (measured 09-17 on the mixed fixture: slot1 combo [38,410,178,440],
#     picker [183,413,199,436], slot2 combo [236,410,388,440])
#   - preset combos are SELF-DRAWN: popup rows probed at the m3e 28px pitch
#     with GetWindowText readback (m3e.switch_preset contract)
#   - the color picker is a 20 DIP bitmap button (clr_picker) next to each
#     combo; ChangeExtruderColor opens the OFFICIAL FilamentColorDialog only
#     for Snapmaker-named presets (PresetComboBoxes.cpp:1067) and falls back
#     to the legacy wx colour dialog otherwise
#   - the Fit camera button is the ImGui FitCameraButtonWindow (GLCanvas3D
#     :7050, tooltip "Fit in all view"); ZoomToFit() (:2824): selection ->
#     zoom_to_selection, assemble canvas -> zoom_to_volumes, else
#     zoom_to_bed. On the maximized rig it sits at client
#     (VIEWPORT_X0+152, height-44) — measured by diag_m8_probe (09-17,
#     blob area 39k -> 424k on click)
#   - purifier gcode comes from the U1 machine start template:
#     SET_PURIFIER_MODE MODE=3 DESIRE_TEMP=45 ... DELAY_OFF=600 (keep-warm),
#     MODE=1 DESIRE_TEMP=42 ALARM_TEMP=45 DELAY_OFF=0 (strong), MODE=3
#     DESIRE_TEMP=0 ... DELAY_OFF=600 (weak) — mode derived in
#     GCode.cpp:2722 from temperature_vitrification (<=50 strong, <=70
#     weak, high-temp filaments skip -> keep-warm)

import ctypes
import ctypes.wintypes as wt
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
from harness.anchors import capture_bgr  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m8]"
ART = HERE / "artifacts"
user32 = ctypes.WinDLL("user32")

# Fit button client offset on the maximized rig (diag_m8_probe 09-17)
FIT_X_OFF = 152
FIT_Y_FROM_BOTTOM = 44

# purifier start-gcode line, asserted param sets per cooling class
PURIFIER_RE = re.compile(rb"SET_PURIFIER_MODE[^\r\n]*")


def fit_click(session):
    """Click the Fit camera button (bottom-left of the canvas)."""
    img = capture_bgr(session)
    h = img.shape[0]
    sx, sy = m7.client(session, m7.VIEWPORT_X0 + FIT_X_OFF,
                       h - FIT_Y_FROM_BOTTOM)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.3)
    winutil.msg_click_screen(sx, sy, session.hwnd)
    time.sleep(1.5)


def blob_stats(img):
    """Largest chromatic blob in the viewport: area / bbox / centroid."""
    import cv2
    import numpy as np
    h, w = img.shape[:2]
    x0, y0, x1, y1 = m7.VIEWPORT_X0 + 10, 110, w - 10, h - 60
    band = img[y0:y1, x0:x1].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _lbl, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    best, best_area = None, 0
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a > best_area:
            best, best_area = i, a
    if best is None:
        return None
    i = best
    return {
        "area": int(best_area),
        "bbox": [int(stats[i, cv2.CC_STAT_LEFT]) + x0,
                 int(stats[i, cv2.CC_STAT_TOP]) + y0,
                 int(stats[i, cv2.CC_STAT_WIDTH]),
                 int(stats[i, cv2.CC_STAT_HEIGHT])],
        "centroid": [int(cents[i][0]) + x0, int(cents[i][1]) + y0],
    }


def viewport_diff(img_a, img_b):
    """Fraction of pixels that changed meaningfully between two frames."""
    import numpy as np
    return float((abs(img_b.astype(int) - img_a.astype(int))
                  .sum(axis=2) > 40).mean())


# --- filament slot grid -------------------------------------------------------

def filament_slots(session):
    """[{slot, combo(text,rect,hwnd), picker_rect, swatch_rect}] from the
    sidebar child tree.

    STRUCTURAL, not band-based: the numbered chips are found by their text
    ('1'..'5', a small button), and each row's combo / legacy picker is matched
    by sharing the chip's row (same centre y, to the right of the chip). The
    previous version scoped rows with the 'Filaments' label + a fixed y band and
    an x<425 filter calibrated on the 1200x800 window — under the MAXIMIZED
    layout (1920x1080) that band matched only ONE row (measured 09-28: slots ==
    [(5, ...)]), so every slot lookup failed.

    It also computed `picker` OUTSIDE the per-chip loop, so every slot was
    handed the LAST row's rectangle — that is why clicking slot 2's colour
    control opened the wrong thing (leading, via the legacy Edit menu, to the
    native colour picker instead of the official library).

    `swatch` is the numbered chip itself: its background is the filament colour
    and, for Snapmaker presets, clicking it opens the OFFICIAL colour library
    (probe 09-28: chip '2' -> popup carrying 'Official Filaments' / 'sku
    34205'). `picker` is the 16x25 button to its right, whose click opens the
    legacy Edit/Delete/Merge #32768 menu.
    """
    rows = list(export_util._children_texts(session.hwnd))
    chips, texts, smalls = [], [], []
    for text, rect, ch in rows:
        if rect[0] > 520 or rect[2] <= rect[0]:     # sidebar only, sane rect
            continue
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        t = text.strip()
        if t.isdigit() and len(t) <= 2 and w <= 30 and h <= 32:
            chips.append((int(t), rect))
        elif 12 <= w <= 30 and 16 <= h <= 30:
            smalls.append(rect)
        elif t and w >= 60:
            texts.append((t, rect, ch))
    out = []
    for no, chip_rect in sorted(chips):
        cy = (chip_rect[1] + chip_rect[3]) / 2
        combo = None
        for text, rect, ch in texts:
            ry = (rect[1] + rect[3]) / 2
            if abs(ry - cy) < 12 and chip_rect[2] <= rect[0] <= chip_rect[2] + 20:
                if combo is None or rect[0] < combo[1][0]:
                    combo = (text, rect, ch)
        picker = None
        for rect in smalls:
            ry = (rect[1] + rect[3]) / 2
            if abs(ry - cy) < 12 and rect[0] > chip_rect[2] - 6:
                if picker is None or rect[0] < picker[0]:
                    picker = rect
        out.append({"slot": no, "combo": combo, "picker": picker,
                    "swatch": chip_rect})
    return out



def wait_slots(session, timeout_s=25.0):
    """filament_slots() once the sidebar actually exposes the slot rows.

    The sidebar is populated ASYNCHRONOUSLY: reading the child tree right after
    the GL canvas reports ready returns no slot rows at all, which surfaced as
    "slot 2 combo not found" and killed the whole case in its first step
    (measured 09-28 — the early system-preset re-apply). Poll instead of
    assuming the layout exists."""
    deadline = time.monotonic() + timeout_s
    slots = filament_slots(session)
    while time.monotonic() < deadline:
        if any(s.get("combo") for s in slots):
            return slots
        time.sleep(0.5)
        slots = filament_slots(session)
    print(f"{LOG} wait_slots: no slot combo appeared within {timeout_s:.0f}s "
          f"({[{k: (v is not None) for k, v in s.items() if k != 'slot'} for s in slots]})")
    return slots


def combo_text(ch):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(ch, buf, 256)
    return buf.value


def _ocr_click_line(session, popup_rect, target_substr, popup_hwnd=None) -> bool:
    """OCR the POPUP window and click the line matching target_substr.

    The popup is a separate top-level window: the main-window capture does not
    contain it (a first cut OCR'd the panel underneath and read 'Advanced',
    'Multimaterial' — measured 09-21), so capture the popup itself.
    """
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from harness import mix_dialog_util as mdu  # noqa: PLC0415
    if popup_hwnd:
        try:
            w, h, buf = winutil.capture_window(popup_hwnd)
            img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(h, w, 4),
                               cv2.COLOR_BGRA2BGR)
        except Exception as exc:  # noqa: BLE001
            # PrintWindow times out while the app is busy (WinError 1460,
            # measured 09-23 across a whole filament-switch loop) — fall back
            # to a SCREEN grab cropped to the popup rect: the popup is a
            # top-level window, so the desktop shows it.
            print(f"{LOG} popup PrintWindow failed ({exc}) — screen crop")
            img = capture_bgr(session)
            x0, y0, x1, y1 = [int(v) for v in popup_rect]
            img = img[max(0, y0):y1, max(0, x0):x1]
        ox, oy = popup_rect[0], popup_rect[1]
    else:
        img = capture_bgr(session)
        ox = oy = 0
    if img.size == 0:
        return False
    try:
        words = mdu.ocr_words_img(img, scale=3, psm=6)
    except Exception as exc:  # noqa: BLE001
        # tesseract can fail to allocate while the app holds most of the
        # guest's RAM (pix_malloc fail, measured 09-23) — degrade to "row not
        # read this step" so the scroll loop retries instead of crashing
        print(f"{LOG} popup OCR failed ({exc}) — retrying")
        return False
    tokens = [t.lower() for t in re.split(r"\s+", target_substr) if t]
    lines: dict[int, list] = {}
    for wd in words:
        lines.setdefault(round(wd[2] / 8), []).append(wd)
    for key in sorted(lines):
        row = sorted(lines[key], key=lambda wd: wd[1])
        line_text = " ".join(wd[0] for wd in row).lower()
        if tokens and all(t in line_text for t in tokens):
            cx = ox + row[0][1] + row[0][3] // 2
            cy = oy + row[0][2] + row[0][4] // 2
            print(f"{LOG} popup OCR row {line_text!r} -> click ({cx},{cy})")
            winutil.msg_click_screen(cx, cy)   # popup is top-level: no root
            return True
    return False


def _real_wheel(x, y, notches):
    """Real (input-queue) wheel scroll at a screen point.

    Self-contained on purpose: some app popups ignore message-level
    WM_MOUSEWHEEL — the filament preset list never moved on 2.4.0, so an
    alphabetically earlier target ('Snapmaker PLA Rainbow' above the current
    selection) stayed unreachable (measured 09-28: 11 attempts OCR'd the same
    lower window). Inlined via ctypes so no harness-side change has to be
    shipped alongside the case."""
    import ctypes  # noqa: PLC0415
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.1)
    u.mouse_event(0x0800, 0, 0, 120 * int(notches), 0)


def click_popup_row(session, popup_rect, target_substr, popup_hwnd=None,
                    scrolls=14, notch=3) -> bool:
    """Find the target row in the popup (OCR of the POPUP window), scrolling.

    Rows are SELF-DRAWN (child enumeration yields nothing) and the popup shows
    only ~13 rows, so a click-walk at the historical 28px pitch stalls once it
    passes the visible area (measured 09-21 — it parked on 'Bambu PAHT-CF'
    while 'Generic ABS' stayed below the fold). The popup opens AT the current
    selection, so scroll to the top first, then walk down, re-OCR-ing each step.
    Wheel goes through WM_MOUSEWHEEL (message-level: no focus needed).
    """
    if popup_hwnd is None:
        return _ocr_click_line(session, popup_rect, target_substr)
    x = (popup_rect[0] + popup_rect[2]) // 2
    y = (popup_rect[1] + popup_rect[3]) // 2
    lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)

    def wheel(notches: int) -> None:
        wparam = (((-120 * notches) & 0xFFFF) << 16)   # negative delta = down
        winutil._send_msg(popup_hwnd, 0x020A, wparam, lparam)

    wheel(-scrolls * 2)          # first: back to the top of the list
    time.sleep(0.7)
    for _step in range(scrolls * 2 + 1):
        if _ocr_click_line(session, popup_rect, target_substr, popup_hwnd):
            return True
        wheel(notch)
        time.sleep(0.5)
    # Second pass with REAL wheel input: on 2.4.0 the preset popup ignored
    # message-level WM_MOUSEWHEEL (the OCR window never moved, so a target
    # ABOVE the opening position was unreachable — measured 09-28).
    print(f"{LOG} popup: message-level wheel found nothing — retrying with real input")
    _real_wheel(x, y, -scrolls)
    time.sleep(0.7)
    for _step in range(scrolls + 1):
        if _ocr_click_line(session, popup_rect, target_substr, popup_hwnd):
            return True
        _real_wheel(x, y, max(1, notch // 2))
        time.sleep(0.45)
    return False


# --- 2.4.1 two-level filament picker (vendor -> type) ------------------------
#
# 产品文档《准备页——耗材分类管理》V0.1（9-29）：耗材下拉框改成三大分组
# （项目预设 / 用户配置 / 系统配置），系统配置内部是**两级菜单**：一级供应商
# （Snapmaker → Generic → 其他厂商字典序），二级耗材类型（Snapmaker 层 8 项置顶）；
# 二次打开按"回显"定位到已选材料；用户预设（我们的 `- STD-TEST` 包）在
# **用户配置 → 自定义**（测试方 10-10 口述）。
#
# 2.4.1 实测（10-08..10-10）:
#   * 消息级点击**打不开**这个弹层，必须**真实点击**；
#   * 槽位行的 combo 打开的是**当前供应商的二级耗材列表**（回显定位）；
#     行尾 16x25 Button 打开的是**一级（供应商/分组）列表**；
#   * 弹层里消息级滚轮无效、**真实滚轮有效**；
#   * 二级行的文本是**短名**（'ABS' / 'PLA Matte'），选完后 combo 显示全名
#     （'Snapmaker ABS'）。
#
# 所以 2.4.1 上"按名字平铺搜"永远找不到 `Generic ABS`（它在 Generic 分支下）——
# 这里实现两级导航，并保留老的平铺行走作为 2.4.0 兜底。

def _screen_ocr_rows(rect, psm=6, scale=3):
    """[(y_center, text, x_left)] of the screen region.

    scale=3 by default: on 2.4.1 the pane's preset rows are small and 2x OCR only
    picked up the bold category headers ('ABS'/'PETG'/'PLA'), so targets like
    'PLA Silk' never matched (measured 10-10). A 2x second pass fills in rows the
    3x pass missed.
    """
    from harness import mix_dialog_util as _mdu
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    x0, y0, x1, y1 = [int(v) for v in rect]
    crop = img[max(0, y0):y1, max(0, x0):x1]

    def rows_at(sc):
        words = _mdu.ocr_words_img(crop, scale=sc, psm=psm)
        lines = {}
        for t, x, y, w, h in words:
            key = next((k for k in lines if abs(k - y) <= 12), y)
            lines.setdefault(key, []).append((x + x0, y + y0, t))
        out = []
        for k in sorted(lines):
            v = sorted(lines[k])
            out.append((v[0][1] + 9, " ".join(t for _x, _y, t in v), v[0][0]))
        return out

    out = rows_at(scale)
    if len(out) < 4:                 # 行太少 → 用 2x 再读一遍合并（按 y 去重）
        seen = {y for y, _t, _x in out}
        for y, t, x in rows_at(2):
            if not any(abs(y - s) <= 6 for s in seen):
                out.append((y, t, x))
                seen.add(y)
        out.sort(key=lambda r: r[0])
    return out


def _row_click(session, x, y):
    """真实点击自绘行（2.4.1 上消息级点击对弹层无效）。"""
    winutil.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(0.9)


def _picker_open(session, slot):
    """打开槽位选择框：(popup, combo_hwnd, opened_by)。真实点击优先、消息级兜底。

    combo 打开二级、行尾 Button 打开一级；两处都试，返回实际开出来的弹层。"""
    slots = wait_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit["combo"]:
        return None, None, ""
    _text, rect, ch = hit["combo"]
    targets = []
    if hit.get("picker"):
        r = hit["picker"]
        targets.append(("picker", (r[0] + r[2]) // 2, (r[1] + r[3]) // 2))
    targets.append(("combo", (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2))
    for tag, cx, cy in targets:
        winutil.user32.SetCursorPos(int(cx), int(cy))
        time.sleep(0.25)
        winutil.real_click_screen(int(cx), int(cy))
        time.sleep(1.2)
        pop = export_util.wait_popup(session.pid, timeout_s=4.0)
        if pop:
            return pop, ch, tag
        winutil.msg_click_screen(cx, cy, session.hwnd)
        time.sleep(1.0)
        pop = export_util.wait_popup(session.pid, timeout_s=3.0)
        if pop:
            return pop, ch, tag + "+msg"
    return None, ch, ""


def _picker_is_vendor_level(rows):
    """一级（供应商/分组）列表的特征：分组标题或已知厂商行成片出现。"""
    blob = " ".join(t for _y, t, _x in rows).lower()
    if "system presets" in blob or "add/remove filament" in blob:
        return True
    vendors = ("snapmaker", "generic", "polymaker", "bambu", "aliz", "sunlu",
               "esun", "valment", "overture", "fusrock", "fdplast", "nit")
    return sum(1 for v in vendors if v in blob) >= 3


def _picker_click_vendor(session, vend, vendor, session_hwnd_hint=None):
    """点左栏的厂商/分组行——**逐个候选 + 右栏回读验证**。

    2.4.1 的"回显行"会被 OCR 读得跟厂商行一模一样（实测：选中 'Generic ABS' 后，
    回显行 OCR 成 'Generic'），直接点它会把弹层点关。所以每个候选点完后重读右栏，
    内容没变就试下一个候选。
    """
    # 先把左栏滚到顶：上一次选择后列表可能停在底部（实测 'Generic' 会滚出视野，
    # 导致后续切换全部失败）。滚完重新 OCR。
    for _i in range(10):
        winutil.real_wheel_screen(vend["rect"][0] + 40,
                                  (vend["rect"][1] + vend["rect"][3]) // 2, 3)
        time.sleep(0.1)
    time.sleep(0.5)
    vend = next((p for p in _picker_panes(session) if p["is_vendor"]), vend)

    low = vendor.lower().strip()

    def row_cands():
        out = []
        for y, text, x in vend["rows"]:
            tl = text.strip().lower()
            if not tl or "@" in tl or "nozzle" in tl or tl.startswith("---"):
                continue
            if tl.startswith(low) and len(tl) <= len(low) + 8:
                out.append((y, text.strip(), x, tl.endswith(">")))
        out.sort(key=lambda c: (not c[3], c[0]))          # 带 '>' 的优先
        return out

    cands = row_cands()
    if not cands:
        # 当前展开分支那行 OCR 读不到（实测）→ 用相邻厂商行插值定位
        y, x = _picker_row_y(vend, vendor)
        if y:
            print(f"{LOG} vendor {vendor!r} 不在 OCR 行表里 → 插值 y={y} 直接 hover+click")
            cands = [(y, f"<interp {vendor}>", x, True)]
    if not cands:
        return ""
    before = _filament_pane(session)
    before_rows = [t for _y, t, _x in before["rows"]] if before else []
    for i, (y, text, x, _arrow) in enumerate(cands):
        cx = max(20, x) + 55
        print(f"{LOG} vendor candidate {text!r} -> hover+real click ({cx},{y}) [{i + 1}/{len(cands)}]")
        _picker_hover(session, cx, y)          # hover 即切右栏（2.4.1 语义）
        _row_click(session, cx, y)
        time.sleep(0.9)
        now = _filament_pane(session)
        now_rows = [t for _y, t, _x in now["rows"]] if now else []
        if now is not None and now_rows != before_rows:
            return text
        # 弹层整个消失（点到回显行/选中项会把弹层点关）或右栏没变 → 该候选无效，试下一个
        print(f"{LOG}   candidate无效（pane={bool(now)}，rows_changed={now_rows != before_rows}）"
              f" — 试下一个")
        if now is None:
            time.sleep(0.4)
    return ""


def _picker_click_text(session, rows, needle, exact_word=False, limit=40,
                       startswith=False, skip_echo=True):
    """在已 OCR 的栏位里找 needle 并真实点击（点行文本起点右侧 55px）。

    * skip_echo：跳过"当前耗材回显行"（含 '@' / 'nozzle'）——左栏第一行就是它，
      子串匹配会把它当成厂商行点掉（实测 10-10：'Snapmaker PLA Silk @U1 0.8 noz…'
      吃掉了 'Snapmaker' 的匹配，导致弹层被点关、导航中断）。
    * startswith：厂商行用前缀匹配（OCR 可能带箭头/尾随字符，整行相等太脆）。
    """
    low = needle.lower().strip()
    if not low:
        return ""
    def norm(t: str) -> str:
        # OCR 易混字符归一：l/i/1 与 o/0（实测 'PLA Silk' 被读成 'PLASIIK'）
        t = re.sub(r"[^0-9a-z]+", "", t.lower())
        return t.replace("i", "l").replace("1", "l").replace("0", "o")

    norm_low = norm(low)

    # 厂商行：优先带 '>' 子菜单箭头、且不含分节标题/回显行（实测 '------ 垄 ABS @U1…' 会被误点）
    if startswith:
        rows = sorted(rows, key=lambda r: (rl := r[1].strip().lower(),
                                           not rl.endswith(">"), rl.startswith("---")))
    for y, text, x in rows[:limit]:
        tl = text.strip().lower()
        if not tl:
            continue
        if skip_echo and ("@" in tl or "nozzle" in tl):
            continue
        if exact_word:
            ok = (tl == low)
        elif startswith:
            ok = tl.startswith(low) and len(tl) <= len(low) + 8
        else:
            ok = (low in tl) or (norm_low and norm_low in norm(tl))
        if not ok:
            continue
        cx = max(20, x) + 55
        print(f"{LOG} picker row {text.strip()!r} -> real click ({cx},{y})")
        _row_click(session, cx, y)
        return text.strip()
    print(f"{LOG} picker: {needle!r} not matched in {len(rows)} row(s) "
          f"{[t[:18] for _y, t, _x in rows[:6]]}")
    return ""


def _picker_row_tooltip(session, pane, y, dwell_s=1.3):
    """OCR the tooltip shown while hovering the pane row at `y` (full name).

    2.4.1 的用户预设行**被面板宽度截断**（实测 10-12：三行都读成
    'Snapmaker PLA' / '~ Snapmaker PLA SnapS...'，目标后缀 '- STD-TEST' 永远
    匹配不到）；hover 后的 tooltip 才是全名：
      'PLA SnapSpeed @U1 - FLOW-TEST' / '- HF-TEST' / '- STD-TEST'。
    """
    import cv2
    import numpy as np
    from harness import mix_dialog_util as _mdu
    hx = pane["rect"][0] + 60
    winutil.user32.SetCursorPos(int(hx), int(y))
    time.sleep(dwell_s)
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    x0 = max(0, pane["rect"][0] - 10)
    x1 = pane["rect"][2] + 330          # tooltip 比栏宽，向右溢出（实测）
    y0, y1 = int(y) + 6, int(y) + 40
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return ""
    words = [w[0] for w in _mdu.ocr_words_img(crop, scale=3, psm=6)]
    return " ".join(words)


def _picker_tooltip_scan(session, pane, needle):
    """行文本被截断时的兜底：逐行 hover 读 tooltip 全名，命中即点。"""
    low = needle.lower().strip()
    if not low:
        return ""
    for y, t, x in pane["rows"]:
        tip = _picker_row_tooltip(session, pane, y)
        if not tip:
            continue
        print(f"{LOG} picker tooltip y={y}: {tip!r}")
        if low in tip.lower():
            cx = max(pane["rect"][0] + 20, x) + 55
            print(f"{LOG} picker tooltip hit -> click ({cx},{y})")
            _row_click(session, cx, y)
            return t.strip()
    return ""


def _picker_scan_for(session, pane, needle, steps=18, notch=-1, **kw):
    """逐档滚动找 needle：**每档都 OCR 一次并尝试点击**。

    2.4.1 实测（10-12，pscan2）：右栏一次 -3 档会跨过 ~7 行，目标行（如 'PLA Rainbow'）
    正好落在两屏之间被跳过；-1 档约 2 行、相邻屏有重叠，不会漏。列表本身很短
    （Snapmaker 二级 ~24 项 ≈ 3 屏），所以整表走一遍很便宜。

    先**回顶**再向下走：弹层开在"回显行"处，目标可能在当前视口**上方**
    （实测 m8d：ABS→PC 时右栏停在 ABS 附近，而目标在下方；反过来 PLA Wood→PLA Matte
    就在上方）——只向下扫会漏。
    """
    got = _picker_click_text(session, pane["rows"], needle, **kw)
    if got:
        return got
    cx = pane["rect"][0] + 60
    cy = (pane["rect"][1] + pane["rect"][3]) // 2
    for _i in range(24):
        winutil.real_wheel_screen(cx, cy, 3)      # 回顶（列表到顶即夹住）
        time.sleep(0.06)
    time.sleep(0.35)
    rows = _screen_ocr_rows(pane["rect"])
    got = _picker_click_text(session, rows, needle, **kw)
    if got:
        return got
    for i in range(steps):
        winutil.real_wheel_screen(cx, cy, notch)
        time.sleep(0.28)
        rows = _screen_ocr_rows(pane["rect"])
        got = _picker_click_text(session, rows, needle, **kw)
        if got:
            print(f"{LOG} picker: {needle!r} 命中（回顶后第 {i + 1} 档）")
            return got
    return ""


def _picker_row_y(pane, name):
    """(y, x) of a pane row for `name`; 缺失时按厂商顺序插值。

    2.4.1 的**当前展开分支**那一行会被 OCR 漏掉（实测：'Generic' 行在截图里明明
    在，OCR 的行表里没有）。已知厂商顺序来自产品文档（Snapmaker → Generic →
    其余字典序），所以可以用相邻行插值出它的 y。
    """
    low = name.lower().strip()
    for y, t, x in pane["rows"]:
        tl = t.strip().lower()
        if tl.startswith(low) and "@" not in tl and "nozzle" not in tl:
            return y, max(20, x)
    known = ["snapmaker", "generic", "aliz", "bambu", "fdplast", "fusrock", "nit",
             "overture", "polymaker", "sunlu", "valment", "esun"]
    if low in known:
        i = known.index(low)

        def y_of(nm):
            for y, t, _x in pane["rows"]:
                if t.strip().lower().startswith(nm):
                    return y
            return None

        prev_y = y_of(known[i - 1]) if i > 0 else None
        next_y = y_of(known[i + 1]) if i + 1 < len(known) else None
        if prev_y is not None and next_y is not None:
            return (prev_y + next_y) // 2, 64
        if next_y is not None:
            return next_y - 28, 64
        if prev_y is not None:
            return prev_y + 28, 64
    return None, None


def _picker_hover(session, x, y, pause=1.1):
    """把光标移到 (x,y) 并停住——2.4.1 的两级菜单 **hover 即切换右栏**
    （实测 10-12：弹层开在鼠标落点，光标压着 'Generic' 行 → 右栏显示 Generic
    的列表；移到 'Snapmaker' 行即切换）。点击前先 hover，可保证分支真的切过去，
    即使点击本身被吞（弹层开着时偶尔发生）。"""
    winutil.user32.SetCursorPos(int(x), int(y))
    time.sleep(pause)


def _picker_panes(session, min_w=120):
    """可见的选择框栏位：[{"rect","hwnd","rows","is_vendor"}]。

    2.4.1 的选择框是**双栏弹层**（实测 10-10）：同一次打开会同时出现两个窗口——
      左栏 (236,446,510,838) = 一级供应商/分组，右栏 (510,474,710,712) = 二级耗材。
    只取 wait_popup 的第一个窗口时永远只看到右栏（二级），因此找不到 Generic 分支。
    """
    import ctypes
    from ctypes import wintypes as wt
    wins = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != session.pid or not user32.IsWindowVisible(hwnd):
            return True
        if hwnd == session.hwnd:
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value != "wxWindowNR":
            return True
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        r = (rc.left, rc.top, rc.right, rc.bottom)
        if (r[2] - r[0]) >= min_w and (r[3] - r[1]) >= 80:
            wins.append((r, hwnd))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    panes = []
    for r, hwnd in wins:
        rows = _screen_ocr_rows(r)
        panes.append({"rect": r, "hwnd": hwnd, "rows": rows,
                      "is_vendor": _picker_is_vendor_level(rows)})
    return panes


def _filament_pane(session, panes=None):
    panes = panes if panes is not None else _picker_panes(session)
    return next((p for p in panes if not p["is_vendor"]), None)


def _split_target(target_substr):
    """旧口径名字 → (vendor, type)。拆不出 vendor 时返回 ('', 原名)。"""
    t = target_substr.strip()
    for vendor in ("Snapmaker", "Generic", "Polymaker", "Bambu", "SUNLU", "eSUN"):
        if t.lower().startswith(vendor.lower()):
            return vendor, t[len(vendor):].strip()
    return "", t


def _two_level_pick(session, slot, target_substr, force=False):
    """2.4.1 双栏导航：左栏选供应商 → 右栏选耗材。命中返回 combo 文本，否则 ''。"""
    vendor, typ = _split_target(target_substr)
    vendor_tries = [vendor] if vendor else ["Snapmaker", "Generic", "Custom", "自定义"]
    if not vendor:
        vendor_tries.append("User")
    for v in vendor_tries:
        if not v:
            continue
        pop, ch, how = _picker_open(session, slot)
        if not pop:
            print(f"{LOG} slot{slot}: picker did not open (target {target_substr!r})")
            return ""
        time.sleep(0.8)
        panes = _picker_panes(session)
        if not panes:
            print(f"{LOG} slot{slot}: no picker panes visible")
            return ""
        print(f"{LOG} slot{slot} panes: "
              f"{[(p['rect'], p['is_vendor'], len(p['rows'])) for p in panes]} "
              f"(vendor try {v!r})")
        vend = next((p for p in panes if p["is_vendor"]), None)
        if vend:
            print(f"{LOG}   vendor pane rows: {[t[:26] for _y, t, _x in vend['rows']][:14]}")
        for p in panes:
            if not p["is_vendor"]:
                print(f"{LOG}   filament pane rows: {[t[:26] for _y, t, _x in p['rows']][:10]}")
        if vend:
            # 当前槽位的耗材**已经属于**目标厂商时：右栏在打开时就是它的列表
            # （弹层开在回显行位置），直接搜右栏即可。此时硬去点厂商行有两重坑
            # （实测 10-12 m8d：Generic ABS → Generic PC）：
            #   ① 该厂商行正是"当前展开分支"，渲染高亮 → OCR 读不到它；
            #   ② 插值坐标可能落在"回显行"上，一点就把弹层点关。
            cur_now = combo_text(ch).lower() if ch else ""
            if v and cur_now.startswith(v.lower()):
                print(f"{LOG} slot{slot}: 当前 {cur_now!r} 已属于 {v!r} → 跳过厂商点击，直接搜右栏")
                hitrow = f"<current {v}>"
            else:
                hitrow = _picker_click_vendor(session, vend, v)
            if not hitrow:
                # 左栏顶部会被"当前耗材回显行"挤下去（实测：Snapmaker 行看不见），
                # 所以先**向上**滚，再看折叠下方（Custom/自定义）。
                for _i in range(10):
                    winutil.real_wheel_screen(vend["rect"][0] + 40,
                                              (vend["rect"][1] + vend["rect"][3]) // 2, 3)
                    time.sleep(0.15)
                time.sleep(0.5)
                panes = _picker_panes(session)
                vend = next((p for p in panes if p["is_vendor"]), None)
                hitrow = _picker_click_text(session, vend["rows"], v, startswith=True) if vend else ""
            if not hitrow and vend:
                for _i in range(12):     # 再向下滚，找 Custom/自定义 之类
                    winutil.real_wheel_screen(vend["rect"][0] + 40,
                                              (vend["rect"][1] + vend["rect"][3]) // 2, -3)
                    time.sleep(0.15)
                time.sleep(0.5)
                panes = _picker_panes(session)
                vend = next((p for p in panes if p["is_vendor"]), None)
                hitrow = _picker_click_text(session, vend["rows"], v, startswith=True) if vend else ""
            if not hitrow:
                # 当前槽位的耗材就属于该厂商时，左栏**可能没有这一行**（被"回显行"占位，
                # 实测 'Snapmaker' 行就是这种情况）→ 视为已选中，直接在右栏找。
                cur = combo_text(ch).lower()
                if cur.startswith(v.lower()):
                    print(f"{LOG} slot{slot}: vendor {v!r} 已是当前槽位（回显行占位）→ 直接搜右栏")
                    hitrow = f"<current {v}>"
                else:
                    print(f"{LOG} slot{slot}: vendor {v!r} not found in the left pane")
                    winutil.user32.keybd_event(0x1B, 0, 0, 0)
                    time.sleep(0.5)
                    continue
            time.sleep(1.0)
            panes = _picker_panes(session)
        filt = _filament_pane(session, panes)
        if not filt:
            print(f"{LOG} slot{slot}: no filament pane after vendor {v!r}")
            winutil.user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.5)
            continue
        print(f"{LOG} slot{slot} after vendor {v!r}: right pane rows "
              f"{[t[:26] for _y, t, _x in filt['rows']][:10]}")
        got = _picker_scan_for(session, filt, typ, steps=18, notch=-1, skip_echo=False)
        if not got:
            # 行文本被面板宽度截断（用户预设行）→ 用 hover tooltip 全名消歧
            got = _picker_tooltip_scan(session, filt, typ)
        now = combo_text(ch)
        print(f"{LOG} slot{slot} after two-level pick ({v!r},{got!r}) -> {now!r}")
        if target_substr in now or (typ and typ.lower() in now.lower()):
            return now
        winutil.user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.5)
    return ""


def switch_filament_preset(session, slot, target_substr, tries=30, force=False):
    """把槽位预设切到 `target_substr`；返回最终 combo 文本（失败＝当前文本）。

    2.4.1：先走两级导航（供应商 → 耗材），没命中再退回老的平铺行走（2.4.0 口径）。"""
    slots = wait_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit["combo"]:
        print(f"{LOG} slot {slot} combo not found")
        return ""
    if not force and target_substr in combo_text(hit["combo"][2]):
        return combo_text(hit["combo"][2])
    two = _two_level_pick(session, slot, target_substr, force=force)
    if two:
        return two
    print(f"{LOG} slot{slot}: two-level navigation missed — falling back to the flat walk")
    return _legacy_preset_walk(session, slot, hit, target_substr, tries, force)


def _legacy_preset_walk(session, slot, hit, target_substr, tries, force):
    """2.4.0 的平铺行走（保留原逻辑，只是从 switch_filament_preset 里拆出来）。"""
    _text, _rect, ch = hit["combo"]
    deadline = time.monotonic() + (90.0 if force else 240.0)
    cx = (_rect[0] + _rect[2]) // 2
    cy = (_rect[1] + _rect[3]) // 2
    for attempt in range(tries):
        if time.monotonic() > deadline:
            print(f"{LOG} slot{slot} preset-switch budget exhausted after {attempt} attempt(s)")
            break
        winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            time.sleep(0.5)
            continue
        if click_popup_row(session, popup[2], target_substr, popup_hwnd=popup[3],
                           scrolls=24, notch=4):
            time.sleep(0.9)
            now = combo_text(ch)
            print(f"{LOG} slot{slot} OCR row -> {now!r}")
            if target_substr in now:
                return now
            continue
        print(f"{LOG} slot{slot} target {target_substr!r} not found by OCR "
              f"(attempt {attempt + 1}/{tries})")
        time.sleep(0.6)
    return combo_text(ch)




def confirm_flow_dialog(session):
    """Answer the prompt raised by a High-Flow switch (the doc's
    '确认切片分配喷嘴' popup) before slicing.

    Measured 09-24: right after Flow -> High Flow the Slice click is rejected
    ('slice click rejected') until the prompt is answered. Prefer a button
    mentioning the high-flow nozzle, then OK/Confirm, then the first button.
    Returns the action taken (or '' when no prompt appeared)."""
    dlg = export_util.wait_toplevel(
        session.pid, lambda c, t, r: c == "#32770", timeout_s=3.0)
    if not dlg:
        return ""
    print(f"{LOG} flow prompt: {dlg[1]!r} rect={dlg[2]}")
    kids = export_util._children_texts(dlg[3])
    print(f"{LOG} flow prompt texts: {[t.strip() for t, _r, _c in kids if t.strip()][:10]}")
    for want in ("high", "高流量", "ok", "yes", "confirm", "确定"):
        # NOTE: this used to call a non-existent click_dialog_button(); the path
        # was never exercised (m8f/m8g only ever meet the high-flow prompt), so a
        # different dialog shape — measured 09-29: an app error box raised while
        # switching flow with an edited process parameter — crashed with
        # NameError. Match and click the button here, with a REAL click: a modal
        # dialog swallows message-level clicks (#123 lesson).
        hit = next(((t.strip(), r) for t, r, _h in kids
                    if want in t.strip().lower()), None)
        if hit:
            t, r = hit
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.2)
            winutil.real_click_screen(cx, cy)
            print(f"{LOG} flow prompt -> {t!r}")
            time.sleep(1.0)
            return t
    if kids:
        t, r, _c = [k for k in kids if k[0].strip()] or kids
        cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.2)
        winutil.real_click_screen(cx, cy)
        print(f"{LOG} flow prompt -> first child {t!r}")
        time.sleep(1.0)
        return f"first {t!r}"
    return ""


OFFICIAL_MARKER = "official filaments"


def official_color_popup(session, timeout_s=8.0):
    """The OFFICIAL colour library (#32770, empty title, children carrying
    'Official Filaments' + the current colour's name and SKU), or None.

    Measured 09-24/28 with diag_m8b_swatch_probe (8 controls in slot 2's row
    clicked one by one): the popup comes from the slot's NUMBERED COLOUR CHIP
    (child 'Button' with text '2', whose background is the filament colour) for
    a Snapmaker-named preset, while the 16x25 button to its right opens the
    Edit/Delete/Merge #32768 menu — the legacy chain that ends at the NATIVE
    Windows picker. The chip path was never taken by the old code because
    filament_slots() picked its 'picker' by size (leftmost 12-30px child)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, title, rect, hwnd in _visible_toplevels(session.pid):
            if cls != "#32770":
                continue
            texts = [t.strip().lower() for t, _r, _h
                     in export_util._children_texts(hwnd) if t.strip()]
            if any(OFFICIAL_MARKER in t for t in texts):
                return cls, title, rect, hwnd
        time.sleep(0.3)
    return None


def popup_colour_texts(popup):
    """(name, sku) of the official popup's current colour, or (None, None)."""
    names, skus = [], []
    for t, _r, _h in export_util._children_texts(popup[3]):
        t = t.strip()
        if not t:
            continue
        if t.lower().startswith("sku"):
            skus.append(t)
        elif OFFICIAL_MARKER not in t.lower() and t.lower() not in (
                "panel", "cancel", "ok", "+ other colors", "official filaments"):
            names.append(t)
    return (names[0] if names else None), (skus[0] if skus else None)


def slot_swatch_rgb(session, slot):
    """Mean BGR of the slot's colour chip (its background IS the filament
    colour) — the swatch surface the baseline rows talk about."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    slots = wait_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit.get("swatch"):
        return None
    x0, y0, x1, y1 = hit["swatch"]
    crop = _screen_crop(x0 + 4, y0 + 4, x1 - 4, y1 - 4)
    if crop is None or crop.size == 0:
        return None
    # cv2 BGR order; the chip is a flat colour, so the mean is stable
    return [int(v) for v in crop.reshape(-1, 3).mean(axis=0)]


def _screen_crop(x0, y0, x1, y1):
    """Crop the desktop grab; the chip rects come from GetWindowRect (screen
    coordinates), so they apply directly here (the earlier stills mixed client
    and screen coordinates and cropped the wrong region, measured 09-24)."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    sw, sh, buf = winutil.screen_grab()
    img = np.frombuffer(buf, np.uint8).reshape(sh, sw, 4)
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img[max(0, y0):y1, max(0, x0):x1]


def click_official_color_popup(session, slot, timeout_s=8.0, tries=3):
    """Click the slot's colour chip and return the official popup (or None).

    坐标空间：chip 的 rect 来自子窗口 GetWindowRect，**已经是屏幕坐标**——再经
    client_to_screen() 会二次偏移（最大化窗口 client 原点 ≈ (+8,+31)），点落到 chip
    下方、什么都不弹（实测 10-12：这就是 m8b '#48 dialog opens: FAIL' 的根因，2.4.0
    上窗口几何不同所以侥幸没炸）。

    重复点击：槽位行的点击偶尔被吞（PITFALLS 18.4 冷启动 / 残留 tooltip），实测
    chip 首点即开官方色卡（#32770 kids='Mint Lemonade'/'sku 34205'/'Official
    Filaments'），但一次不中不该判定 SUT 行为变化——多试几次再定性。
    """
    slots = wait_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit.get("swatch"):
        print(f"{LOG} slot {slot} colour chip not found")
        return None
    x0, y0, x1, y1 = hit["swatch"]
    sx, sy = (x0 + x1) // 2, (y0 + y1) // 2
    for i in range(max(1, tries)):
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        winutil.real_click_screen(sx, sy)
        popup = official_color_popup(session,
                                     timeout_s=timeout_s if i == 0 else 2.5)
        if popup:
            print(f"{LOG} slot{slot} chip click at ({sx},{sy}) -> official colour "
                  f"popup {popup[2]} (try {i + 1})")
            return popup
        print(f"{LOG} slot{slot} chip click at ({sx},{sy}) -> nothing (try {i + 1})")
        time.sleep(0.5)
    return None


def click_color_picker(session, slot, timeout_s=6.0, dialog_cls="#32770"):
    """Click the slot's colour control; return the OFFICIAL colour popup tuple
    or, when the slot holds a non-Snapmaker filament (which falls back to the
    legacy picker), the native 'Color' dialog.

    Preferred path (measured 09-28): the slot's NUMBERED COLOUR CHIP opens the
    official library directly for Snapmaker presets. Only when no official
    popup appears does the legacy chain run: picker (REAL click) -> native
    #32768 menu (Edit/Delete/Merge with) -> its first row 'Edit' -> 'Material
    settings' dialog -> its 'colourpicker' child (MESSAGE click: a real click
    there is swallowed, g7b) -> native 'Color' #32770."""
    popup = click_official_color_popup(session, slot, timeout_s=timeout_s)
    if popup:
        return popup
    # A non-official filament (非官方耗材, baseline #44's 纯色 case) falls back
    # to the LEGACY picker and the chip click already opened it — take that one
    # instead of running the menu chain again and stacking a second dialog
    # (measured 09-28: slot 1 'Generic PETG' -> 'Please choose the filament
    # color' with '&Basic colors:').
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        native_dlg = export_util.wait_toplevel(
            session.pid, lambda c, t, r: c == "#32770", timeout_s=0.5)
        if native_dlg:
            texts = [x.strip().lower() for x, _r, _h
                     in export_util._children_texts(native_dlg[3])]
            if any("basic colors" in x for x in texts):
                print(f"{LOG} slot{slot}: legacy picker opened by the chip "
                      f"(title={native_dlg[1]!r})")
                return native_dlg
            break
        time.sleep(0.3)
    slots = filament_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit["picker"]:
        print(f"{LOG} slot {slot} picker not found")
        return None
    rect = hit["picker"]
    px = (rect[0] + rect[2]) // 2
    py = (rect[1] + rect[3]) // 2
    # REAL click: the clr_picker is a wxBitmapButton whose wx handler
    # needs a real input event (message-level clicks never opened the
    # menu, measured 09-17 suite). 坐标已是屏幕坐标（子窗口 GetWindowRect），
    # **不要再 client_to_screen**（二次偏移会把点挪到控件外，实测 10-12）。
    sx, sy = px, py
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    winutil.real_click_screen(sx, sy)
    menu = export_util.wait_toplevel(
        session.pid, lambda c, t, r: c == "#32768", timeout_s=3.0)
    if menu:
        mr = menu[2]
        my = mr[1] + max((mr[3] - mr[1]) // 6, 8)   # first row of three
        mx = (mr[0] + mr[2]) // 2
        winutil.user32.SetCursorPos(mx, my)
        time.sleep(0.2)
        winutil.real_click_screen(mx, my)
        time.sleep(0.5)
    # 'Material settings' (contains the colourpicker child)
    dlg = export_util.wait_toplevel(
        session.pid, lambda c, t, r: c == "#32770", timeout_s=timeout_s)
    if dlg:
        cp = next((ch for t, r, ch
                   in export_util._children_texts(dlg[3])
                   if t.strip() == "colourpicker"), None)
        if cp:
            rc = wt.RECT()
            user32.GetWindowRect(cp, ctypes.byref(rc))
            winutil.msg_click_screen((rc.left + rc.right) // 2,
                                     (rc.top + rc.bottom) // 2, cp)
            time.sleep(1.5)
            # the official color dialog opens as a SECOND #32770 ('Color')
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                for cls, title, rect2, hwnd in _visible_toplevels(
                        session.pid):
                    if cls == "#32770" and "color" in title.lower():
                        time.sleep(1.0)
                        return cls, title, rect2, hwnd
                time.sleep(0.3)
    if dialog_cls:
        dlg = export_util.wait_toplevel(
            session.pid, lambda c, t, r: c == dialog_cls,
            timeout_s=timeout_s)
    else:
        dlg = export_util.wait_popup(session.pid, timeout_s=timeout_s)
    time.sleep(1.0)
    return dlg


def _visible_toplevels(pid):
    """[(cls, title, rect, hwnd)] of the pid's visible top-level windows."""
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                     ctypes.c_void_p)
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(96)
        user32.GetWindowTextW(hwnd, txt, 96)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((cls.value, txt.value,
                    (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def close_dialog_by_button(dlg, substr):
    """Click the dialog child button whose text contains substr."""
    kids = export_util._children_texts(dlg[3])
    for t, r, _h in kids:
        if substr.lower() in t.lower():
            winutil.msg_click_screen((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            time.sleep(1.2)
            return True
    return False


# --- nozzle band --------------------------------------------------------------

def nozzle_reads(session):
    """{diameter, flow, flow_rect} from the sidebar nozzle section.

    Values are located RELATIVE to the 'Diameter'/'Flow' labels instead of the
    original rig's absolute band (screen y 275-325): on this rig the section sits
    elsewhere, so the band returned the diameter by luck and never saw the flow
    value (measured 09-21: flow=None while the panel showed 'Standard').
    On 2.4.0 the nozzle section appears TWICE in the child tree: a collapsed
    template instance (y~248-280, 20px slivers at x5-25) and the live one
    (y~283-315). Anchor on the LIVE labels (label rows below y=250) and only
    accept value rects wide enough to be the live widgets (measured 09-22, g11).
    """
    rows = list(export_util._children_texts(session.hwnd))
    labels = [r for t, r, _c in rows if t.strip() in ("Diameter", "Flow")
              and r[0] < 425 and r[1] > 250]
    if labels:
        lo, hi = min(r[1] for r in labels) - 12, max(r[3] for r in labels) + 12
    else:
        lo, hi = 275, 325
    diameter = flow = None
    flow_rect = None
    for text, rect, ch in rows:
        if not (lo <= rect[1] <= hi and rect[0] < 425):
            continue
        if text.strip() == "Diameter" or text.strip() == "Flow":
            continue
        if rect[2] - rect[0] < 40:      # degenerate template instance
            continue
        if text.strip().endswith("mm"):
            diameter = text.strip().replace(" ", "")
        elif text.strip() in ("Standard", "High Flow"):
            flow = text.strip()
            flow_rect = rect
    return {"diameter": diameter, "flow": flow, "flow_rect": flow_rect}


def switch_flow_combo(session, target_substr, tries=4):
    """Row-probe the nozzle Flow combo ('Standard'/'High Flow')."""
    reads = nozzle_reads(session)
    rect = reads.get("flow_rect")
    if not rect:
        print(f"{LOG} flow combo not found")
        return ""
    # click near the combo's dropdown arrow (the value text child is a
    # Static overlay; a center click can land on it and be swallowed)
    cx = rect[2] - 12
    cy = (rect[1] + rect[3]) // 2
    for attempt in range(tries):
        winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            print(f"{LOG} flow attempt {attempt + 1}: popup did not open")
            time.sleep(0.6)
            continue
        pr = popup[2]
        # OCR the popup and click the ROW whose text contains the target —
        # the blind pitch walk missed whenever the popup failed to reopen on
        # the 2nd attempt, so the switch never happened (measured 09-24: the
        # options list DID contain 'High Flow' all along, g33).
        if click_popup_row(session, pr, target_substr, popup_hwnd=popup[3]):
            time.sleep(0.9)
            now = nozzle_reads(session).get("flow") or ""
            print(f"{LOG} flow OCR row -> {now!r}")
            if target_substr in now:
                time.sleep(0.8)
                return now
            continue
        px = (pr[0] + pr[2]) // 2
        py = pr[1] + 14 + attempt * 28
        winutil.msg_click_screen(px, py)
        time.sleep(0.9)
        now = nozzle_reads(session).get("flow") or ""
        print(f"{LOG} flow row {attempt}: {now!r}")
        if target_substr in now:
            time.sleep(1.0)
            return now
    return nozzle_reads(session).get("flow") or ""


def wait_arrival(session, timeout_s=300, min_frac=0.0025):
    """Wait for fixture-model arrival while CONTINUOUSLY sweeping blocker
    dialogs. The boot sweep (launcher, 25s budget) can miss load-phase
    dialogs: 'Customized Preset' re-pops per preset group and 'Loading...'
    lingers — any of them blocks arrival forever (measured 09-17 suite:
    m8d/m8c arrival FAIL with the dialog dismissed only once). Gate is
    0.25% (m7i small-cube gate): the mixed fixture reads only ~0.8%
    chromatic on the new build, jittering around the old 0.6% gate."""
    from m7_common import model_colored_frac
    from harness import launcher
    deadline = time.monotonic() + timeout_s
    frac = model_colored_frac(session)
    ok = frac >= min_frac
    while not ok and time.monotonic() < deadline:
        launcher.sweep_boot_blockers(session.pid, session.hwnd, budget_s=3.0)
        time.sleep(2.0)
        frac = model_colored_frac(session)
        ok = frac >= min_frac
    print(f"{LOG} arrival: {ok} ({frac:.2%}, gate {min_frac:.2%})")
    return ok, frac


# --- purifier gcode asserts ---------------------------------------------------

def purifier_params(gcode_bytes):
    """Parse the first SET_PURIFIER_MODE line into a dict (None if absent)."""
    m = PURIFIER_RE.search(gcode_bytes)
    if not m:
        return None
    line = m.group(0)
    out = {}
    for key in (b"MODE", b"DESIRE_TEMP", b"ALARM_TEMP", b"FAN_SPEED",
                b"DELAY_OFF"):
        km = re.search(key + rb"=([-\w.]+)", line)
        out[key.decode()] = km.group(1).decode() if km else None
    return out


def used_filaments(gcode_bytes):
    """[i+1 for slots with nonzero 'filament used [g]' weight]. The comment
    reads `; filament used [g] = 10.24, 0.00, ...` (measured 09-17)."""
    m = re.search(rb"; filament used \[g\] ?= ?([\d., ]+)", gcode_bytes)
    if not m:
        return []
    vals = [float(v) for v in re.split(rb"[, ]+", m.group(1).strip()) if v]
    return [i + 1 for i, v in enumerate(vals) if v > 0]
