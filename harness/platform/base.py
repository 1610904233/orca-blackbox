# base.py — platform-neutral driver contract (macOS port Phase 0).
#
# The black-box suite grew a Windows-only "eyes + hands" layer in
# harness/winutil.py: window discovery by PID, PrintWindow capture, and
# message-level SendMessage input. A macOS port cannot reuse any of those
# primitives (wxOSX has no HWNDs, PrintWindow, or WS_VISIBLE), but the
# CASES mostly care about a much smaller semantic vocabulary:
#
#   find the app window -> capture pixels -> click/text -> read state
#
# This module defines that vocabulary. Platform backends implement it; the
# shared oracle (template match, OCR, gcode/3mf checks) stays untouched.
#
# Design rules:
#   * Coordinates are PHYSICAL pixels. A backend must expose the same
#     coordinate space its capture returns (Windows: DPI-aware client px).
#   * Frames are BGRA, top-down, tightly packed — exactly what
#     winutil.capture_window() already returns, so cv2 code is shared.
#   * Rects are inclusive-exclusive (left, top, right, bottom), matching
#     GetWindowRect / AXFrame conventions.
#   * Nothing here imports ctypes, winreg, PyObjC, or an app module: this
#     file must import on every platform, including CI lint on Linux.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable


class PlatformError(RuntimeError):
    """Base class for driver/platform failures."""


class UnsupportedPlatform(PlatformError):
    """No backend exists for the requested platform name."""


class DriverNotAvailable(PlatformError):
    """A backend exists but cannot run here (missing runtime/permissions)."""


class DriverOperationError(PlatformError):
    """A primitive failed at the OS boundary (capture, input, enumeration)."""


