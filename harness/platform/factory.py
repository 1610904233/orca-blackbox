# factory.py — choose a platform backend without importing foreign OS APIs.
#
# `get_driver()` is the only entry point application code should use. The
# Windows implementation imports ctypes.WinDLL at module import time, so it
# must stay behind a lazy import: importing this package on macOS/Linux
# would otherwise fail before the backend could report "not supported".

from __future__ import annotations

import sys

from .base import Driver, UnsupportedPlatform

_DRIVER: Driver | None = None


def current_platform_name() -> str:
    """Normalize sys.platform to the names used by this package."""
    name = sys.platform.lower()
    if name.startswith("win") or name in {"cygwin", "msys"}:
        return "windows"
    if name == "darwin":
        return "macos"
    return name


def get_driver(platform_name: str | None = None, *,
               refresh: bool = False) -> Driver:
    """Return the singleton driver for `platform_name` (default: this OS)."""
    global _DRIVER
    name = (platform_name or current_platform_name()).lower()
    if name in {"win32", "windows"}:
        name = "windows"
    elif name in {"darwin", "macos", "mac"}:
        name = "macos"

    if _DRIVER is not None and _DRIVER.name == name and not refresh:
        return _DRIVER

    if name == "windows":
        from .windows import WindowsDriver
        driver: Driver = WindowsDriver()
    elif name == "macos":
        from .macos import MacOSDriver
        driver = MacOSDriver()
    else:
        raise UnsupportedPlatform(
            f"no driver for platform {name!r}; available: "
            + ", ".join(available_platforms()))
    _DRIVER = driver
    return driver


def available_platforms() -> tuple[str, ...]:
    """Platform names that have a backend module (macOS is a Phase 2 stub)."""
    return ("windows", "macos")
