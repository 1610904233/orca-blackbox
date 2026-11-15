# harness.platform — platform-neutral driver contract (macOS port).
#
# Application code should call:
#
#     from harness.platform import get_driver
#     driver = get_driver()          # WindowsDriver today; MacOSDriver later
#     app = driver.launch(exe, datadir=profile_dir)
#     frame = driver.capture(app.main_window)
#
# Backends are selected lazily so importing this package never loads a
# foreign OS API. See base.py for the contract and windows.py for the
# current implementation.
#
# NOTE: `platform` here is a subpackage of `harness`, not the stdlib module;
# absolute `import platform` elsewhere still resolves to the stdlib.

from .base import (  # noqa: F401
    AppHandle,
    ControlRef,
    Driver,
    DriverNotAvailable,
    DriverOperationError,
    Frame,
    PlatformError,
    Rect,
    UnsupportedPlatform,
    WindowRef,
)
from .factory import available_platforms, current_platform_name, get_driver  # noqa: F401

__all__ = [
    "AppHandle",
    "ControlRef",
    "Driver",
    "DriverNotAvailable",
    "DriverOperationError",
    "Frame",
    "PlatformError",
    "Rect",
    "UnsupportedPlatform",
    "WindowRef",
    "available_platforms",
    "current_platform_name",
    "get_driver",
]
