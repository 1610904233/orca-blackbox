"""Platform-neutral driver contract for the black-box GUI harness.

This module is intentionally dependency-free (stdlib only).  It defines the
data types and the ``Driver`` protocol that every platform backend implements:

* Windows  -> ``harness.platform.windows``  (existing Win32 semantics)
* macOS    -> ``harness.platform.macos``    (AX + ScreenCaptureKit)

Importing this module must never import ``ctypes``, ``winreg``, PyObjC or any
other platform-specific binding: ``harness.platform`` is imported by tooling
that runs on every host.

Coordinate / pixel conventions
------------------------------
* ``Rect`` / ``WindowRef.rect`` are in **physical screen pixels**, top-left
  origin.  On macOS these are AX/CG points multiplied by ``backingScaleFactor``.
* ``Frame`` is **BGRA, top-down, physical pixels** — the same layout the
  Windows ``winutil.capture_window`` returns.
* ``Driver.click`` / ``wheel`` take physical screen pixels.
"""

from __future__ import annotations

import binascii
import os
import signal
import struct
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence, runtime_checkable

__all__ = [
    "Rect",
    "Frame",
    "WindowRef",
    "ControlRef",
    "AppHandle",
    "Driver",
    "DriverNotAvailable",
    "DriverError",
    "LaunchError",
    "CaptureError",
    "ControlNotFound",
]


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

class DriverError(RuntimeError):
    """Base class for driver-level failures."""


class DriverNotAvailable(DriverError):
    """The platform backend cannot run (missing TCC grant, unsupported OS)."""


class LaunchError(DriverError):
    """The app could not be launched (missing exe, second instance, ...)."""


class CaptureError(DriverError):
    """A screenshot could not be produced."""