@dataclass(frozen=True)
class Rect:
    """Screen-space rectangle in physical pixels (right/bottom exclusive)."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    @classmethod
    def from_ltrb(cls, ltrb: Sequence[int]) -> "Rect":
        left, top, right, bottom = ltrb
        return cls(int(left), int(top), int(right), int(bottom))


@dataclass(frozen=True)
class Frame:
    """A captured image: BGRA, top-down, `width * height * 4` bytes."""

    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        expected = self.width * self.height * 4
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"invalid frame size {self.width}x{self.height}")
        if len(self.pixels) != expected:
            raise ValueError(
                f"frame buffer is {len(self.pixels)} B, expected {expected} B "
                f"for {self.width}x{self.height} BGRA")


@dataclass(frozen=True)
class WindowRef:
    """Opaque native window handle (HWND on Windows, AXUIElement on macOS)."""

    native: Any

    def __post_init__(self) -> None:
        if self.native is None:
            raise ValueError("WindowRef.native must not be None")

    def __int__(self) -> int:
        # Windows compatibility: many legacy helpers still take an HWND int.
        return int(self.native)


@dataclass(frozen=True)
class ControlRef:
    """A native control discovered below a window (button/edit/combo...)."""

    window: WindowRef
    native: Any
    role: str = ""
    name: str = ""
    class_name: str = ""
    rect: Rect | None = None

    def __post_init__(self) -> None:
        if self.native is None:
            raise ValueError("ControlRef.native must not be None")


class AppHandle:
    """A launched app instance: pid + main window + lifecycle callbacks."""

    def __init__(self, pid: int, main_window: WindowRef, *,
                 close: Callable[[float], None] | None = None,
                 alive: Callable[[], bool] | None = None,
                 native: Any = None) -> None:
        self.pid = int(pid)
        self.main_window = main_window
        # `native` is the backend's own session object (Windows: AppSession).
        # It exists for incremental migration and diagnostics; new code should
        # stay on the platform-neutral attributes above.
        self.native = native
        self._close = close
        self._alive = alive

    def alive(self) -> bool:
        return bool(self._alive()) if self._alive else True

    def close(self, timeout_s: float = 10.0) -> None:
        if self._close is not None:
            self._close(timeout_s)


@runtime_checkable
class Driver(Protocol):
    """The minimal vocabulary a platform backend must provide.

    `message_input` tells call sites whether `click(real=False)` can work
    without foreground/focus (Windows: True via SendMessage; macOS: False,
    it must use Accessibility actions or CGEvent).
    """

    name: str
    message_input: bool

    # --- launch / discovery ------------------------------------------------
    def launch(self, exe: Path | str | None = None, *,
               datadir: Path | str | None = None,
               model: Path | str | None = None,
               wait_window_s: float = 150.0,
               dismiss_blockers: bool = True,
               dismiss_wizard: bool = False) -> AppHandle:
        """Start the app and wait for its main window."""

    def windows_for_pid(self, pid: int) -> list[WindowRef]:
        """Visible top-level windows owned by `pid`."""

    def find_main_window(self, pid: int, timeout_s: float = 60.0,
                         stable_s: float = 1.0) -> WindowRef:
        """Wait for the app's main window (title is empty in Orca)."""

    def window_title(self, window: WindowRef) -> str: ...
    def window_class(self, window: WindowRef) -> str: ...

    # --- geometry ----------------------------------------------------------
    def window_rect(self, window: WindowRef) -> Rect:
        """Outer window rect in screen pixels."""

    def client_rect(self, window: WindowRef) -> Rect:
        """Client area as (0, 0, width, height) — capture coordinates."""

    def client_to_screen(self, window: WindowRef, x: int, y: int) -> tuple[int, int]: ...
    def screen_to_client(self, window: WindowRef, x: int, y: int) -> tuple[int, int]: ...
    def screen_size(self) -> tuple[int, int]: ...
    def dpi_scale(self, window: WindowRef) -> float:
        """Physical px per logical px (Windows 96 DPI -> 1.0)."""

    # --- eyes --------------------------------------------------------------
    def capture(self, window: WindowRef) -> Frame:
        """Capture the window's client area without requiring foreground."""

    def capture_screen(self) -> Frame:
        """Capture the whole desktop (fallback/oracle for dialogs)."""

    # --- hands -------------------------------------------------------------
    def click(self, window: WindowRef, x: int, y: int, *,
              screen: bool = False, button: str = "left",
              real: bool = False) -> Any:
        """Click at client coords (`screen=False`) or screen coords.

        `real=False` requests message-level injection when the backend has
        it; macOS must ignore the distinction and use an OS-level event.
        Returns the backend's target reference (HWND on Windows).
        """

    def wheel(self, window: WindowRef, x: int, y: int, notches: int, *,
              screen: bool = False, real: bool = False) -> None: ...

    def send_text(self, window: WindowRef, text: str, *,
                  target: ControlRef | None = None) -> None:
        """Type text into `target` (or the window) without focus stealing."""

    def read_text(self, window: WindowRef, *,
                  target: ControlRef | None = None) -> str:
        """Read a control's value, or the window title when target is None."""

    def send_key(self, window: WindowRef, key: str, *,
                 target: ControlRef | None = None,
                 modifiers: Sequence[str] = ()) -> None:
        """Press a named key ("enter", "esc", "tab", "ctrl"...) or one char."""

    def set_foreground(self, window: WindowRef) -> bool: ...
    def close_window(self, window: WindowRef) -> None: ...

    # --- native controls ---------------------------------------------------
    def controls(self, window: WindowRef, *,
                 visible_only: bool = True) -> list[ControlRef]:
        """Native descendants (buttons/edits/combos) with text and rect."""

    def find_control(self, window: WindowRef, *, name: str | None = None,
                     class_name: str | None = None, role: str | None = None,
                     visible_only: bool = True) -> ControlRef | None:
        """First descendant matching name substring / class / generic role."""

    def click_control(self, control: ControlRef, *, button: str = "left",
                      real: bool = False) -> Any: ...

    def control_text(self, control: ControlRef) -> str: ...
    def set_control_text(self, control: ControlRef, text: str) -> None: ...


class NullDriver:
    """Explicit placeholder for phases that have no backend yet."""

    name = "null"
    message_input = False

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def __getattr__(self, item: str):
        raise DriverNotAvailable(self.reason)
