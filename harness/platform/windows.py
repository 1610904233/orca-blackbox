# windows.py — the Windows backend of harness.platform.
#
# This backend is deliberately a thin adapter over the proven primitives:
# winutil (window discovery, PrintWindow capture, SendMessage input) and
# launcher (clean-env boot + blocker sweep). It adds NO new timing, retry,
# or coordinate policy, so the 74 baseline cases keep their exact behaviour
# while the rest of the suite can start migrating off raw HWND calls.
#
# What a macOS backend cannot reuse is exactly what this file is allowed to
# use: HWNDs, window messages, #32770 dialogs, PrintWindow, SendInput.

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from pathlib import Path
from typing import Any, Sequence

from .. import launcher, winutil
from .base import (
    AppHandle,
    ControlRef,
    DriverOperationError,
    Frame,
    Rect,
    WindowRef,
)

_WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

# Win32 window class -> a semantic role macOS can also express (AXRole).
_ROLE_BY_CLASS = {
    "Button": "button",
    "Edit": "text_field",
    "ComboBox": "combo_box",
    "Static": "label",
    "ListBox": "list",
    "SysListView32": "list",
    "SysTreeView32": "tree",
    "SysTabControl32": "tab_group",
    "msctls_trackbar32": "slider",
    "msctls_updown32": "stepper",
}

_VK = {
    "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B,
    "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}
_MODIFIER_VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B}


def _hwnd(window: WindowRef | int) -> int:
    return int(window.native) if isinstance(window, WindowRef) else int(window)


def _role_for_class(class_name: str) -> str:
    return _ROLE_BY_CLASS.get(class_name, (class_name or "unknown").lower())


def _control_text(hwnd: int) -> str:
    n = winutil.user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    winutil.user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _control_rect(hwnd: int) -> Rect:
    rc = wt.RECT()
    if not winutil.user32.GetWindowRect(hwnd, ctypes.byref(rc)):
        raise DriverOperationError(
            f"GetWindowRect failed for control 0x{hwnd:x}: "
            f"{ctypes.WinError(ctypes.get_last_error())}")
    return Rect(rc.left, rc.top, rc.right, rc.bottom)