class ControlNotFound(LookupError):
    """No accessibility control matched the requested predicate."""


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle.  ``x``/``y`` is the top-left corner."""

    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def to_xywh(self) -> tuple[int, int, int, int]:
        return (int(round(self.x)), int(round(self.y)),
                int(round(self.w)), int(round(self.h)))

    def to_xyxy(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.right, self.bottom)

    @classmethod
    def from_xyxy(cls, x0: float, y0: float, x1: float, y1: float) -> "Rect":
        return cls(x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0))

    @classmethod
    def from_cg_bounds(cls, bounds: Any, scale: float = 1.0) -> "Rect":
        """Build a Rect from a CGWindowList bounds dict (points).

        PyObjC hands back an ``NSDictionary`` here, so ``isinstance(dict)``
        is not enough — prefer the mapping interface.
        """
        if hasattr(bounds, "get"):
            try:
                x = bounds.get("X", 0)
                y = bounds.get("Y", 0)
                w = bounds.get("Width", 0)
                h = bounds.get("Height", 0)
            except Exception:
                x = y = w = h = 0
        elif isinstance(bounds, dict):
            x = bounds.get("X", bounds.get(b"X", 0))
            y = bounds.get("Y", bounds.get(b"Y", 0))
            w = bounds.get("Width", bounds.get(b"Width", 0))
            h = bounds.get("Height", bounds.get(b"Height", 0))
        else:  # CGRect-like object
            x, y = bounds.origin.x, bounds.origin.y
            w, h = bounds.size.width, bounds.size.height
        return cls(float(x) * scale, float(y) * scale,
                   float(w) * scale, float(h) * scale)

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.right and self.y <= py < self.bottom

    def intersects(self, other: "Rect") -> bool:
        return not (other.x >= self.right or other.right <= self.x
                    or other.y >= self.bottom or other.bottom <= self.y)

    def intersect(self, other: "Rect") -> "Rect":
        x0 = max(self.x, other.x)
        y0 = max(self.y, other.y)
        x1 = min(self.right, other.right)
        y1 = min(self.bottom, other.bottom)
        return Rect.from_xyxy(x0, y0, x1, y1)

    def scaled(self, factor: float) -> "Rect":
        return Rect(self.x * factor, self.y * factor,
                    self.w * factor, self.h * factor)

    def __bool__(self) -> bool:
        return self.w > 0 and self.h > 0


# ---------------------------------------------------------------------------
# frame (BGRA, top-down, physical pixels)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Frame:
    """A captured image: BGRA bytes, row-major, top-down, physical pixels."""

    width: int
    height: int
    data: bytes

    def __post_init__(self) -> None:
        expected = self.width * self.height * 4
        if self.width < 0 or self.height < 0:
            raise ValueError("negative frame dimensions")
        if len(self.data) < expected:
            raise ValueError(
                f"frame buffer too small: {len(self.data)} < {expected} "
                f"({self.width}x{self.height} BGRA)")

    @property
    def stride(self) -> int:
        return self.width * 4

    @property
    def rect(self) -> Rect:
        return Rect(0, 0, self.width, self.height)

    def pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        i = (y * self.width + x) * 4
        return (self.data[i + 2], self.data[i + 1], self.data[i], self.data[i + 3])

    def crop(self, rect: Rect) -> "Frame":
        x0 = max(0, min(self.width, int(round(rect.x))))
        y0 = max(0, min(self.height, int(round(rect.y))))
        x1 = max(x0, min(self.width, int(round(rect.right))))
        y1 = max(y0, min(self.height, int(round(rect.bottom))))
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0:
            return Frame(0, 0, b"")
        rows = []
        stride = self.stride
        for y in range(y0, y1):
            start = y * stride + x0 * 4
            rows.append(self.data[start:start + w * 4])
        return Frame(w, h, b"".join(rows))

    def stats(self, sample_step: int = 4) -> dict:
        """Cheap luma / non-black / chromatic statistics.

        Sampling keeps this fast enough for a 1920x1080 BGRA frame in pure
        Python (step=4 -> ~130k samples).
        """
        step = max(1, int(sample_step))
        w, h, data = self.width, self.height, self.data
        n = luma_sum = nonblack = colored = 0
        min_luma = 255.0
        max_luma = 0.0
        for y in range(0, h, step):
            row = y * w * 4
            for x in range(0, w, step):
                i = row + x * 4
                b, g, r = data[i], data[i + 1], data[i + 2]
                lo, hi = min(b, g, r), max(b, g, r)
                lum = (b + g + r) / 3.0
                luma_sum += lum
                n += 1
                if lum > 8:
                    nonblack += 1
                if hi - lo > 24:
                    colored += 1
                if lum < min_luma:
                    min_luma = lum
                if lum > max_luma:
                    max_luma = lum
        if not n:
            return {"samples": 0, "mean_luma": 0.0, "min_luma": 0.0,
                    "max_luma": 0.0, "nonblack_fraction": 0.0,
                    "colored_fraction": 0.0, "blank": True}
        return {
            "samples": n,
            "mean_luma": luma_sum / n,
            "min_luma": min_luma,
            "max_luma": max_luma,
            "nonblack_fraction": nonblack / n,
            "colored_fraction": colored / n,
            "blank": (nonblack / n) < 0.01,
        }

    def difference(self, other: "Frame", threshold: int = 8,
                   sample_step: int = 4) -> float:
        """Fraction of sampled pixels whose channels differ beyond threshold."""
        if (self.width, self.height) != (other.width, other.height):
            return 1.0
        step = max(1, int(sample_step))
        w, h = self.width, self.height
        a, b = self.data, other.data
        n = changed = 0
        for y in range(0, h, step):
            row = y * w * 4
            for x in range(0, w, step):
                i = row + x * 4
                if (abs(a[i] - b[i]) > threshold
                        or abs(a[i + 1] - b[i + 1]) > threshold
                        or abs(a[i + 2] - b[i + 2]) > threshold):
                    changed += 1
                n += 1
        return changed / n if n else 0.0

    # -- persistence -------------------------------------------------------

    def save_bmp(self, path: str | os.PathLike) -> Path:
        """Write a 32-bit top-down BMP (BGRA matches the BMP byte order)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        row = self.stride
        file_size = 54 + row * self.height
        header = (b"BM" + file_size.to_bytes(4, "little") + b"\0\0\0\0"
                  + (54).to_bytes(4, "little")
                  + (40).to_bytes(4, "little") + self.width.to_bytes(4, "little")
                  + (-self.height).to_bytes(4, "little")  # negative = top-down
                  + (1).to_bytes(2, "little") + (32).to_bytes(2, "little")
                  + (0).to_bytes(4, "little")
                  + (row * self.height).to_bytes(4, "little")
                  + (2835).to_bytes(4, "little") * 2 + b"\0" * 8)
        p.write_bytes(header + self.data[:row * self.height])
        return p

    def save_png(self, path: str | os.PathLike) -> Path:
        """Write a PNG (pure stdlib; BGRA -> RGBA)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        w, h, data = self.width, self.height, self.data
        raw = bytearray()
        stride = self.stride
        for y in range(h):
            raw.append(0)  # filter: none
            start = y * stride
            for x in range(w):
                i = start + x * 4
                raw.extend((data[i + 2], data[i + 1], data[i], data[i + 3]))

        def chunk(tag: bytes, payload: bytes) -> bytes:
            return (struct.pack(">I", len(payload)) + tag + payload
                    + struct.pack(">I", binascii.crc32(tag + payload) & 0xFFFFFFFF))

        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
               + chunk(b"IEND", b""))
        p.write_bytes(png)
        return p

    def save(self, path: str | os.PathLike) -> Path:
        suffix = Path(path).suffix.lower()
        if suffix == ".png":
            return self.save_png(path)
        return self.save_bmp(path)


# ---------------------------------------------------------------------------
# handles
# ---------------------------------------------------------------------------

@dataclass
class WindowRef:
    """A top-level window.

    ``handle`` is backend-specific (an AXUIElement on macOS, an HWND on
    Windows).  ``id`` is a stable numeric id when the backend has one
    (CGWindowID / HWND).
    """

    handle: Any = None
    id: int = 0
    pid: int = 0
    title: str = ""
    rect: Rect = field(default_factory=Rect)
    layer: int = 0
    on_screen: bool = True
    scale: float = 1.0
    raw: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.id or self.handle)


@dataclass
class ControlRef:
    """A native accessibility control."""

    handle: Any = None
    role: str = ""
    subrole: str = ""
    title: str = ""
    description: str = ""
    value: Any = None
    identifier: str = ""
    enabled: bool = True
    selected: bool | None = None
    actions: tuple[str, ...] = ()
    rect: Rect | None = None
    window: WindowRef | None = None
    raw: dict = field(default_factory=dict)

    def text(self) -> str:
        for candidate in (self.value, self.title, self.description):
            if isinstance(candidate, str) and candidate:
                return candidate
        if self.value is not None:
            return str(self.value)
        return ""

    def __bool__(self) -> bool:
        return self.handle is not None


@dataclass
class AppHandle:
    """A launched app instance.

    ``popen`` is optional: backends that launch through an OS API can still
    populate ``pid`` and implement ``terminate`` via signals.
    """

    pid: int
    path: Path | None = None
    bundle_id: str = ""
    popen: Any = None
    datadir: Path | None = None
    log_path: Path | None = None
    extra: dict = field(default_factory=dict)

    def poll(self) -> int | None:
        if self.popen is not None:
            return self.popen.poll()
        return None

    def alive(self) -> bool:
        if self.popen is not None:
            return self.popen.poll() is None
        try:
            os.kill(self.pid, 0)
            return True
        except OSError:
            return False

    def terminate(self, timeout_s: float = 10.0) -> None:
        """Graceful terminate (SIGTERM), then SIGKILL after the timeout."""
        if self.popen is not None:
            if self.popen.poll() is not None:
                return
            self.popen.terminate()
            try:
                self.popen.wait(timeout=timeout_s)
                return
            except Exception:
                self.popen.kill()
                try:
                    self.popen.wait(timeout=5.0)
                except Exception:
                    pass
            return
        if not self.alive():
            return
        try:
            os.kill(self.pid, signal.SIGTERM)
        except OSError:
            return
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not self.alive():
                return
            time.sleep(0.2)
        try:
            os.kill(self.pid, signal.SIGKILL)
        except OSError:
            pass

    def kill(self) -> None:
        if self.popen is not None:
            self.popen.kill()
        else:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# driver protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Driver(Protocol):
    """The "eyes and hands" contract every platform backend implements."""

    #: True when the backend can inject *message-level* input (Win32
    #: SendMessage).  macOS has no such channel -> False.
    message_input: bool

    # -- lifecycle ---------------------------------------------------------

    def launch(
        self,
        exe: Path | str | None = None,
        datadir: Path | str | None = None,
        model: Path | str | None = None,
        *,
        timeout_s: float = 150.0,
        dismiss_wizard: bool = True,
        env: dict[str, str] | None = None,
        log_path: Path | str | None = None,
    ) -> AppHandle:
        ...

    # -- windows -----------------------------------------------------------

    def windows_for_pid(self, pid: int) -> list[WindowRef]:
        ...

    def find_main_window(self, pid: int, *, timeout_s: float = 60.0,
                         stable_s: float = 1.0) -> WindowRef:
        ...

    def window_rect(self, win: WindowRef) -> Rect:
        ...

    def client_rect(self, win: WindowRef) -> Rect:
        ...

    def client_to_screen(self, win: WindowRef, x: float, y: float) -> tuple[float, float]:
        ...

    def screen_to_client(self, win: WindowRef, x: float, y: float) -> tuple[float, float]:
        ...

    def screen_size(self) -> tuple[int, int]:
        ...

    def dpi_scale(self, win: WindowRef | None = None) -> float:
        ...

    # -- capture -----------------------------------------------------------

    def capture(self, win: WindowRef) -> Frame:
        ...

    def capture_screen(self) -> Frame:
        ...

    # -- input -------------------------------------------------------------

    def click(self, x: float, y: float, *, button: str = "left",
              clicks: int = 1) -> None:
        ...

    def wheel(self, x: float, y: float, notches: int) -> None:
        ...

    def send_text(self, text: str) -> None:
        ...

    def read_text(self, ctl: ControlRef) -> str:
        ...

    def send_key(self, key: str, *, modifiers: Sequence[str] = ()) -> None:
        ...

    def set_foreground(self, win: WindowRef) -> bool:
        ...

    def close_window(self, win: WindowRef) -> None:
        ...

    # -- controls ----------------------------------------------------------

    def controls(self, win: WindowRef, *, max_depth: int = 8) -> list[ControlRef]:
        ...

    def find_control(self, win: WindowRef, *, role: str | None = None,
                     title: str | None = None, identifier: str | None = None,
                     contains: bool = True, timeout_s: float = 0.0
                     ) -> ControlRef | None:
        ...

    def click_control(self, ctl: ControlRef) -> bool:
        ...

    def control_text(self, ctl: ControlRef) -> str:
        ...

    def set_control_text(self, ctl: ControlRef, text: str) -> bool:
        ...
