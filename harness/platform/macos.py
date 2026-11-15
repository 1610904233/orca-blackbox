# macos.py — Phase 2 backend placeholder (not implemented yet).
#
# Availability (checked 2026-11-15): Snapmaker publishes a universal macOS
# dmg for v2.4.1 (Snapmaker_Orca_Mac_universal_V2.4.1.dmg), but the accepted
# 2.4.2 build is Windows-only in the local QA drop. A macOS runner (real Mac
# or VM, TCC Accessibility + Screen Recording granted) is also absent, so
# nothing in this module can be validated yet. It exists to pin the mapping
# and to fail loudly instead of silently falling back to Win32 assumptions.
#
# Planned primitive mapping (Phase 2, PyObjC):
#   launch              NSWorkspace.openApplication / subprocess open -a
#   windows_for_pid     AXUIElementCreateApplication(pid) -> kAXWindowsAttribute
#   window_title/class  kAXTitleAttribute / kAXRole + kAXSubrole
#   window_rect         AXPosition + AXSize (screen points -> physical px)
#   capture             ScreenCaptureKit (macOS 14+) or CGWindowListCreateImage
#                       (deprecated); convert to BGRA top-down
#   click               AXPress / AXSetValue on the element, else CGEvent
#   send_text           AXValue (set) / CGEvent keyboard events (fallback)
#   send_key            CGEventCreateKeyboardEvent
#   controls            AXChildren recursion -> ControlRef(role, title, frame)
#   close_window        AXClose / kAXCancelAction, else Cmd+W
#
# Hard differences the cases must branch on:
#   * no SendMessage/WM_* injection -> Driver.message_input is False;
#     real=True and real=False both mean OS-level events.
#   * no #32770 dialogs -> dialog discovery must use AXRole
#     (AXSheet/AXDialog) and titles, never Win32 class names.
#   * no PrintWindow -> ScreenCaptureKit requires Screen Recording TCC;
#     a denied permission must surface as DriverNotAvailable, not black frames.
#   * menu bar is global (AXMenuBar), not a per-window child HWND; topbar_util
#     must be replaced by AX menu traversal.
#   * wxOSX coordinate origin is bottom-left for some AX values; normalize to
#     top-left physical pixels at this boundary.

from __future__ import annotations

import sys

from .base import DriverNotAvailable


class MacOSDriver:
    """Fail-fast placeholder until a macOS build + runner are available."""

    name = "macos"
    message_input = False

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise DriverNotAvailable(
                "macOS driver can only be instantiated on darwin "
                f"(current sys.platform={sys.platform!r})")
        raise DriverNotAvailable(
            "macOS backend is Phase 2: needs a macOS Orca build and a runner "
            "with Accessibility + Screen Recording TCC grants")
