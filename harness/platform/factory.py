"""Lazy platform-backend selection.

Only the backend for the *current* platform is imported.  In particular,
``harness.platform.windows`` is never imported on macOS and
``harness.platform.macos`` (which imports PyObjC) is never imported on
Windows.
"""

from __future__ import annotations

import sys

from .base import Driver, DriverNotAvailable

__all__ = ["current_platform", "get_driver", "available_platforms"]


def current_platform() -> str:
    """Canonical platform name: ``macos`` / ``windows`` / others as-is."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return sys.platform


def available_platforms() -> tuple[str, ...]:
    return ("windows", "macos")


def get_driver(platform: str | None = None) -> Driver:
    """Return a driver for ``platform`` (default: the running platform)."""
    name = (platform or current_platform()).lower()
    if name in ("macos", "darwin", "mac"):
        from .macos import MacOSDriver  # local import: only on macOS
        return MacOSDriver()
    if name in ("windows", "win32", "win"):
        try:
            from .windows import WindowsDriver  # local import: only on Windows
        except ImportError as exc:  # pragma: no cover - depends on tree state
            raise DriverNotAvailable(
                "the Windows backend (harness/platform/windows.py) is not "
                "present in this checkout; Windows runs still use the "
                "existing harness.winutil path"
            ) from exc
        return WindowsDriver()
    raise DriverNotAvailable(
        f"no black-box driver backend for platform {name!r} "
        f"(supported: {', '.join(available_platforms())})"
    )
