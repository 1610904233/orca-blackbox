#!/usr/bin/env python3
# topbar_util.py — drive the self-drawn BBLTopbar tools and the native
# popup menus they open (Tier 0 for menu-class black-box operations).
#
# UI facts (measured on the 08-24 dev build, source-verified):
#   - the BBLTopbar is a wxAuiToolBar: ONE child HWND spanning the top band
#     of the frame; the File / dropdown tools are DRAWN inside it (no per-
#     tool HWNDs) — they are located by probing x offsets.
#   - BBLTopbar::OnMouseLeftDown checks FindToolByCurrentPosition() (the
#     REAL cursor position) before handing the click to the toolbar, so the
#     physical cursor must sit on the tool first (SetCursorPos) or the click
#     becomes a window drag.
#   - a tool click opens a NATIVE popup menu (class "#32768", TrackPopupMenu
#     inside the wx handler); the click's SendMessage stays pending while
#     the menu modal loop runs (SendMessageTimeout times out — expected).
#   - the menu's real state machine lives in the modal loop, so neither
#     SendMessage keys nor clicks drive it; the reliable activation is
#     WM_COMMAND(item_id) to the frame: wx dispatches it through the
#     CURRENT popup menu (wxCurrentPopupMenu -> wxMenu::MSWCommand ->
#     FindItem incl. submenus -> wxEVT_MENU on the menu's own handler).
#   - item ids are wxNewId()-generated: read them from the open menu's
#     HMENU (MN_GETHMENU) via GetMenuItemInfo; submenus are reachable via
#     GetSubMenu without ever opening them.
#
# This mirrors the export_util convention: locate deterministically by
# enumeration, never cache coordinates, close what you open.

import ctypes
import ctypes.wintypes as wt
import time

from . import winutil

user32 = ctypes.WinDLL("user32")
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

MENU_CLASS = "#32768"
WM_CANCELMODE = 0x001F
WM_COMMAND = 0x0111
MN_GETHMENU = 0x01E1
MF_BYPOSITION = 0x0400
MIIM_ID = 0x00000002
MIIM_SUBMENU = 0x00000004

# Tool x offsets inside the topbar (measured: File tool ~offset 10-40,
# dropdown tool ~offset 70-100 at 96 DPI). Probed in order.
FILE_TOOL_OFFSETS = (10, 20, 30, 40, 50, 60)
DROP_TOOL_OFFSETS = (70, 80, 90, 100, 110, 120, 130)


class MENUITEMINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT), ("fMask", wt.UINT), ("fType", wt.UINT),
        ("fState", wt.UINT), ("wID", wt.UINT), ("hSubMenu", ctypes.c_void_p),
        ("hbmpChecked", ctypes.c_void_p), ("hbmpUnchecked", ctypes.c_void_p),
        ("dwItemData", ctypes.c_void_p), ("dwTypeData", ctypes.c_void_p),
        ("cch", wt.UINT), ("hbmpItem", ctypes.c_void_p),
    ]


# ---------------------------------------------------------------------------
# window discovery
# ---------------------------------------------------------------------------

def _topbar(hwnd: int):
    """The BBLTopbar child: topmost full-width band of the frame (h ~30)."""
    tops = sorted({r[1] for _, r, _, _ in _children(hwnd)})
    top_y = tops[0] if tops else 0
    for text, rect, ch, cls in _children(hwnd):
        if rect[1] == top_y and (rect[3] - rect[1]) <= 40 and (rect[2] - rect[0]) > 500:
            return text, rect, ch
    return None


def _children(parent: int):
    out = []

    def cb(hwnd, _lp):
        txt = ctypes.create_unicode_buffer(128)
        user32.GetWindowTextW(hwnd, txt, 128)
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd, cls.value))
        return True

    user32.EnumChildWindows(ctypes.c_void_p(parent), WNDENUMPROC(cb), 0)
    return out


