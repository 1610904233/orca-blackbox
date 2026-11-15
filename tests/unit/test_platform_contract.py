# test_platform_contract.py — pure unit tests for harness.platform.
#
# These do NOT launch the app or touch HWNDs; the end-to-end contract is
# tests/engine/m0_platform_contract.py (run on the guest rig). This file is
# safe on the host:
#
#   python -m pytest tests/unit/test_platform_contract.py --confcutdir=tests/unit -q
#
# --confcutdir keeps tests/conftest.py (1920x1080 / 96 DPI / remote-control
# rig gates) out of the unit session — those gates are for GUI cases.

import sys

import pytest

from harness.platform import (
    AppHandle,
    Driver,
    DriverNotAvailable,
    DriverOperationError,
    Frame,
    Rect,
    UnsupportedPlatform,
    WindowRef,
    get_driver,
)
from harness.platform.base import ControlRef


def test_rect_geometry():
    r = Rect(10, 20, 40, 70)
    assert (r.width, r.height) == (30, 50)
    assert r.center == (25, 45)
    assert r.as_tuple() == (10, 20, 40, 70)
    assert Rect.from_ltrb((1, 2, 3, 4)) == Rect(1, 2, 3, 4)


def test_frame_rejects_wrong_buffer_size():
    with pytest.raises(ValueError):
        Frame(2, 2, b"\0" * 4)
    with pytest.raises(ValueError):
        Frame(0, 1, b"")


def test_frame_accepts_bgra_buffer():
    f = Frame(2, 1, b"\0" * 8)
    assert (f.width, f.height, len(f.pixels)) == (2, 1, 8)


def test_window_ref_and_control_ref_require_native():
    assert int(WindowRef(123)) == 123
    with pytest.raises(ValueError):
        WindowRef(None)
    with pytest.raises(ValueError):
        ControlRef(WindowRef(1), None)


def test_app_handle_lifecycle_callbacks():
    closed = []
    handle = AppHandle(42, WindowRef(7), close=lambda t: closed.append(t),
                       alive=lambda: True)
    assert handle.pid == 42
    assert handle.alive() is True
    handle.close(3.5)
    assert closed == [3.5]


def test_unknown_platform_is_explicit():
    with pytest.raises(UnsupportedPlatform):
        get_driver("definitely-not-an-os")


def test_macos_stub_fails_fast_off_darwin():
    if sys.platform == "darwin":
        pytest.skip("on darwin the Phase 2 backend is expected to be real")
    from harness.platform.macos import MacOSDriver
    with pytest.raises(DriverNotAvailable):
        MacOSDriver()


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="Windows backend is the only implemented one")
def test_windows_driver_satisfies_protocol():
    driver = get_driver("windows", refresh=True)
    assert isinstance(driver, Driver)
    assert driver.name == "windows"
    assert driver.message_input is True
    sw, sh = driver.screen_size()
    assert sw > 0 and sh > 0


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="Windows backend is the only implemented one")
def test_windows_driver_rejects_bad_arguments_before_touching_os():
    driver = get_driver("windows")
    with pytest.raises(ValueError):
        driver.click(WindowRef(1), 0, 0, button="middle")
    with pytest.raises(ValueError):
        driver.send_key(WindowRef(1), "not-a-key")
    with pytest.raises(DriverOperationError):
        driver.wheel(WindowRef(1), 0, 0, 1, real=False)


def test_case_platform_metadata_defaults_to_windows():
    import cases
    assert cases.DEFAULT_PLATFORMS == ("windows",)
    assert cases.case_platforms("m8x_153") == ("windows",)
    # Every enabled baseline case must name at least one platform; none has
    # been marked macOS yet (Phase 3 work).
    assert cases.enabled_cases(platform="macos") == []
    assert cases.enabled_cases(platform="windows") == cases.enabled_cases()
