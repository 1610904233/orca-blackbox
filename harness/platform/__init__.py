"""Platform abstraction for the black-box harness.

``harness.platform`` itself is importable everywhere: it only pulls in
``base`` (stdlib) and ``factory`` (lazy).  A backend module is loaded on
demand by :func:`factory.get_driver`.
"""

from .base import (
    AppHandle,
    CaptureError,
    ControlNotFound,
    ControlRef,
    Driver,
    DriverError,
    DriverNotAvailable,
    Frame,
    LaunchError,
    Rect,
    WindowRef,
)
from .factory import available_platforms, current_platform, get_driver

__all__ = [
    "AppHandle",
    "CaptureError",
    "ControlNotFound",
    "ControlRef",
    "Driver",
    "DriverError",
    "DriverNotAvailable",
    "Frame",
    "LaunchError",
    "Rect",
    "WindowRef",
    "available_platforms",
    "current_platform",
    "get_driver",
]