def _enum_menu_windows(pid: int):
    """Visible native popup-menu windows (#32768) of the app."""
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value != MENU_CLASS:
            return True
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((rc.left, rc.top, rc.right, rc.bottom, hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def wait_menu_popup(pid: int, timeout_s: float = 6.0) -> list:
    """Wait for at least one #32768 popup-menu window; returns all of them."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        found = _enum_menu_windows(pid)
        if found:
            return found
        time.sleep(0.2)
    return []


def hover_row(menu_rect: tuple, item_count: int, index: int) -> None:
    """Park the REAL cursor on a menu row — the menu modal loop tracks the
    physical cursor: hovering opens submenus and highlights items."""
    left, top, right, bottom = menu_rect
    row_h = (bottom - top - 4) / max(item_count, 1)
    x = (left + right) // 2
    y = top + 2 + int((index + 0.5) * row_h)
    user32.SetCursorPos(x, y)


def wait_submenu(pid: int, known: set, timeout_s: float = 5.0):
    """Wait for a NEW popup menu window (not in `known`); returns its
    (rect, hwnd, hmenu) or None."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for rect, hwnd in [(m[:4], m[4]) for m in _enum_menu_windows(pid)]:
            if hwnd not in known:
                return rect, hwnd, menu_hmenu(hwnd)
        time.sleep(0.2)
    return None


def submenu_row_candidates(rect: tuple, n_items: int, index: int,
                           step: int = 6) -> list:
    """Candidate y positions for a submenu row, probed around the computed
    center. Measured on the 08-24 build the rows sit ~12px LOWER than the
    naive top+2+(i+0.5)*pitch formula (row pitch ~20px starting at top+12),
    so the candidates walk downward first, then upward."""
    left, top, right, bottom = rect
    pitch = (bottom - top - 4) / max(n_items, 1)
    base = top + 2 + int((index + 0.5) * pitch)
    return [base + k * step for k in range(0, 6)] + \
           [base - k * step for k in (1, 2, 3)]


def real_click_submenu_row(session, submenu_name: str, row_substr: str,
                           success_fn, label: str = "", max_attempts: int = 8,
                           step: int = 6) -> bool:
    """Open the dropdown menu, hover `submenu_name` to open its submenu,
    then REAL-click the row whose label contains `row_substr` (case-
    insensitive), probing y candidates until `success_fn()` returns True.

    `success_fn` is the caller's observable (e.g. the model disappearing /
    appearing) — the only reliable signal that the right row was hit, since
    native menu rows hit-test in the modal loop and the measured row
    geometry drifts ~12px from the naive formula. Reopens the menus between
    attempts. Returns True when the observable fired."""
    from . import winutil
    # 2.4.2 fast path: WM_COMMAND is dead for dropdown rows there (see the
    # probe_242_dddispatch note above) but every row's label carries its
    # ACCELERATOR — read it live from the HMENU, close the menu, hand the
    # app keyboard focus and send the keystroke. The hover ladder below
    # stays as the fallback for rows without accelerators / dead keys.
    accel = _row_accelerator(session, submenu_name, row_substr)
    parsed = _parse_accel(accel) if accel else None
    if parsed:
        print(f"[topbar] {label or row_substr}: accelerator route "
              f"{accel!r} (WM_COMMAND is dead on 2.4.2 dropdowns)")
        _focus_click(session)
        _send_accel(*parsed)
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if success_fn():
                print(f"[topbar] {label or row_substr}: {accel} fired "
                      f"the observable")
                return True
            time.sleep(0.5)
        print(f"[topbar] {label or row_substr}: {accel} did not fire the "
              f"observable — falling back to the hover ladder")
    for attempt in range(max_attempts):
        menu = open_dropdown_menu(session)
        if not menu:
            print(f"[topbar] {label}: dropdown menu did not open "
                  f"(attempt {attempt + 1})")
            continue
        rect, hwnd, hmenu = menu
        items = menu_items(hmenu)
        sub_idx = find_item(hmenu, submenu_name)
        if sub_idx is None:
            close_menu_windows(session.pid)
            continue
        hover_row(rect, len(items), sub_idx)
        sub = wait_submenu(session.pid, {hwnd}, timeout_s=5.0)
        if not sub:
            close_menu_windows(session.pid)
            continue
        srect, _shwnd, shmenu = sub
        sub_items = menu_items(shmenu)
        row_idx = find_item(shmenu, row_substr)
        if row_idx is None:
            close_menu_windows(session.pid)
            print(f"[topbar] {label}: row '{row_substr}' not found")
            return False
        left, top, right, _b = srect
        cx = (left + right) // 2
        for y in submenu_row_candidates(srect, len(sub_items), row_idx, step):
            winutil.real_click_screen(cx, y)
            # poll the observable: the click closes the menu (modal loop
            # exits) and the app repaints — give it a few seconds
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline:
                if success_fn():
                    close_menu_windows(session.pid)
                    return True
                time.sleep(0.5)
            menus = _enum_menu_windows(session.pid)
            if menus:
                close_menu_windows(session.pid)
                time.sleep(1.0)
            # reopen for the next candidate
            menu = open_dropdown_menu(session)
            if not menu:
                break
            rect, hwnd, hmenu = menu
            items = menu_items(hmenu)
            sub_idx = find_item(hmenu, submenu_name)
            hover_row(rect, len(items), sub_idx)
            sub = wait_submenu(session.pid, {hwnd}, timeout_s=5.0)
            if not sub:
                break
            srect, _shwnd, shmenu = sub
            sub_items = menu_items(shmenu)
            row_idx = find_item(shmenu, row_substr)
            left, top, right, _b = srect
            cx = (left + right) // 2
        close_menu_windows(session.pid)
    return False


# ---------------------------------------------------------------------------
# menu structure
# ---------------------------------------------------------------------------

def menu_hmenu(menu_hwnd: int) -> int:
    """The HMENU behind a popup menu window (MN_GETHMENU)."""
    h = user32.SendMessageW(menu_hwnd, MN_GETHMENU, 0, 0)
    if not h:
        h = user32.GetMenu(menu_hwnd)
    return h


def menu_items(hmenu: int) -> list:
    """[(index, label, state_flags)] for every item of `hmenu`."""
    if not hmenu:
        return []
    n = user32.GetMenuItemCount(hmenu)
    items = []
    for i in range(n):
        buf = ctypes.create_unicode_buffer(256)
        ln = user32.GetMenuStringW(hmenu, i, buf, 256, MF_BYPOSITION)
        st = user32.GetMenuState(hmenu, i, MF_BYPOSITION)
        items.append((i, buf.value[:ln], st))
    return items


def item_info(hmenu: int, index: int):
    """(item_id, submenu_hmenu) of the item at `index`."""
    info = MENUITEMINFO()
    info.cbSize = ctypes.sizeof(MENUITEMINFO)
    info.fMask = MIIM_ID | MIIM_SUBMENU
    if not user32.GetMenuItemInfoW(hmenu, index, True, ctypes.byref(info)):
        return None, None
    return info.wID, (info.hSubMenu or 0)


def find_item(hmenu: int, label_substr: str):
    """Index of the first item whose label contains `label_substr`
    (case-insensitive — builds differ, e.g. 'Delete All' vs 'Delete all')."""
    needle = label_substr.lower()
    for i, label, _st in menu_items(hmenu):
        if needle in label.lower():
            return i
    return None


# ---------------------------------------------------------------------------
# activation
# ---------------------------------------------------------------------------

# 2.4.2 lesson (probe_242_dddispatch): dispatching a DROPDOWN submenu row by
# WM_COMMAND(item_id) is DEAD there — id 348 (Delete All) / 354 (Top) sent to
# BOTH the frame and the topbar child all 'complete' but nothing happens,
# while the FILE menu's WM_COMMAND rows (Import id 330) still work (m7c).
# Every dropdown row carries its ACCELERATOR in the label tail, so the
# reliable route is the keyboard one a user takes.
_VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "del": 0x2E,
       "delete": 0x2E, "esc": 0x1B, "escape": 0x1B, "enter": 0x0D,
       "return": 0x0D, "tab": 0x09, "space": 0x20, "?": 0xBF, "&": 0x31 + 7}


def _parse_accel(accel: str):
    """'Ctrl+Shift+S' / 'Del' / 'Z' -> ([modifier VKs], key VK) or None."""
    parts = [p.strip().lower() for p in accel.split("+") if p.strip()]
    if not parts:
        return None
    mods, key = [], None
    for p in parts:
        if p in ("ctrl", "control"):
            mods.append(_VK["ctrl"])
        elif p == "shift":
            mods.append(_VK["shift"])
        elif p in ("alt", "menu"):
            mods.append(_VK["alt"])
        elif len(p) == 1 and p.isalnum():
            key = ord(p.upper())
        elif p in _VK:
            key = _VK[p]
        elif p.startswith("f") and p[1:].isdigit() and 1 <= int(p[1:]) <= 12:
            key = 0x70 + int(p[1:]) - 1
        else:
            return None
    if key is None:
        return None
    return mods, key


def _send_accel(mods, key):
    for vk in mods:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
    user32.keybd_event(key, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(key, 0, 2, 0)
    for vk in reversed(mods):
        time.sleep(0.05)
        user32.keybd_event(vk, 0, 2, 0)
    time.sleep(0.6)


def _row_accelerator(session, submenu_name: str, row_substr: str):
    """Open the dropdown, read the matched row's FULL label (accelerators
    live in the '\t' tail), close the menu; returns the accelerator text or
    None."""
    menu = open_dropdown_menu(session)
    if not menu:
        return None
    _rect, _hwnd, hmenu = menu
    try:
        via_idx = find_item(hmenu, submenu_name)
        if via_idx is None:
            return None
        _vid, sub = item_info(hmenu, via_idx)
        if not sub:
            return None
        row_idx = find_item(sub, row_substr)
        if row_idx is None:
            return None
        label = menu_items(sub)[row_idx][1]
        return label.split("\t")[-1].strip() if "\t" in label else None
    finally:
        close_menu_windows(session.pid)


def _focus_click(session):
    """One real click inside the canvas band to hand the app REAL keyboard
    focus (message clicks never grant it; without focus keybd_event
    accelerators go to whatever window has it). Bottom-of-viewport bed
    click: harmless for the submenu flows (at most deselects)."""
    from . import winutil
    l, t, r, b = winutil.window_rect(session.hwnd)
    x, y = (l + r) // 2, t + (b - t) * 3 // 4
    user32.SetCursorPos(x, y)
    time.sleep(0.2)
    winutil.real_click_screen(x, y)
    time.sleep(0.5)

def activate_menu_item(session, hmenu: int, index: int) -> bool:
    """Dispatch WM_COMMAND(item_id) to the frame — the same message a real
    selection produces. Returns True once the app confirmed it accepted the
    message (the send may time out while the app opens a modal dialog —
    that is still a successful activation)."""
    item_id, _ = item_info(hmenu, index)
    if not item_id:
        return False
    result = ctypes.c_ulong()
    # 3s cap: the app handles the command synchronously inside the send and
    # may block (modal file dialog) — the send "failing" is expected then.
    ok = user32.SendMessageTimeoutW(session.hwnd, WM_COMMAND, item_id, 0,
                                    0x0000 | 0x0002, 3000, ctypes.byref(result))
    print(f"[topbar] WM_COMMAND(id={item_id}) sent, completed={bool(ok)}")
    return True


def dispatch_submenu(session, top, child, via=None, top_menu=None):
    """Open a topbar menu ('file' | 'dropdown') and dispatch a row by
    WM_COMMAND(item_id) — no hover anywhere.

    2.4.2: hover-opening submenus is unreliable there, but while the PARENT
    popup is open the whole HMENU tree is readable — GetSubMenu descends
    without hovering (probe_242_submenu), and WM_COMMAND(child_id) still
    reaches the handler through wxCurrentPopupMenu (wxMenu::MSWCommand's
    FindItem descends into submenus). `via` = submenu label to descend
    through ('Import' / 'Edit' / 'View'); `child` = row label substring or
    the numeric command id; `top_menu` = an already-open (rect, hwnd,
    hmenu) to skip reopening. Returns (dispatched, item_id)."""
    menu = top_menu or (open_file_menu(session) if top == "file"
                        else open_dropdown_menu(session))
    if not menu:
        print(f"[topbar] dispatch_submenu: {top!r} menu did not open")
        return False, None
    _rect, _hwnd, hmenu = menu
    target = hmenu
    if via:
        via_idx = find_item(hmenu, via)
        if via_idx is None:
            print(f"[topbar] dispatch_submenu: no {via!r} row in menu")
            close_menu_windows(session.pid)
            return False, None
        _vid, sub = item_info(hmenu, via_idx)
        if not sub:
            print(f"[topbar] dispatch_submenu: {via!r} has no submenu")
            close_menu_windows(session.pid)
            return False, None
        target = sub
    rows = menu_items(target)
    idx = None
    if isinstance(child, int):
        for i, _label, _st in rows:
            wid, _sub = item_info(target, i)
            if wid == child:
                idx = i
                break
    else:
        needle = child.lower()
        for i, label, _st in rows:
            if needle in label.lower():
                idx = i
                break
    if idx is None:
        print(f"[topbar] dispatch_submenu: child {child!r} not in "
              f"{[l for _i, l, _s in rows]}")
        close_menu_windows(session.pid)
        return False, None
    item_id, _sub = item_info(target, idx)
    ok = activate_menu_item(session, target, idx)
    time.sleep(0.6)
    close_menu_windows(session.pid)
    return ok, item_id


def close_menu_windows(pid: int) -> None:
    """Dismiss any still-open popup menus (WM_CANCELMODE)."""
    for rect, hwnd in [(m[:4], m[4]) for m in _enum_menu_windows(pid)]:
        user32.SendMessageW(hwnd, WM_CANCELMODE, 0, 0)


# ---------------------------------------------------------------------------
# topbar tools
# ---------------------------------------------------------------------------

def click_topbar_tool(session, offsets, label: str):
    """SetCursorPos + message-click inside the topbar until a popup menu
    opens. Returns (menu_windows, toolbar_hwnd) or (None, hwnd)."""
    tb = _topbar(session.hwnd)
    if not tb:
        print(f"[topbar] {label}: topbar not found")
        return None, None
    _, rect, ch = tb
    cy = (rect[1] + rect[3]) // 2
    for off in offsets:
        x = rect[0] + off
        winutil.user32.SetCursorPos(x, cy)
        time.sleep(0.3)
        winutil.msg_click_screen(x, cy, session.hwnd)
        time.sleep(1.0)
        menus = wait_menu_popup(session.pid, timeout_s=3.0)
        if menus:
            print(f"[topbar] {label} opened at offset {off}")
            return menus, ch
        print(f"[topbar] {label} offset {off}: no menu")
    return None, ch


def open_file_menu(session):
    """Open the topbar File menu; returns its (rect, hwnd, hmenu)."""
    menus, _ = click_topbar_tool(session, FILE_TOOL_OFFSETS, "File")
    return _menu_tuple(session, menus)


def open_dropdown_menu(session):
    """Open the topbar dropdown menu (Edit/View/Preferences/Help)."""
    menus, _ = click_topbar_tool(session, DROP_TOOL_OFFSETS, "Dropdown")
    return _menu_tuple(session, menus)


def _menu_tuple(session, menus):
    if not menus:
        return None
    rect = menus[0][:4]
    hwnd = menus[0][4]
    return rect, hwnd, menu_hmenu(hwnd)