class WindowsDriver:
    """Driver implementation for wxMSW builds of Snapmaker Orca."""

    name = "windows"
    message_input = True

    # --- launch / discovery ------------------------------------------------
    def launch(self, exe: Path | str | None = None, *,
               datadir: Path | str | None = None,
               model: Path | str | None = None,
               wait_window_s: float = 150.0,
               dismiss_blockers: bool = True,
               dismiss_wizard: bool = False) -> AppHandle:
        session = launcher.launch(
            exe=exe, datadir=datadir, model=model,
            wait_window_s=wait_window_s,
            dismiss_blockers=dismiss_blockers,
            dismiss_wizard=dismiss_wizard)
        return AppHandle(
            pid=session.pid,
            main_window=WindowRef(session.hwnd),
            close=session.close,
            alive=session.alive,
            native=session)

    def windows_for_pid(self, pid: int) -> list[WindowRef]:
        return [WindowRef(hwnd) for hwnd, owner in winutil.enum_windows()
                if owner == pid]

    def find_main_window(self, pid: int, timeout_s: float = 60.0,
                         stable_s: float = 1.0) -> WindowRef:
        return WindowRef(winutil.find_main_window(
            pid, timeout_s=timeout_s, stable_s=stable_s))

    def window_title(self, window: WindowRef) -> str:
        return winutil.window_title(_hwnd(window))

    def window_class(self, window: WindowRef) -> str:
        return winutil.window_class(_hwnd(window))

    # --- geometry ----------------------------------------------------------
    def window_rect(self, window: WindowRef) -> Rect:
        return Rect.from_ltrb(winutil.window_rect(_hwnd(window)))

    def client_rect(self, window: WindowRef) -> Rect:
        rc = wt.RECT()
        if not winutil.user32.GetClientRect(_hwnd(window), ctypes.byref(rc)):
            raise DriverOperationError(
                f"GetClientRect failed: {ctypes.WinError(ctypes.get_last_error())}")
        return Rect(0, 0, rc.right - rc.left, rc.bottom - rc.top)

    def client_to_screen(self, window: WindowRef, x: int, y: int) -> tuple[int, int]:
        return winutil.client_to_screen(_hwnd(window), int(x), int(y))

    def screen_to_client(self, window: WindowRef, x: int, y: int) -> tuple[int, int]:
        pt = wt.POINT(int(x), int(y))
        if not winutil.user32.ScreenToClient(_hwnd(window), ctypes.byref(pt)):
            raise DriverOperationError(
                f"ScreenToClient failed: {ctypes.WinError(ctypes.get_last_error())}")
        return (pt.x, pt.y)

    def screen_size(self) -> tuple[int, int]:
        return (winutil.user32.GetSystemMetrics(0),
                winutil.user32.GetSystemMetrics(1))

    def dpi_scale(self, window: WindowRef) -> float:
        return winutil.get_dpi_for_window(_hwnd(window)) / 96.0

    # --- eyes --------------------------------------------------------------
    def capture(self, window: WindowRef) -> Frame:
        try:
            w, h, buf = winutil.capture_window(_hwnd(window))
        except Exception as exc:  # noqa: BLE001 — normalize the boundary error
            raise DriverOperationError(str(exc)) from exc
        return Frame(w, h, buf)

    def capture_screen(self) -> Frame:
        try:
            w, h, buf = winutil.screen_grab()
        except Exception as exc:  # noqa: BLE001
            raise DriverOperationError(str(exc)) from exc
        return Frame(w, h, buf)

    # --- hands -------------------------------------------------------------
    def _screen_point(self, window: WindowRef, x: int, y: int,
                      screen: bool) -> tuple[int, int]:
        if screen:
            return (int(x), int(y))
        return winutil.client_to_screen(_hwnd(window), int(x), int(y))

    def click(self, window: WindowRef, x: int, y: int, *,
              screen: bool = False, button: str = "left",
              real: bool = False) -> Any:
        if button not in ("left", "right"):
            raise ValueError(f"unsupported mouse button: {button!r}")
        sx, sy = self._screen_point(window, x, y, screen)
        if real:
            if button == "left":
                return winutil.real_click_screen(sx, sy)
            return winutil.real_right_click_screen(sx, sy)
        if button != "left":
            # The suite has no message-level right-click primitive; native
            # popups (#32768) only see real input anyway.
            raise DriverOperationError(
                "Windows backend has no message-level right click; use real=True")
        return winutil.msg_click_screen(sx, sy, root_hwnd=_hwnd(window))

    def wheel(self, window: WindowRef, x: int, y: int, notches: int, *,
              screen: bool = False, real: bool = False) -> None:
        if not real:
            raise DriverOperationError(
                "Windows backend has no message-level wheel; use real=True")
        sx, sy = self._screen_point(window, x, y, screen)
        winutil.real_wheel_screen(sx, sy, notches)

    def send_text(self, window: WindowRef, text: str, *,
                  target: ControlRef | None = None) -> None:
        hwnd = target.native if target is not None else _hwnd(window)
        winutil.msg_text(int(hwnd), text)

    def read_text(self, window: WindowRef, *,
                  target: ControlRef | None = None) -> str:
        if target is None:
            return winutil.window_title(_hwnd(window))
        # WM_GETTEXT, not GetWindowTextW: a cross-process Edit's contents are
        # not in its cached caption (PITFALLS 2026-09-24).
        return winutil.edit_text(int(target.native))

    def send_key(self, window: WindowRef, key: str, *,
                 target: ControlRef | None = None,
                 modifiers: Sequence[str] = ()) -> None:
        hwnd = int(target.native) if target is not None else _hwnd(window)
        key_l = key.lower()
        if key_l in _VK:
            vk = _VK[key_l]
        elif len(key) == 1:
            vk = ord(key.upper())
        elif key_l.startswith("f") and key_l[1:].isdigit() \
                and 1 <= int(key_l[1:]) <= 12:
            vk = 0x70 + int(key_l[1:]) - 1
        else:
            raise ValueError(f"unknown key: {key!r}")
        mods = [m.lower() for m in modifiers]
        unknown = [m for m in mods if m not in _MODIFIER_VK]
        if unknown:
            raise ValueError(f"unknown modifier(s): {unknown}")
        if len(mods) > 1:
            # winutil.msg_key holds one modifier VK; callers that need chords
            # should add a primitive instead of approximating silently.
            raise DriverOperationError("winutil.msg_key supports one modifier")
        winutil.msg_key(hwnd, vk, _MODIFIER_VK[mods[0]] if mods else 0)

    def set_foreground(self, window: WindowRef) -> bool:
        return winutil.force_set_foreground(_hwnd(window))

    def close_window(self, window: WindowRef) -> None:
        winutil.close_window(_hwnd(window))

    # --- native controls ---------------------------------------------------
    def controls(self, window: WindowRef, *,
                 visible_only: bool = True) -> list[ControlRef]:
        root = _hwnd(window)
        out: list[ControlRef] = []

        @_WNDENUMPROC
        def callback(child, _lparam):
            if visible_only and not winutil.user32.IsWindowVisible(child):
                return True
            cls = winutil.window_class(child)
            out.append(ControlRef(
                window=window,
                native=child,
                role=_role_for_class(cls),
                name=_control_text(child),
                class_name=cls,
                rect=_control_rect(child)))
            return True

        winutil.user32.EnumChildWindows(ctypes.c_void_p(root), callback, 0)
        return out

    def find_control(self, window: WindowRef, *, name: str | None = None,
                     class_name: str | None = None, role: str | None = None,
                     visible_only: bool = True) -> ControlRef | None:
        name_l = name.lower() if name else None
        role_l = role.lower() if role else None
        for control in self.controls(window, visible_only=visible_only):
            if name_l is not None and name_l not in control.name.lower():
                continue
            if class_name is not None and control.class_name != class_name:
                continue
            if role_l is not None and control.role != role_l:
                continue
            return control
        return None

    def click_control(self, control: ControlRef, *, button: str = "left",
                      real: bool = False) -> Any:
        rect = control.rect or _control_rect(int(control.native))
        x, y = rect.center
        return self.click(control.window, x, y, screen=True,
                          button=button, real=real)

    def control_text(self, control: ControlRef) -> str:
        text = winutil.edit_text(int(control.native))
        return text if text else _control_text(int(control.native))

    def set_control_text(self, control: ControlRef, text: str) -> None:
        hwnd = int(control.native)
        winutil.select_all(hwnd)
        winutil.msg_text(hwnd, text)
