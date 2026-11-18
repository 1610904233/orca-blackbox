"""macOS backend: AX for controls, ScreenCaptureKit for pixels, CGEvent for input.

Design notes
------------
* **Eyes** — ScreenCaptureKit (macOS 14+).  ``CGDisplayCreateImage`` is
  unavailable since macOS 15 and even ``CGWindowListCreateImage`` is
  deprecated, so a one-shot ``SCStream`` is used for both window and display
  captures.  Frames are converted to BGRA, top-down physical pixels (the same
  contract as the Windows backend).
* **Coordinates** — AX and CGWindow geometry are in *points*, captures are in
  *pixels*.  ``backingScaleFactor`` normalises every public coordinate to
  physical pixels, top-left origin.
* **Hands** — no Win32 ``SendMessage`` equivalent exists on macOS, so
  ``message_input = False`` and actions use ``AXPress`` / ``AXSetValue`` when
  possible, falling back to real CGEvents.  This match's display is 1x, so
  the point/pixel conversion is an identity, but the code keeps the factor.
  Measured 2026-11-16: with AweSun/UURemote attached, synthetic CGEvents
  (keyboard or mouse, global or ``CGEventPostToPid``) are swallowed; AX
  actions remain reliable.  ``click`` / ``wheel`` / ``send_text`` are
  therefore best-effort HID paths that need a foreground app and no
  input-suppressing remote-control layer.
* **TCC** — Accessibility or Screen Recording denial raises
  ``DriverNotAvailable``; a black frame must never be mistaken for a product
  defect.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import objc
import os
import plistlib
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Sequence

import AppKit
import ApplicationServices as AS
import CoreFoundation
import Quartz
import ScreenCaptureKit as SCK
from CoreMedia import CMSampleBufferGetImageBuffer
from Foundation import NSObject

from .base import (
    AppHandle,
    CaptureError,
    ControlRef,
    DriverError,
    DriverNotAvailable,
    Frame,
    LaunchError,
    Rect,
    WindowRef,
)

__all__ = ["MacOSDriver", "DEFAULT_APP", "DEFAULT_EXE"]

DEFAULT_APP = Path("/Applications/Snapmaker Orca.app")
DEFAULT_EXE = DEFAULT_APP / "Contents" / "MacOS" / "Snapmaker_Orca"

# Boot blockers copied from harness/launcher.py (docs/PITFALLS.md §19).
# Forced-upgrade dialogs ("Snapmaker Orca needs an update") must NEVER be in
# this list: any button exits the app.
_BLOCKER_TITLES = (
    "wizard",
    "configuration update",
    "new version of snapmaker orca",
    "snapmaker orca update",
    "customized preset",
    "modified g-code",
    "snapmaker orca information",
)
_BLOCKER_BUTTONS = ("close", "cancel", "skip", "finish", "got it", "ok")

_PIXEL_FORMAT_BGRA = 0x42475241  # 'BGRA'
_AXVALUE_CGPOINT = 1
_AXVALUE_CGSIZE = 2


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


_AXLIB = ctypes.CDLL(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
_AXValueGetValue = _AXLIB.AXValueGetValue
_AXValueGetValue.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
_AXValueGetValue.restype = ctypes.c_bool


def _wait_event(event: threading.Event, timeout_s: float) -> bool:
    """Wait for a PyObjC completion, pumping the main run loop."""
    deadline = time.monotonic() + timeout_s
    while not event.is_set() and time.monotonic() < deadline:
        CoreFoundation.CFRunLoopRunInMode(
            CoreFoundation.kCFRunLoopDefaultMode, 0.05, False)
    return event.is_set()


def _ax_copy(element, attribute):
    if element is None:
        return None
    err, value = AS.AXUIElementCopyAttributeValue(element, attribute, None)
    return value if err == 0 else None


def _ax_str(element, attribute) -> str:
    value = _ax_copy(element, attribute)
    return value if isinstance(value, str) else ""


def _ax_bool(element, attribute, default: bool | None = None):
    value = _ax_copy(element, attribute)
    if value is None:
        return default
    return bool(value)


def _ax_actions(element) -> tuple[str, ...]:
    if element is None:
        return ()
    try:
        err, names = AS.AXUIElementCopyActionNames(element, None)
    except Exception:
        return ()
    if err != 0 or not names:
        return ()
    return tuple(str(n) for n in names)


def _ax_perform(element, action: str) -> bool:
    if element is None:
        return False
    try:
        return AS.AXUIElementPerformAction(element, action) == 0
    except Exception:
        return False


def _ax_set(element, attribute, value) -> bool:
    if element is None:
        return False
    try:
        return AS.AXUIElementSetAttributeValue(element, attribute, value) == 0
    except Exception:
        return False


def _ax_point_size(element):
    """AX position/size in points, or (None, None)."""
    pos = _ax_copy(element, AS.kAXPositionAttribute)
    size = _ax_copy(element, AS.kAXSizeAttribute)
    if pos is None or size is None:
        return None, None
    try:
        p = _CGPoint()
        s = _CGSize()
        ok_p = _AXValueGetValue(objc.pyobjc_id(pos), _AXVALUE_CGPOINT,
                                ctypes.byref(p))
        ok_s = _AXValueGetValue(objc.pyobjc_id(size), _AXVALUE_CGSIZE,
                                ctypes.byref(s))
        if not (ok_p and ok_s):
            return None, None
        return (p.x, p.y), (s.width, s.height)
    except Exception:
        return None, None


def _ax_id(element) -> int:
    try:
        return int(objc.pyobjc_id(element))
    except Exception:
        return id(element)


def _cg_bounds_tuple(bounds) -> tuple[float, float, float, float]:
    """(x, y, w, h) from an NSDictionary/CGRect bounds object."""
    if hasattr(bounds, "get"):
        try:
            return (float(bounds.get("X", 0)), float(bounds.get("Y", 0)),
                    float(bounds.get("Width", 0)), float(bounds.get("Height", 0)))
        except Exception:
            return (0.0, 0.0, 0.0, 0.0)
    try:
        return (float(bounds.origin.x), float(bounds.origin.y),
                float(bounds.size.width), float(bounds.size.height))
    except Exception:
        return (0.0, 0.0, 0.0, 0.0)


class _FrameGrabber(NSObject):
    """SCStreamOutput delegate that keeps the first screen frame."""

    def init(self):
        self = objc.super(_FrameGrabber, self).init()
        if self is None:
            return None
        self.event = threading.Event()
        self.stopped = threading.Event()
        self.image = None
        self.error = None
        return self

    def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buffer, output_type):
        if self.image is not None:
            return
        try:
            pixel_buffer = CMSampleBufferGetImageBuffer(sample_buffer)
            if pixel_buffer is None:
                raise RuntimeError("sample buffer has no image buffer")
            ci_image = Quartz.CIImage.imageWithCVPixelBuffer_(pixel_buffer)
            context = Quartz.CIContext.context()
            self.image = context.createCGImage_fromRect_(
                ci_image, ci_image.extent())
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            self.error = repr(exc)
        finally:
            self.event.set()

    def stream_didStopWithError_(self, stream, error):
        if error is not None and self.error is None:
            self.error = str(error)
        self.stopped.set()


class MacOSDriver:
    """AX + ScreenCaptureKit implementation of :class:`Driver`."""

    #: macOS has no message-level input channel.
    message_input = False

    def __init__(self, *, check_permissions: bool = True):
        self._ax_apps: dict[int, object] = {}
        self._shareable = None
        self._shareable_ts = 0.0
        self._event_source_obj = None
        if check_permissions:
            self._require_ax()
            self._require_screen()

    def _event_source(self):
        """Explicit CGEventSource for synthetic input.

        Events created with a NULL source were observed to be dropped while
        AweSun/UURemote was attached; an explicit private/HID source is
        delivered (verified on a System Settings button, 2026-11-16).
        """
        if self._event_source_obj is None:
            self._event_source_obj = (
                Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
                or Quartz.CGEventSourceCreate(
                    Quartz.kCGEventSourceStateHIDSystemState))
        return self._event_source_obj

    # ------------------------------------------------------------------
    # TCC / platform helpers
    # ------------------------------------------------------------------

    def _require_ax(self) -> None:
        if not bool(AS.AXIsProcessTrusted()):
            raise DriverNotAvailable(
                "Accessibility permission is required (System Settings > "
                "Privacy & Security > Accessibility > ZCode)")

    def _require_screen(self) -> None:
        try:
            ok = bool(Quartz.CGPreflightScreenCaptureAccess())
        except AttributeError:  # pragma: no cover - very old macOS
            return
        if not ok:
            raise DriverNotAvailable(
                "Screen Recording permission is required (System Settings > "
                "Privacy & Security > Screen & System Audio Recording > ZCode)")

    @staticmethod
    def _scale_for_point(px: float, py: float) -> float:
        """backingScaleFactor of the screen containing a top-left point."""
        try:
            main = AppKit.NSScreen.mainScreen()
            main_h = main.frame().size.height if main else 0.0
            for screen in AppKit.NSScreen.screens():
                frame = screen.frame()
                top = main_h - (frame.origin.y + frame.size.height)
                if (frame.origin.x <= px <= frame.origin.x + frame.size.width
                        and top <= py <= top + frame.size.height):
                    return float(screen.backingScaleFactor())
            if main is not None:
                return float(main.backingScaleFactor())
        except Exception:
            pass
        return 1.0

    def _scale_for_rect(self, rect: Rect) -> float:
        cx, cy = rect.center
        return self._scale_for_point(cx, cy)

    def screen_size(self) -> tuple[int, int]:
        w = int(Quartz.CGDisplayPixelsWide(Quartz.CGMainDisplayID()))
        h = int(Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID()))
        if w <= 0 or h <= 0:
            screen = AppKit.NSScreen.mainScreen()
            frame = screen.frame()
            scale = float(screen.backingScaleFactor())
            w, h = int(frame.size.width * scale), int(frame.size.height * scale)
        return w, h

    def dpi_scale(self, win: WindowRef | None = None) -> float:
        if win is not None:
            if win.scale > 0:
                return win.scale
            return self._scale_for_rect(win.rect)
        return float(AppKit.NSScreen.mainScreen().backingScaleFactor())

    # ------------------------------------------------------------------
    # launch
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_exe(exe: Path | str | None) -> Path:
        candidate = exe or os.environ.get("ORCA_VISION_APP_EXE") or DEFAULT_EXE
        path = Path(candidate).expanduser()
        if path.is_dir():
            if path.suffix == ".app":
                info = path / "Contents" / "Info.plist"
                name = "Snapmaker_Orca"
                if info.exists():
                    try:
                        with info.open("rb") as fh:
                            name = plistlib.load(fh).get(
                                "CFBundleExecutable", name)
                    except Exception:
                        pass
                path = path / "Contents" / "MacOS" / name
            else:
                macos_dir = path / "Contents" / "MacOS"
                if macos_dir.is_dir():
                    entries = [p for p in macos_dir.iterdir() if p.is_file()]
                    if entries:
                        path = entries[0]
        if not path.exists():
            raise FileNotFoundError(
                f"app executable not found: {path} (pass exe=/path/to.app)")
        return path

    @staticmethod
    def _bundle_id(exe: Path) -> str:
        for parent in exe.parents:
            if parent.suffix == ".app":
                info = parent / "Contents" / "Info.plist"
                if info.exists():
                    try:
                        with info.open("rb") as fh:
                            return plistlib.load(fh).get(
                                "CFBundleIdentifier", "")
                    except Exception:
                        return ""
        return ""

    @staticmethod
    def _seed_minimal_datadir(datadir: Path) -> None:
        """Mirror harness/profile.py's minimal sandbox on macOS.

        The app stages its own presets, but seeding the conf up front skips
        the splash/wizard gates and keeps the window at its default size.
        """
        datadir.mkdir(parents=True, exist_ok=True)
        conf_path = datadir / "Snapmaker_Orca.conf"
        if not conf_path.exists():
            minimal = {
                "app": {
                    "language": "en_US",
                    "show_splash_screen": False,
                    "single_instance": False,
                    "default_page": "1",
                    "privacy_policy_isagree": True,
                    "backup_switch": False,
                    # Pin the geometry the macOS pilots are calibrated for;
                    # without this key the app's own default is used and can
                    # drift across builds.  ORCA_BB_WINDOW_FRAME overrides it
                    # for cases that need a wider toolbar (e.g. Assembly View).
                    "window_mainframe": os.environ.get(
                        "ORCA_BB_WINDOW_FRAME", "360; 80; 1200; 800; 0"),
                },
                "firstguide": {"finish": True},
            }
            body = json.dumps(minimal, indent=4, ensure_ascii=False)
            digest = hashlib.md5((body + "\n").encode("utf-8")).hexdigest().upper()
            conf_path.write_text(
                body + "\n# MD5 checksum " + digest + "\n", encoding="utf-8")
            print(f"[macos] seeded conf: {conf_path}")

        repo = Path(__file__).resolve().parents[2]
        resources = repo / "resources"
        # system presets: repo resources first, then the app bundle's copy
        system_dst = datadir / "system"
        if not system_dst.exists():
            vendor_src = resources / "Snapmaker"
            vendor_json = resources / "Snapmaker.json"
            if not vendor_src.exists():
                for p in Path("/Applications").glob("*.app"):
                    cand = p / "Contents" / "Resources" / "profiles" / "Snapmaker"
                    if cand.exists():
                        vendor_src = cand
                        vendor_json = cand.parent / "Snapmaker.json"
                        break
            if vendor_src.exists():
                try:
                    system_dst.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(vendor_src, system_dst / "Snapmaker")
                    if vendor_json.exists():
                        shutil.copy2(vendor_json, system_dst / "Snapmaker.json")
                    print(f"[macos] seeded system presets: {system_dst}")
                except Exception as exc:  # noqa: BLE001
                    print(f"[macos] WARN seeding system presets: {exc}")

        printers_dst = datadir / "printers"
        if not printers_dst.exists():
            printers_src = resources / "printers"
            if not printers_src.exists():
                for p in Path("/Applications").glob("*.app"):
                    cand = p / "Contents" / "Resources" / "printers"
                    if cand.exists():
                        printers_src = cand
                        break
            if printers_src.exists():
                try:
                    shutil.copytree(printers_src, printers_dst)
                    print(f"[macos] seeded printers: {printers_dst}")
                except Exception as exc:  # noqa: BLE001
                    print(f"[macos] WARN seeding printers: {exc}")

        user_dst = datadir / "user"
        if not user_dst.exists():
            user_src = resources / "user"
            if user_src.exists():
                try:
                    shutil.copytree(user_src, user_dst)
                    print(f"[macos] seeded user presets: {user_dst}")
                except Exception as exc:  # noqa: BLE001
                    print(f"[macos] WARN seeding user presets: {exc}")

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
        if datadir is None:
            raise ValueError("datadir is required (isolation!)")
        exe_path = self._resolve_exe(exe)
        datadir_path = Path(datadir).expanduser().resolve()
        self._seed_minimal_datadir(datadir_path)

        bundle_id = self._bundle_id(exe_path)
        if bundle_id:
            existing = [
                app for app in AppKit.NSRunningApplication
                .runningApplicationsWithBundleIdentifier_(bundle_id)
                if not app.isTerminated()
            ]
            if existing:
                pids = ", ".join(str(a.processIdentifier()) for a in existing)
                raise LaunchError(
                    f"another {bundle_id} instance is already running (pid {pids}); "
                    f"close it before launching the sandbox")

        args = [str(exe_path), "--datadir", str(datadir_path)]
        if model is not None:
            model_path = Path(model).expanduser().resolve()
            if not model_path.exists():
                raise FileNotFoundError(f"model not found: {model_path}")
            args.append(str(model_path))

        child_env = {k: v for k, v in os.environ.items()
                     if k.upper() != "ORCA_GUI_TEST_MODE"}
        if env:
            child_env.update({str(k): str(v) for k, v in env.items()})

        if log_path is None:
            log_path = datadir_path / "driver_stdout.log"
        log_path = Path(log_path).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = log_path.open("ab", buffering=0)

        print(f"[macos] launching {' '.join(args)}")
        try:
            popen = subprocess.Popen(
                args, cwd=str(exe_path.parent), env=child_env,
                stdout=log_fh, stderr=subprocess.STDOUT)
        except Exception:
            log_fh.close()
            raise

        app = AppHandle(
            pid=int(popen.pid), path=exe_path, bundle_id=bundle_id,
            popen=popen, datadir=datadir_path, log_path=log_path,
            extra={"log_fh": log_fh, "args": args})
        try:
            win = self.find_main_window(app.pid, timeout_s=timeout_s)
        except BaseException:
            app.terminate()
            log_fh.close()
            raise

        dismissed: list[str] = []
        if dismiss_wizard:
            dismissed = self._dismiss_boot_blockers(app.pid, win, budget_s=8.0)
        app.extra["window"] = win
        app.extra["blockers"] = dismissed
        print(f"[macos] pid={app.pid} main window id={win.id} "
              f"rect={win.rect.to_xywh()} scale={win.scale:.2f}")
        if dismissed:
            print(f"[macos] dismissed boot blockers: {dismissed}")
        return app

    def _dismiss_boot_blockers(self, pid: int, main: WindowRef,
                              budget_s: float = 8.0) -> list[str]:
        dismissed: list[str] = []
        main_id = None
        try:
            self._attach_ax_window(main)
            main_id = _ax_id(main.handle) if main.handle is not None else None
        except Exception:
            pass
        deadline = time.monotonic() + budget_s
        while time.monotonic() < deadline:
            for axw in self._ax_windows(pid):
                if main_id is not None and _ax_id(axw) == main_id:
                    continue
                title = _ax_str(axw, AS.kAXTitleAttribute)
                low = title.lower()
                if not any(b in low for b in _BLOCKER_TITLES):
                    continue
                if "needs an update" in low:
                    continue  # forced upgrade: closing exits the app
                if self._ax_close_any(axw):
                    dismissed.append(title or "<untitled>")
                    print(f"[macos] dismissed blocker: {title!r}")
                    time.sleep(1.2)
            time.sleep(0.4)
        return dismissed

    def dismiss_boot_blockers(self, pid: int, main: WindowRef, *,
                              grace_s: float = 8.0,
                              budget_s: float = 6.0) -> list[str]:
        """Dismiss known blockers that appear *after* an action.

        Opening a project with customized presets raises "Customized Preset"
        again (the same title the launcher clears at boot); while it is up the
        main menus stay disabled and the window title stays empty.  Wait a
        grace period for such a window, then clear it.
        """
        deadline = time.monotonic() + max(0.0, grace_s)
        while time.monotonic() < deadline:
            for win in self.windows_for_pid(pid):
                if not win.on_screen or win.id == main.id:
                    continue
                low = (win.title or "").lower()
                if any(b in low for b in _BLOCKER_TITLES):
                    return self._dismiss_boot_blockers(
                        pid, main, budget_s=budget_s)
            time.sleep(0.4)
        return []

    def _ax_close_any(self, axw) -> bool:
        close_btn = _ax_copy(axw, AS.kAXCloseButtonAttribute)
        if close_btn is not None and _ax_perform(close_btn, AS.kAXPressAction):
            return True
        # The wizard may expose a Cancel/Close button as a descendant.
        for elem in self._walk(axw, max_depth=6):
            if _ax_str(elem, AS.kAXRoleAttribute) not in ("AXButton",):
                continue
            text = (_ax_str(elem, AS.kAXTitleAttribute) + " "
                    + _ax_str(elem, AS.kAXDescriptionAttribute)).lower()
            if any(word in text for word in _BLOCKER_BUTTONS):
                if _ax_perform(elem, AS.kAXPressAction):
                    return True
        # Custom-drawn info dialogs (e.g. "Snapmaker Orca information" about a
        # newer configuration) expose no titled button; click the OCR'd label.
        point, size = _ax_point_size(axw)
        if point and size:
            try:
                from .macos_ocr import recognize_text
                scale = self._scale_for_point(*point)
                rect = Rect(point[0] * scale, point[1] * scale,
                            size[0] * scale, size[1] * scale)
                words = recognize_text(self.capture_screen(), rect)
                for label in ("ok", "close", "got it", "continue"):
                    word = next((w for w in words
                                 if w.text.strip().lower() == label), None)
                    if word is not None:
                        self.click(*word.rect.center)
                        return True
            except Exception as exc:  # noqa: BLE001
                print(f"[macos] OCR dismiss failed: {exc!r}")
        return False

    # ------------------------------------------------------------------
    # window discovery
    # ------------------------------------------------------------------

    def _cg_window_list(self) -> list[WindowRef]:
        info = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID) or []
        scale_cache: dict[tuple[float, float], float] = {}
        result = []
        for raw in info:
            try:
                pid = int(raw.get("kCGWindowOwnerPID", 0))
                wid = int(raw.get("kCGWindowNumber", 0))
                layer = int(raw.get("kCGWindowLayer", 0))
                bounds = raw.get("kCGWindowBounds", {})
                alpha = float(raw.get("kCGWindowAlpha", 1.0))
                on_screen = bool(raw.get("kCGWindowIsOnscreen", False))
                title = raw.get("kCGWindowName", "") or ""
                # scale lookup keyed on the window centre (rounded)
                bx, by, bw, bh = _cg_bounds_tuple(bounds)
                key = (round(bx + bw / 2), round(by + bh / 2))
                if key not in scale_cache:
                    scale_cache[key] = self._scale_for_point(*key)
                scale = scale_cache[key]
                rect = Rect.from_cg_bounds(bounds, scale)
                if alpha <= 0.01:
                    continue
                result.append(WindowRef(
                    handle=None, id=wid, pid=pid, title=str(title),
                    rect=rect, layer=layer, on_screen=on_screen,
                    scale=scale, raw=dict(raw)))
            except Exception:
                continue
        result.sort(key=lambda w: w.rect.area, reverse=True)
        return result

    def windows_for_pid(self, pid: int) -> list[WindowRef]:
        return [w for w in self._cg_window_list() if w.pid == int(pid)]

    def _cg_window_by_id(self, window_id: int) -> WindowRef | None:
        if not window_id:
            return None
        info = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionIncludingWindow, window_id) or []
        for raw in info:
            try:
                if int(raw.get("kCGWindowNumber", -1)) == int(window_id):
                    bounds = raw.get("kCGWindowBounds", {})
                    bx, by, bw, bh = _cg_bounds_tuple(bounds)
                    scale = self._scale_for_point(bx + bw / 2, by + bh / 2)
                    return WindowRef(
                        id=int(window_id),
                        pid=int(raw.get("kCGWindowOwnerPID", 0)),
                        title=str(raw.get("kCGWindowName", "") or ""),
                        rect=Rect.from_cg_bounds(bounds, scale),
                        layer=int(raw.get("kCGWindowLayer", 0)),
                        on_screen=bool(raw.get("kCGWindowIsOnscreen", False)),
                        scale=scale, raw=dict(raw))
            except Exception:
                continue
        for win in self._cg_window_list():
            if win.id == int(window_id):
                return win
        return None

    def find_main_window(self, pid: int, *, timeout_s: float = 60.0,
                         stable_s: float = 1.0) -> WindowRef:
        deadline = time.monotonic() + timeout_s
        last_rect = None
        stable_since = None
        last_candidates: list[WindowRef] = []
        while time.monotonic() < deadline:
            candidates = [
                w for w in self.windows_for_pid(pid)
                if w.on_screen and w.layer == 0
                and w.rect.w >= 200 and w.rect.h >= 150
            ]
            last_candidates = candidates
            if candidates:
                win = max(candidates, key=lambda w: w.rect.area)
                if last_rect is not None and abs(win.rect.x - last_rect.x) < 1 \
                        and abs(win.rect.y - last_rect.y) < 1 \
                        and abs(win.rect.w - last_rect.w) < 1 \
                        and abs(win.rect.h - last_rect.h) < 1:
                    if stable_since is not None and \
                            time.monotonic() - stable_since >= stable_s:
                        self._attach_ax_window(win)
                        return win
                else:
                    last_rect = win.rect
                    stable_since = time.monotonic()
            time.sleep(0.25)
        detail = ", ".join(f"id={w.id} {w.rect.to_xywh()} layer={w.layer}"
                           for w in last_candidates[:5])
        raise TimeoutError(
            f"no stable main window for pid {pid} within {timeout_s}s "
            f"(candidates: {detail or 'none'})")

    def window_rect(self, win: WindowRef) -> Rect:
        fresh = self._cg_window_by_id(win.id)
        if fresh is not None:
            win.rect = fresh.rect
            win.title = fresh.title or win.title
            win.layer = fresh.layer
            win.on_screen = fresh.on_screen
            win.scale = fresh.scale
        return win.rect

    def client_rect(self, win: WindowRef) -> Rect:
        # The AX window frame is the closest stable client rectangle macOS
        # exposes; the title bar is part of it.
        self._attach_ax_window(win)
        point, size = _ax_point_size(win.handle)
        if point and size:
            scale = self._scale_for_point(*point)
            return Rect(point[0] * scale, point[1] * scale,
                        size[0] * scale, size[1] * scale)
        return self.window_rect(win)

    def client_to_screen(self, win: WindowRef, x: float, y: float) -> tuple[float, float]:
        rect = self.client_rect(win)
        return (rect.x + x, rect.y + y)

    def screen_to_client(self, win: WindowRef, x: float, y: float) -> tuple[float, float]:
        rect = self.client_rect(win)
        return (x - rect.x, y - rect.y)

    # ------------------------------------------------------------------
    # AX plumbing
    # ------------------------------------------------------------------

    def _ax_app(self, pid: int):
        app = self._ax_apps.get(pid)
        if app is None:
            app = AS.AXUIElementCreateApplication(pid)
            self._ax_apps[pid] = app
        return app

    def _ax_windows(self, pid: int) -> list:
        value = _ax_copy(self._ax_app(pid), AS.kAXWindowsAttribute)
        if not value:
            return []
        return list(value)

    def _attach_ax_window(self, win: WindowRef) -> None:
        if win.handle is not None:
            return
        windows = self._ax_windows(win.pid)
        if not windows:
            return
        best = None
        best_score = None
        for axw in windows:
            title = _ax_str(axw, AS.kAXTitleAttribute)
            point, size = _ax_point_size(axw)
            if point and size:
                scale = self._scale_for_point(*point)
                r = Rect(point[0] * scale, point[1] * scale,
                         size[0] * scale, size[1] * scale)
                score = (abs(r.x - win.rect.x) + abs(r.y - win.rect.y)
                         + abs(r.w - win.rect.w) + abs(r.h - win.rect.h))
            else:
                r = Rect()
                score = 1e12
            if win.title and title == win.title:
                score = -1.0
            if best_score is None or score < best_score:
                best, best_score = axw, score
        if best is None:
            best = max(windows, key=lambda w: (_ax_point_size(w)[1] or (0, 0))[0]
                       * (_ax_point_size(w)[1] or (0, 0))[1])
        win.handle = best

    def _walk(self, root, max_depth: int = 8, limit: int = 800):
        if root is None:
            return
        queue = [(root, 0)]
        seen = set()
        yielded = 0
        # AXUIElement proxies are freed between yields; their ObjC address can
        # then be reused, which made the address-keyed ``seen`` set drop real
        # children (observed on NSOpenPanel: 14 of 144 elements).  Keep every
        # element alive for the duration of the walk.
        keep = [root]
        while queue and yielded < limit:
            elem, depth = queue.pop(0)
            key = _ax_id(elem)
            if key in seen:
                continue
            seen.add(key)
            yield elem
            yielded += 1
            if depth >= max_depth:
                continue
            children = _ax_copy(elem, AS.kAXChildrenAttribute)
            if children:
                keep.extend(children)
                for child in children:
                    queue.append((child, depth + 1))

    def _ax_rect(self, element) -> Rect | None:
        point, size = _ax_point_size(element)
        if not point or not size:
            return None
        scale = self._scale_for_point(*point)
        return Rect(point[0] * scale, point[1] * scale,
                    size[0] * scale, size[1] * scale)

    def _control_from_ax(self, element, win: WindowRef) -> ControlRef:
        raw_value = _ax_copy(element, AS.kAXValueAttribute)
        value = raw_value if isinstance(raw_value, (str, int, float, bool)) else None
        ctl = ControlRef(
            handle=element,
            role=_ax_str(element, AS.kAXRoleAttribute),
            subrole=_ax_str(element, AS.kAXSubroleAttribute),
            title=_ax_str(element, AS.kAXTitleAttribute),
            description=_ax_str(element, AS.kAXDescriptionAttribute),
            value=value,
            identifier=_ax_str(element, AS.kAXIdentifierAttribute),
            enabled=bool(_ax_bool(element, AS.kAXEnabledAttribute, True)),
            selected=_ax_bool(element, AS.kAXSelectedAttribute, None),
            actions=_ax_actions(element),
            rect=self._ax_rect(element),
            window=win,
            raw={"ax_id": _ax_id(element)},
        )
        return ctl

    def controls(self, win: WindowRef, *, max_depth: int = 8) -> list[ControlRef]:
        self._require_ax()
        self._attach_ax_window(win)
        roots = []
        if win.handle is not None:
            roots.append(win.handle)
        menu = _ax_copy(self._ax_app(win.pid), AS.kAXMenuBarAttribute)
        if menu is not None:
            roots.append(menu)
        result: list[ControlRef] = []
        seen: set[int] = set()
        for root in roots:
            for elem in self._walk(root, max_depth=max_depth):
                key = _ax_id(elem)
                if key in seen:
                    continue
                seen.add(key)
                ctl = self._control_from_ax(elem, win)
                if ctl.role:
                    result.append(ctl)
        return result

    def find_control(self, win: WindowRef, *, role: str | None = None,
                     title: str | None = None, identifier: str | None = None,
                     contains: bool = True, timeout_s: float = 0.0
                     ) -> ControlRef | None:
        deadline = time.monotonic() + max(0.0, timeout_s)
        while True:
            for ctl in self.controls(win):
                if role is not None and ctl.role.lower() != role.lower():
                    continue
                if identifier is not None:
                    if contains:
                        if identifier.lower() not in ctl.identifier.lower():
                            continue
                    elif ctl.identifier.lower() != identifier.lower():
                        continue
                if title is not None:
                    hay = " ".join((ctl.title, ctl.description,
                                   ctl.text(), ctl.identifier)).lower()
                    if contains:
                        if title.lower() not in hay:
                            continue
                    elif ctl.title.lower() != title.lower():
                        continue
                return ctl
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.3)

    def click_control(self, ctl: ControlRef) -> bool:
        self._require_ax()
        if ctl.handle is None:
            return False
        for action in (AS.kAXPressAction, AS.kAXConfirmAction, "AXOpen"):
            if _ax_perform(ctl.handle, action):
                return True
        if ctl.rect is not None and ctl.rect.area > 0:
            cx, cy = ctl.rect.center
            self.click(cx, cy)
            return True
        return False

    def control_text(self, ctl: ControlRef) -> str:
        if ctl.handle is None:
            return ctl.text()
        for attr in (AS.kAXValueAttribute, AS.kAXTitleAttribute,
                     AS.kAXDescriptionAttribute):
            value = _ax_copy(ctl.handle, attr)
            if isinstance(value, str):
                return value
            if isinstance(value, (bool, int, float)):
                return str(int(value)) if isinstance(value, bool) else str(value)
        return ctl.text()

    def read_text(self, ctl: ControlRef) -> str:
        return self.control_text(ctl)

    def set_control_text(self, ctl: ControlRef, text: str) -> bool:
        self._require_ax()
        if ctl.handle is None:
            return False
        if _ax_set(ctl.handle, AS.kAXValueAttribute, text):
            return True
        if _ax_set(ctl.handle, AS.kAXFocusedAttribute, True):
            self.send_key("a", modifiers=("cmd",))
            self.send_text(text)
            return True
        return False

    # ------------------------------------------------------------------
    # native file dialogs (NSSavePanel / NSOpenPanel)
    # ------------------------------------------------------------------

    #: Panel titles seen on this build.  The save panel is a separate
    #: CGWindow (AXSubrole AXDialog, layer > 0), not an AXSheet child.
    _SAVE_PANEL_TITLES = ("save", "save as", "save as…", "export")
    _OPEN_PANEL_TITLES = ("open", "open...", "open…", "import")

    def find_file_dialog(self, pid: int, *, titles: Sequence[str],
                         exclude_id: int | None = None,
                         timeout_s: float = 12.0) -> WindowRef | None:
        """Wait for a native file panel window and return it with AX attached."""
        wanted = {t.strip().lower() for t in titles}
        deadline = time.monotonic() + max(0.0, timeout_s)
        while True:
            for win in self.windows_for_pid(pid):
                if not win.on_screen:
                    continue
                if exclude_id is not None and win.id == exclude_id:
                    continue
                if (win.title or "").strip().lower() not in wanted:
                    continue
                if win.handle is None:
                    self._attach_ax_window(win)
                if win.handle is not None:
                    return win
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.25)

    def _dialog_widgets(self, panel: WindowRef):
        """(filename field, Save button, Cancel button, Replace button).

        Keep the *first* match: the panel tree also contains display-only
        proxies with the same role/rect (a field whose value includes the
        extension, a Save button that accepts AXPress but does nothing).
        The first BFS match is the real control.
        """
        field = save = cancel = replace = None
        for elem in self._walk(panel.handle, max_depth=12):
            role = _ax_str(elem, AS.kAXRoleAttribute)
            if role == "AXTextField":
                if field is not None:
                    continue
                title = _ax_str(elem, AS.kAXTitleAttribute)
                value = _ax_copy(elem, AS.kAXValueAttribute)
                content = f"{title} {value if isinstance(value, str) else ''}".strip()
                low = content.lower()
                # Exclude the tag editor and the search field; the filename
                # field is the remaining text field with content.
                if content and "tag editor" not in low and "search" not in low:
                    field = elem
            elif role == "AXButton":
                title = _ax_str(elem, AS.kAXTitleAttribute).strip().lower()
                if title in ("save", "save as", "open", "import", "export"):
                    if save is None:
                        save = elem
                elif title == "cancel":
                    if cancel is None:
                        cancel = elem
                elif title in ("replace", "yes"):
                    if replace is None:
                        replace = elem
        return field, save, cancel, replace

    @staticmethod
    def _panel_still_open(pid: int, panel_id: int) -> bool:
        info = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionIncludingWindow, panel_id) or []
        for raw in info:
            try:
                if int(raw.get("kCGWindowNumber", -1)) == int(panel_id):
                    return bool(raw.get("kCGWindowIsOnscreen", False))
            except Exception:
                continue
        return False

    def _wait_panel_closed(self, pid: int, panel_id: int,
                           timeout_s: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_s)
        while time.monotonic() < deadline:
            if not self._panel_still_open(pid, panel_id):
                return True
            time.sleep(0.25)
        return not self._panel_still_open(pid, panel_id)

    def _wait_sidebar_cell(self, panel: WindowRef, label: str,
                           timeout_s: float = 12.0):
        """The panel's sidebar cell for ``label`` (AX tree can lag)."""
        deadline = time.monotonic() + max(0.0, timeout_s)
        while time.monotonic() < deadline:
            cell = self._find_sidebar_open(panel.handle, label)
            if cell is not None:
                return cell
            panel.handle = None
            self._attach_ax_window(panel)
            time.sleep(0.5)
        return None

    def navigate_panel_to(self, panel: WindowRef, directory: Path | str,
                          win: WindowRef, *, timeout_s: float = 60.0) -> bool:
        """Navigate an NSSavePanel/NSOpenPanel to ``directory`` (under $HOME).

        File rows are not AX-exposed, so this uses the same route as
        ``open_file_dialog``: AXOpen/click the sidebar home row, then OCR the
        panel and single-click each path component (right-most match = the
        column just opened).
        """
        home = Path.home().resolve()
        target = Path(directory).expanduser().resolve()
        try:
            components = list(target.relative_to(home).parts)
        except ValueError:
            print(f"[macos] navigate_panel_to: {target} is outside {home}")
            return False

        self.set_foreground(win)
        time.sleep(0.4)
        cell = self._wait_sidebar_cell(panel, home.name)
        if cell is None:
            print(f"[macos] navigate_panel_to: sidebar row {home.name!r} missing")
            return False
        opened = _ax_perform(cell, "AXOpen") or _ax_perform(
            cell, AS.kAXPressAction)
        if not opened:
            rect = self._ax_rect(cell)
            if rect is not None and rect.area > 0:
                self.click(*rect.center)
        time.sleep(1.2)

        deadline = time.monotonic() + timeout_s
        for component in components:
            word = None
            last_scroll = time.monotonic()
            pages = 0
            while time.monotonic() < deadline:
                word = self._pick_rightmost(
                    self._panel_ocr_words(panel), component)
                if word is not None:
                    break
                if pages < 10 and time.monotonic() - last_scroll > 2.5:
                    # Long folder lists: the row may be below the visible page.
                    self._scroll_browser(panel, down=True)
                    pages += 1
                    last_scroll = time.monotonic()
                time.sleep(0.7)
            if word is None:
                from .macos_ocr import joined_text
                print(f"[macos] navigate_panel_to: {component!r} not visible; "
                      f"panel OCR={joined_text(self._panel_ocr_words(panel))[:200]!r}")
                return False
            print(f"[macos] navigate_panel_to: open {component!r} at "
                  f"({word.rect.center[0]:.0f},{word.rect.center[1]:.0f})")
            # Save panels remember icon/list view; a double-click descends in
            # every view mode (column view also accepts it).
            self.click(*word.rect.center, clicks=2)
            time.sleep(1.4)
        return True

    def _replace_button_in_sheets(self, panel: WindowRef, main: WindowRef):
        """A Replace/OK button inside an AXSheet attached to the panel/main."""
        roots = [panel.handle, main.handle]
        for root in roots:
            if root is None:
                continue
            sheets = _ax_copy(root, "AXSheets")
            for sheet in list(sheets or []):
                for elem in self._walk(sheet, max_depth=10):
                    if _ax_str(elem, AS.kAXRoleAttribute) != "AXButton":
                        continue
                    label = (_ax_str(elem, AS.kAXTitleAttribute) + " "
                             + _ax_str(elem, AS.kAXValueAttribute)).lower()
                    if any(k in label for k in ("replace", "yes", "ok")):
                        return elem
        return None

    def save_file_dialog(self, win: WindowRef, path: Path | str, *,
                         default_dir: Path | str | None = None,
                         titles: Sequence[str] | None = None,
                         timeout_s: float = 25.0,
                         navigate_dir: bool = False,
                         name_is_stem: bool = False,
                         accept_anywhere: bool = False,
                         search_roots: Sequence[Path | str] | None = None,
                         ) -> bool:
        """Fill the open native save panel and commit it.

        The panel is expected to be open already (File > Save Project as...,
        Export STL, ...).  macOS save panels show only the *file name*; the
        directory is the panel's current folder.  For Save Project as... that
        follows the model's directory (see ``default_dir``), but the STL
        export panel remembers a global last-used folder.  ``navigate_dir``
        walks the panel sidebar + OCR to ``path.parent`` first.

        ``name_is_stem`` sets only the stem and lets the app append its own
        extension (the STL export appends ``.stl`` even to a name that already
        has one).

        Returns True when the requested ``path`` exists afterwards.
        """
        self._require_ax()
        target = Path(path).expanduser().resolve()
        panel = self.find_file_dialog(
            win.pid, titles=titles or self._SAVE_PANEL_TITLES,
            exclude_id=win.id, timeout_s=12.0)
        if panel is None:
            print(f"[macos] save_file_dialog: no save panel for pid {win.pid}")
            return False
        field = save = cancel = _replace = None
        widget_deadline = time.monotonic() + 12.0
        while time.monotonic() < widget_deadline:
            field, save, cancel, _replace = self._dialog_widgets(panel)
            if field is not None and save is not None:
                break
            # The CGWindow can appear before its AX subtree is populated.
            panel.handle = None
            self._attach_ax_window(panel)
            time.sleep(0.4)
        if field is None or save is None:
            print(f"[macos] save_file_dialog: widgets missing "
                  f"(field={field is not None}, save={save is not None})")
            return False
        where = next((elem for elem in self._walk(panel.handle, max_depth=12)
                      if _ax_str(elem, AS.kAXRoleAttribute) == "AXPopUpButton"
                      and _ax_str(elem, AS.kAXTitleAttribute)
                      .lower().startswith("where")), None)
        if where is not None:
            print(f"[macos] save_file_dialog: panel folder="
                  f"{_ax_str(where, AS.kAXTitleAttribute)!r} "
                  f"{(str(_ax_copy(where, AS.kAXValueAttribute) or ''))!r}")

        started = time.time()
        if navigate_dir and not self.navigate_panel_to(panel, target.parent, win):
            print(f"[macos] save_file_dialog: cannot navigate to "
                  f"{target.parent}")
            return False
        if navigate_dir:
            # Navigating rebuilds the panel's AX subtree; the old widget
            # wrappers become invalid (readback None) and Save would use an
            # empty name.
            field = save = None
            refresh_deadline = time.monotonic() + 8.0
            while time.monotonic() < refresh_deadline:
                field, save, cancel, _replace = self._dialog_widgets(panel)
                if field is not None and save is not None:
                    break
                time.sleep(0.3)
            if field is None or save is None:
                print("[macos] save_file_dialog: widgets lost after navigation")
                return False
        name = target.stem if name_is_stem else target.name
        if not _ax_set(field, AS.kAXValueAttribute, name):
            _ax_set(field, AS.kAXFocusedAttribute, True)
            self.send_key("a", modifiers=("cmd",))
            self.send_text(name)
        time.sleep(0.4)
        readback = _ax_copy(field, AS.kAXValueAttribute)
        print(f"[macos] save_file_dialog: name={name!r} readback={readback!r}")

        if navigate_dir or accept_anywhere:
            # Export panel: it ignores AXPress and is not a key window (real
            # keyboard/mouse focus never lands on its field), so commit with a
            # real click and rely on the fresh-file discovery below for the
            # actual name.
            save_rect = self._ax_rect(save)
            if save_rect is not None and save_rect.area > 0:
                print("[macos] save_file_dialog: real-click Save")
                self.click(*save_rect.center)
            if not self._wait_panel_closed(win.pid, panel.id, 12.0):
                print(f"[macos] save_file_dialog: AXPress Save -> "
                      f"{_ax_perform(save, AS.kAXPressAction)}")
                self._wait_panel_closed(win.pid, panel.id, 5.0)
        else:
            # Save Project as...: AXPress is the working channel; the panel is
            # not a key window, so real clicks/keys never reach it.
            for attempt in range(3):
                pressed = _ax_perform(save, AS.kAXPressAction)
                print(f"[macos] save_file_dialog: AXPress Save -> {pressed}")
                if pressed and self._wait_panel_closed(win.pid, panel.id, 4.0):
                    break
                time.sleep(0.5)

        # An overwrite prompt may appear on top of the panel ("Replace") as
        # either a separate window or an AXSheet.
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not self._panel_still_open(win.pid, panel.id):
                break
            sheet_replace = self._replace_button_in_sheets(panel, win)
            if sheet_replace is not None:
                print("[macos] save_file_dialog: sheet overwrite -> Replace "
                      f"{_ax_str(sheet_replace, AS.kAXTitleAttribute)!r}")
                _ax_perform(sheet_replace, AS.kAXPressAction)
                time.sleep(1.0)
                continue
            for cand in self.windows_for_pid(win.pid):
                if not cand.on_screen or cand.id == panel.id:
                    continue
                if cand.id == win.id:
                    continue
                if cand.handle is None:
                    self._attach_ax_window(cand)
                if cand.handle is None:
                    continue
                _f, _s, _c, replace = self._dialog_widgets(cand)
                if replace is not None:
                    print(f"[macos] save_file_dialog: overwrite prompt "
                          f"id={cand.id} title={cand.title!r} -> "
                          f"Replace {_ax_str(replace, AS.kAXTitleAttribute)!r}")
                    _ax_perform(replace, AS.kAXPressAction)
                    time.sleep(1.0)
                    break
            time.sleep(0.3)

        if target.exists():
            print(f"[macos] save_file_dialog: wrote {target}")
            return True

        # The panel may have saved into another folder, or the app may have
        # appended its own extension.  Look for a fresh file whose name starts
        # with the requested stem.
        candidates: list[Path] = []
        folders = []
        if default_dir is not None:
            folders.append(Path(default_dir).expanduser().resolve())
        folders.append(target.parent)
        stem = Path(name).stem
        for folder in folders:
            if not folder.is_dir():
                continue
            fresh: list[Path] = []
            for cand in folder.iterdir():
                try:
                    if (cand.is_file()
                            and cand.stat().st_mtime >= started - 2.0):
                        fresh.append(cand)
                except OSError:
                    continue
            named = [p for p in fresh if p.name.startswith(stem)]
            if named:
                candidates.extend(named)
            elif navigate_dir and len(fresh) == 1:
                # Export panels ignore the programmatic name and use the
                # project's own default (e.g. "Untitled.stl").  In navigate
                # mode the destination folder is dedicated and starts empty,
                # so the single fresh file is the export.
                candidates.append(fresh[0])

        if accept_anywhere and not candidates:
            # The export panel remembers a global last-used folder.  Instead
            # of navigating its (deep) column view, accept the default folder
            # and find the file this call just wrote: the newest file with the
            # target's suffix under the allowed roots.
            roots = [Path(r).expanduser().resolve() for r in (search_roots or [])]
            if not roots:
                roots = [target.parent.parent,
                         Path.home() / "Documents",
                         Path.home() / "Desktop",
                         Path.home() / "Downloads"]
            suffix = target.suffix.lower()
            fresh_any: list[Path] = []
            for root in roots:
                if not root.is_dir():
                    continue
                try:
                    for cand in root.rglob("*"):
                        try:
                            if (not cand.is_file() or cand == target
                                    or (suffix and cand.suffix.lower() != suffix)
                                    or cand.stat().st_mtime < started - 2.0):
                                continue
                        except OSError:
                            continue
                        fresh_any.append(cand)
                except OSError:
                    continue
            fresh_any.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            print(f"[macos] save_file_dialog: accept_anywhere fresh "
                  f"{[str(p) for p in fresh_any[:3]]}")
            if fresh_any:
                candidates.append(fresh_any[0])
        for cand in candidates:
            if cand == target:
                break
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(cand), str(target))
                print(f"[macos] save_file_dialog: moved {cand} -> {target}")
                break
            except OSError as exc:
                print(f"[macos] save_file_dialog: move failed: {exc}")
        if target.exists():
            return True
        print(f"[macos] save_file_dialog: {target} not found after save "
              f"(candidates={[str(c) for c in candidates]})")
        return False

    # -- open ------------------------------------------------------------

    @staticmethod
    def _find_sidebar_open(root, label: str):
        """The AXCell of the sidebar row whose text equals ``label``."""
        for elem in MacOSDriver._walk_static(root):
            if _ax_str(elem, AS.kAXRoleAttribute) != "AXCell":
                continue
            if "AXOpen" not in _ax_actions(elem):
                continue
            for child in (MacOSDriver._walk_static(elem, max_depth=2)):
                value = _ax_copy(child, AS.kAXValueAttribute)
                if isinstance(value, str) and value.strip().lower() == label.lower():
                    return elem
        return None

    @staticmethod
    def _walk_static(root, max_depth: int = 16):
        """BFS over AXChildren without requiring ``self`` (static helper)."""
        if root is None:
            return
        queue = [(root, 0)]
        seen = set()
        # See _walk: hold the AX proxies so their addresses cannot be reused
        # while the address-keyed ``seen`` set is in use.
        keep = [root]
        while queue:
            elem, depth = queue.pop(0)
            key = _ax_id(elem)
            if key in seen:
                continue
            seen.add(key)
            yield elem
            if depth >= max_depth:
                continue
            children = _ax_copy(elem, AS.kAXChildrenAttribute)
            if children:
                keep.extend(children)
                for child in children:
                    queue.append((child, depth + 1))

    @staticmethod
    def _pick_rightmost(words, token: str):
        """OCR word matching ``token`` in the right-most column."""
        token = token.strip().lower()
        if not token:
            return None
        exact = [w for w in words if w.text.strip().lower() == token]
        hits = exact or [w for w in words if token in w.text.strip().lower()]
        if not hits:
            return None
        return max(hits, key=lambda w: w.rect.x)

    @staticmethod
    def _row_click_point(panel: WindowRef, word):
        """A click point on the row that avoids the bottom button strip.

        Rows near the panel bottom overlap the Cancel/Open hover padding; a
        click there dismisses the panel (measured).  Click the row's right
        side instead, which is still inside the active file column.
        """
        x, y = word.rect.center
        if y > panel.rect.bottom - 100:
            x = panel.rect.right - 40
        return x, y

    def _panel_ocr_words(self, panel: WindowRef):
        from .macos_ocr import recognize_text  # local import: PyObjC OCR
        frame = self.capture_screen()
        return recognize_text(frame, panel.rect)

    def _scroll_browser(self, panel: WindowRef, *, down: bool = True) -> bool:
        """Page the panel's file browser vertically (long folder lists).

        AX page actions are not honoured by this panel; a real wheel event
        over the file list is what a user does and does scroll it.
        """
        # Wheel only: the AX page actions on the browser's scroll areas can
        # scroll a different column and cancel the wheel's effect (measured:
        # the same wheel works in a probe that does not perform them).
        try:
            x = panel.rect.x + panel.rect.w * 0.85
            y = panel.rect.y + panel.rect.h * 0.55
            self.wheel(x, y, -6 if down else 6)
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[macos] wheel scroll failed: {exc!r}")
            return False

    @staticmethod
    def _pick_file_word(words, target: Path):
        """OCR word for a file name, tolerant of extension I/l confusion."""
        name = target.name.casefold()
        stem = target.stem.casefold()
        if not stem:
            return None
        exact = [w for w in words if w.text.strip().casefold() == name]
        if exact:
            return max(exact, key=lambda w: w.rect.x)
        hits = [w for w in words if stem in w.text.casefold()]
        if hits:
            return max(hits, key=lambda w: w.rect.x)
        norm_stem = "".join(ch for ch in stem if ch.isalnum())
        if not norm_stem:
            return None
        norm_hits = []
        for w in words:
            norm = "".join(ch for ch in w.text.casefold() if ch.isalnum())
            if norm_stem in norm:
                norm_hits.append(w)
        return max(norm_hits, key=lambda w: w.rect.x) if norm_hits else None

    def open_file_dialog(self, win: WindowRef, path: Path | str, *,
                         titles: Sequence[str] | None = None,
                         timeout_s: float = 90.0) -> bool:
        """Navigate the open native panel to ``path`` and press Open.

        macOS's NSOpenPanel opens on "Recents" and exposes its file rows as
        empty ``AXScrollArea`` columns, so the rows are addressed visually:

        1. AXOpen the sidebar "home" row;
        2. OCR the panel and single-click each path component under ``$HOME``,
           always taking the right-most match (the column just opened);
        3. single-click the file (this enables Open) and AXPress Open.

        Paths outside ``$HOME`` are not supported by this route (Cmd+Shift+G
        does not submit on this build) and return False.
        """
        self._require_ax()
        target = Path(path).expanduser().resolve()
        panel = self.find_file_dialog(
            win.pid, titles=titles or self._OPEN_PANEL_TITLES,
            exclude_id=win.id, timeout_s=12.0)
        if panel is None:
            print(f"[macos] open_file_dialog: no open panel for pid {win.pid}")
            return False

        home = Path.home().resolve()
        try:
            components = list(target.parent.relative_to(home).parts)
        except ValueError:
            print(f"[macos] open_file_dialog: {target} is outside {home}; "
                  f"unsupported (no Go-to-folder submit)")
            return False

        self.set_foreground(win)
        time.sleep(0.4)
        home_cell = None
        home_deadline = time.monotonic() + 12.0
        while time.monotonic() < home_deadline:
            home_cell = self._find_sidebar_open(panel.handle, home.name)
            if home_cell is not None:
                break
            # The panel's AX subtree can lag the CGWindow by a second or two.
            panel.handle = None
            self._attach_ax_window(panel)
            time.sleep(0.5)
        if home_cell is None:
            print(f"[macos] open_file_dialog: sidebar row {home.name!r} missing")
            return False
        opened = _ax_perform(home_cell, "AXOpen")
        if not opened:
            opened = _ax_perform(home_cell, AS.kAXPressAction)
        if not opened:
            rect = self._ax_rect(home_cell)
            if rect is not None and rect.area > 0:
                cx, cy = rect.center
                print(f"[macos] open_file_dialog: click home row at "
                      f"({cx:.0f},{cy:.0f})")
                self.click(cx, cy)
                opened = True
        print(f"[macos] open_file_dialog: home row -> {opened}")
        time.sleep(1.2)

        deadline = time.monotonic() + timeout_s
        for component in components:
            word = None
            last_scroll = time.monotonic()
            pages = 0
            while time.monotonic() < deadline:
                word = self._pick_rightmost(
                    self._panel_ocr_words(panel), component)
                if word is not None:
                    # A row sitting on the bottom edge is under the
                    # Open/Cancel button strip; clicking it dismisses the
                    # panel.  Scroll until it is safely above the buttons.
                    if (word.rect.center[1] > panel.rect.bottom - 60
                            and pages < 16):
                        self._scroll_browser(panel, down=True)
                        pages += 1
                        last_scroll = time.monotonic()
                        word = None
                        time.sleep(0.8)
                        continue
                    break
                if pages < 16 and time.monotonic() - last_scroll > 2.5:
                    self._scroll_browser(panel, down=True)
                    pages += 1
                    last_scroll = time.monotonic()
                time.sleep(0.7)
            if word is None:
                from .macos_ocr import joined_text
                print(f"[macos] open_file_dialog: folder {component!r} "
                      f"not visible; OCR="
                      f"{joined_text(self._panel_ocr_words(panel))[-200:]!r}")
                return False
            cx, cy = self._row_click_point(panel, word)
            print(f"[macos] open_file_dialog: open {component!r} at "
                  f"({cx:.0f},{cy:.0f})")
            self.click(cx, cy)
            time.sleep(1.4)

        word = None
        retry_at = time.monotonic() + 10.0
        retried = False
        last_words = []
        last_scroll = time.monotonic()
        pages = 0
        while time.monotonic() < deadline:
            last_words = self._panel_ocr_words(panel)
            word = self._pick_file_word(last_words, target)
            if word is not None:
                break
            if pages < 6 and time.monotonic() - last_scroll > 2.5:
                self._scroll_browser(panel, down=True)
                pages += 1
                last_scroll = time.monotonic()
            if not retried and time.monotonic() >= retry_at and components:
                # The last click may have only selected the folder; click it
                # again before giving up.
                again = self._pick_rightmost(last_words, components[-1])
                if again is not None:
                    print(f"[macos] open_file_dialog: retry folder "
                          f"{components[-1]!r}")
                    self.click(*again.rect.center)
                    retried = True
                    time.sleep(1.2)
                    continue
            time.sleep(0.7)
        if word is None:
            from .macos_ocr import joined_text
            print(f"[macos] open_file_dialog: {target.name!r} not visible; "
                  f"OCR={joined_text(last_words)[-220:]!r}")
            return False
        cx, cy = self._row_click_point(panel, word)
        print(f"[macos] open_file_dialog: select {target.name!r} at "
              f"({cx:.0f},{cy:.0f})")
        self.click(cx, cy)
        time.sleep(1.0)

        _field, open_btn, _cancel, _replace = self._dialog_widgets(panel)
        if open_btn is None:
            print("[macos] open_file_dialog: Open button missing")
            return False
        enable_deadline = time.monotonic() + 5.0
        while time.monotonic() < enable_deadline:
            if _ax_bool(open_btn, AS.kAXEnabledAttribute, False):
                break
            time.sleep(0.3)
        if not _ax_bool(open_btn, AS.kAXEnabledAttribute, False):
            print("[macos] open_file_dialog: Open button stayed disabled")
            return False
        pressed = _ax_perform(open_btn, AS.kAXPressAction)
        print(f"[macos] open_file_dialog: press Open -> {pressed}")

        close_deadline = time.monotonic() + 30.0
        while time.monotonic() < close_deadline:
            if not self._panel_still_open(win.pid, panel.id):
                # A project with customized presets re-raises the same
                # "Customized Preset" blocker the launcher clears at boot;
                # it keeps the title empty and the menus disabled until
                # dismissed.
                dismissed = self.dismiss_boot_blockers(
                    win.pid, win, grace_s=6.0, budget_s=4.0)
                if dismissed:
                    print(f"[macos] open_file_dialog: cleared blockers "
                          f"{dismissed}")
                print(f"[macos] open_file_dialog: opened {target.name}")
                return True
            time.sleep(0.3)
        print("[macos] open_file_dialog: panel did not close")
        return False

    # ------------------------------------------------------------------
    # capture (ScreenCaptureKit)
    # ------------------------------------------------------------------

    def _shareable_content(self):
        now = time.monotonic()
        if self._shareable is not None and now - self._shareable_ts < 2.0:
            return self._shareable
        state = {}
        event = threading.Event()

        def handler(content, error):
            state["content"] = content
            state["error"] = error
            event.set()

        SCK.SCShareableContent \
            .getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
                False, True, handler)
        if not _wait_event(event, 10.0):
            raise CaptureError("timed out waiting for SCShareableContent")
        if state.get("error") is not None:
            raise DriverNotAvailable(
                f"ScreenCaptureKit unavailable: {state['error']}")
        self._shareable = state["content"]
        self._shareable_ts = now
        return self._shareable

    def _grab_with_filter(self, content_filter, width: int, height: int,
                          timeout_s: float = 6.0, attempts: int = 2):
        last_error = None
        for attempt in range(max(1, attempts)):
            try:
                return self._grab_once(content_filter, width, height, timeout_s)
            except CaptureError as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    print(f"[macos] capture retry ({exc})")
                    time.sleep(0.8)
        raise last_error

    def _grab_once(self, content_filter, width: int, height: int,
                   timeout_s: float = 6.0):
        self._require_screen()
        cfg = SCK.SCStreamConfiguration.alloc().init()
        cfg.setWidth_(int(width))
        cfg.setHeight_(int(height))
        cfg.setShowsCursor_(False)
        cfg.setPixelFormat_(_PIXEL_FORMAT_BGRA)
        if hasattr(cfg, "setIgnoreShadowsSingleWindow_"):
            cfg.setIgnoreShadowsSingleWindow_(True)
        grabber = _FrameGrabber.alloc().init()
        stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(
            content_filter, cfg, grabber)
        try:
            ok, error = stream.addStreamOutput_type_sampleHandlerQueue_error_(
                grabber, SCK.SCStreamOutputTypeScreen, None, None)
        except Exception as exc:  # noqa: BLE001
            raise CaptureError(f"SCStream.addStreamOutput failed: {exc}")
        if not ok:
            raise CaptureError(f"SCStream.addStreamOutput failed: {error}")

        started = threading.Event()
        start_error = {}

        def on_start(error):
            start_error["error"] = error
            started.set()

        stream.startCaptureWithCompletionHandler_(on_start)
        if not _wait_event(started, 10.0):
            raise CaptureError("SCStream.startCapture timed out")
        if start_error.get("error") is not None:
            raise CaptureError(f"SCStream.startCapture failed: {start_error['error']}")
        try:
            if not grabber.event.wait(timeout_s):
                raise CaptureError(
                    f"SCStream produced no frame within {timeout_s}s")
            if grabber.error:
                raise CaptureError(f"SCStream frame error: {grabber.error}")
            if grabber.image is None:
                raise CaptureError("SCStream returned no image")
            return grabber.image
        finally:
            stopped = threading.Event()

            def on_stop(error):
                stopped.set()

            stream.stopCaptureWithCompletionHandler_(on_stop)
            _wait_event(stopped, 3.0)

    def _cgimage_to_frame(self, image) -> Frame:
        width = int(Quartz.CGImageGetWidth(image))
        height = int(Quartz.CGImageGetHeight(image))
        if width <= 0 or height <= 0:
            raise CaptureError(f"empty CGImage {width}x{height}")
        buf = bytearray(width * height * 4)
        space = Quartz.CGColorSpaceCreateDeviceRGB()
        info = (Quartz.kCGImageAlphaPremultipliedFirst
                | Quartz.kCGBitmapByteOrder32Little)
        ctx = Quartz.CGBitmapContextCreate(
            buf, width, height, 8, width * 4, space, info)
        if ctx is None:
            raise CaptureError("CGBitmapContextCreate failed")
        # ScreenCaptureKit's CGImage already has the top row at the top:
        # drawing it without a flip produces a top-down BGRA buffer.  (An
        # extra translate/scale flip turns the whole app UI upside down —
        # caught by visual inspection of the first m2 capture.)
        Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, width, height), image)
        return Frame(width, height, bytes(buf))

    def capture(self, win: WindowRef) -> Frame:
        self._require_screen()
        win = self._refresh(win)
        if win.id:
            try:
                content = self._shareable_content()
                target = None
                for scwin in content.windows() or []:
                    try:
                        if int(scwin.windowID()) == int(win.id):
                            target = scwin
                            break
                    except Exception:
                        continue
                if target is not None:
                    content_filter = SCK.SCContentFilter.alloc() \
                        .initWithDesktopIndependentWindow_(target)
                    width = max(1, int(round(win.rect.w)))
                    height = max(1, int(round(win.rect.h)))
                    image = self._grab_with_filter(content_filter, width, height)
                    return self._cgimage_to_frame(image)
                print(f"[macos] window id={win.id} not in SCShareableContent; "
                      f"falling back to screen crop")
            except DriverNotAvailable:
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"[macos] window capture failed ({exc}); "
                      f"falling back to screen crop")
        screen = self.capture_screen()
        return screen.crop(win.rect)

    def capture_screen(self) -> Frame:
        self._require_screen()
        content = self._shareable_content()
        displays = list(content.displays() or [])
        if not displays:
            raise CaptureError("ScreenCaptureKit returned no displays")
        main_id = Quartz.CGMainDisplayID()
        display = next(
            (d for d in displays if int(d.displayID()) == int(main_id)),
            displays[0])
        width, height = self.screen_size()
        content_filter = SCK.SCContentFilter.alloc() \
            .initWithDisplay_excludingApplications_exceptingWindows_(
                display, [], [])
        image = self._grab_with_filter(content_filter, width, height)
        return self._cgimage_to_frame(image)

    def _refresh(self, win: WindowRef) -> WindowRef:
        fresh = self._cg_window_by_id(win.id)
        if fresh is not None:
            win.rect = fresh.rect
            win.title = fresh.title or win.title
            win.layer = fresh.layer
            win.on_screen = fresh.on_screen
            win.scale = fresh.scale
        return win

    # ------------------------------------------------------------------
    # input (real OS events; no message-level channel on macOS)
    # ------------------------------------------------------------------

    def move(self, x: float, y: float) -> None:
        """Move the pointer (hover) without clicking."""
        self._require_ax()
        source = self._event_source()
        scale = self._scale_for_point(x, y)
        point = Quartz.CGPointMake(x / scale, y / scale)
        event = Quartz.CGEventCreateMouseEvent(
            source, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft)
        if event is not None:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def click(self, x: float, y: float, *, button: str = "left",
              clicks: int = 1) -> None:
        self._require_ax()
        source = self._event_source()
        scale = self._scale_for_point(x, y)
        point = Quartz.CGPointMake(x / scale, y / scale)
        button = button.lower()
        if button == "right":
            down_t, up_t, cg_button = (Quartz.kCGEventRightMouseDown,
                                       Quartz.kCGEventRightMouseUp,
                                       Quartz.kCGMouseButtonRight)
        elif button == "middle":
            down_t, up_t, cg_button = (Quartz.kCGEventOtherMouseDown,
                                       Quartz.kCGEventOtherMouseUp,
                                       Quartz.kCGMouseButtonCenter)
        else:
            down_t, up_t, cg_button = (Quartz.kCGEventLeftMouseDown,
                                       Quartz.kCGEventLeftMouseUp,
                                       Quartz.kCGMouseButtonLeft)
        move = Quartz.CGEventCreateMouseEvent(
            source, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft)
        if move is not None:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
        for i in range(max(1, int(clicks))):
            down = Quartz.CGEventCreateMouseEvent(source, down_t, point, cg_button)
            up = Quartz.CGEventCreateMouseEvent(source, up_t, point, cg_button)
            if down is None or up is None:
                raise DriverError("CGEventCreateMouseEvent returned nil")
            Quartz.CGEventSetIntegerValueField(
                down, Quartz.kCGMouseEventClickState, i + 1)
            Quartz.CGEventSetIntegerValueField(
                up, Quartz.kCGMouseEventClickState, i + 1)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
            time.sleep(0.05)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
            if i + 1 < clicks:
                time.sleep(0.08)

    def wheel(self, x: float, y: float, notches: int) -> None:
        self._require_ax()
        source = self._event_source()
        scale = self._scale_for_point(x, y)
        point = Quartz.CGPointMake(x / scale, y / scale)
        move = Quartz.CGEventCreateMouseEvent(
            source, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft)
        if move is not None:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
            time.sleep(0.05)
        event = Quartz.CGEventCreateScrollWheelEvent(
            source, Quartz.kCGScrollEventUnitLine, 1, int(notches))
        if event is None:
            raise DriverError("CGEventCreateScrollWheelEvent returned nil")
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    # ANSI key codes (Carbon/HIToolbox virtual key codes).
    _KEYCODES = {
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
        "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
        "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
        "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
        "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37,
        "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44,
        "n": 45, "m": 46, ".": 47, "`": 50,
        "return": 36, "enter": 36, "tab": 48, "space": 49,
        "delete": 51, "backspace": 51, "escape": 53, "esc": 53,
        "left": 123, "right": 124, "down": 125, "up": 126,
        "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
        "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96,
        "f6": 97, "f7": 98, "f8": 100, "f9": 101, "f10": 109,
        "f11": 103, "f12": 111,
    }
    _MODIFIERS = {
        "cmd": Quartz.kCGEventFlagMaskCommand,
        "command": Quartz.kCGEventFlagMaskCommand,
        "shift": Quartz.kCGEventFlagMaskShift,
        "alt": Quartz.kCGEventFlagMaskAlternate,
        "option": Quartz.kCGEventFlagMaskAlternate,
        "opt": Quartz.kCGEventFlagMaskAlternate,
        "ctrl": Quartz.kCGEventFlagMaskControl,
        "control": Quartz.kCGEventFlagMaskControl,
    }

    def send_key(self, key: str, *, modifiers: Sequence[str] = ()) -> None:
        self._require_ax()
        auto_shift = len(key) == 1 and key.isalpha() and key.isupper()
        name = key.lower()
        code = self._KEYCODES.get(name)
        if code is None:
            raise ValueError(f"unsupported key: {key!r}")
        flags = 0
        if auto_shift:
            flags |= Quartz.kCGEventFlagMaskShift
        for mod in modifiers:
            flags |= self._MODIFIERS.get(mod.lower(), 0)
        source = self._event_source()
        for down_flag in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(source, code, down_flag)
            if event is None:
                raise DriverError("CGEventCreateKeyboardEvent returned nil")
            if flags:
                Quartz.CGEventSetFlags(event, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            time.sleep(0.02)

    def send_text(self, text: str) -> None:
        self._require_ax()
        source = self._event_source()
        try:
            for char in text:
                units = len(char.encode("utf-16-le")) // 2
                for down_flag in (True, False):
                    event = Quartz.CGEventCreateKeyboardEvent(source, 0, down_flag)
                    if event is None:
                        raise DriverError("CGEventCreateKeyboardEvent returned nil")
                    Quartz.CGEventKeyboardSetUnicodeString(event, units, char)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                time.sleep(0.01)
            return
        except Exception:
            pass
        # Clipboard fallback (restores the previous text afterwards).
        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        old = pasteboard.stringForType_(AppKit.NSPasteboardTypeString)
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, AppKit.NSPasteboardTypeString)
        self.send_key("v", modifiers=("cmd",))
        time.sleep(0.25)
        if old:
            pasteboard.clearContents()
            pasteboard.setString_forType_(old, AppKit.NSPasteboardTypeString)

    def set_foreground(self, win: WindowRef) -> bool:
        self._require_ax()
        self._attach_ax_window(win)
        if win.handle is not None:
            _ax_perform(win.handle, AS.kAXRaiseAction)
        app = AppKit.NSRunningApplication \
            .runningApplicationWithProcessIdentifier_(win.pid)
        if app is None:
            return False
        # On macOS 14+ NSRunningApplication.activateWithOptions_ is commonly
        # ignored for a background caller; the supported activation path is
        # NSWorkspace.openApplicationAtURL with activates=True.
        url = app.bundleURL()
        if url is not None:
            try:
                cfg = AppKit.NSWorkspaceOpenConfiguration.configuration()
                cfg.setActivates_(True)
                if hasattr(cfg, "setCreatesNewApplicationInstance_"):
                    cfg.setCreatesNewApplicationInstance_(False)
                event = threading.Event()

                def handler(_app, _error):
                    event.set()

                AppKit.NSWorkspace.sharedWorkspace() \
                    .openApplicationAtURL_configuration_completionHandler_(
                        url, cfg, handler)
                _wait_event(event, 5.0)
            except Exception:
                pass
        try:
            app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        except Exception:
            pass
        time.sleep(0.4)
        front = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        return bool(front is not None and front.processIdentifier() == win.pid)

    def close_window(self, win: WindowRef) -> None:
        self._require_ax()
        self._attach_ax_window(win)
        if win.handle is not None:
            button = _ax_copy(win.handle, AS.kAXCloseButtonAttribute)
            if button is not None and _ax_perform(button, AS.kAXPressAction):
                return
        # Fallback: Cmd+W on the app (works for standard wx frames).
        if self.set_foreground(win):
            self.send_key("w", modifiers=("cmd",))
