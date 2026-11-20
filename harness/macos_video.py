#!/usr/bin/env python3
# harness/macos_video.py — full-screen video recorder for the macOS pilot cases.
#
# Started from tests/engine/mac_common.launch_and_focus after the main window is
# up, stopped by close_app, atexit, or the SIGTERM handler (runner watchdog).
#
# Frames come from one *persistent* ScreenCaptureKit stream (created once, 5fps
# minimum frame interval).  Two alternatives were measured and rejected:
#   * driver.capture_screen() per frame: ~120 ms per grab (new stream each call)
#     and two concurrent SCK pipelines starve each other, which slowed 2.4.2
#     enough to break menu/dialog timing in m8x_212;
#   * CGWindowListCreateImage: ~6 ms/frame but omits the app's self-drawn
#     dialogs (m8x_212's Retraction dialog never appeared in the video).
# The persistent stream keeps dialogs/menus visible at a low, steady cost.
# If SCK cannot start, the recorder falls back to CGWindowListCreateImage and
# says so in the log (dialogs may be missing from that video).
#
# Review aids:
#   * elapsed timestamp burned into the top-left corner;
#   * a fading ring at every real click / AX press (coordinates in screen px);
#   * latest PASS/FAIL state as a small colour chip at the bottom-left;
#   * <case>_<stamp>.timeline.jsonl — full log lines + clicks on the same clock;
#   * <case>_<stamp>.meta.json — duration, frame count, size, stop reason.
#
# Environment:
#   ORCA_BB_VIDEO=0          disable recording (default: enabled)
#   ORCA_BB_VIDEO_FPS=5      frames per second (clamped to 1..10)
#   ORCA_BB_VIDEO_DIR=...    override output root (default artifacts/mac/videos)

from __future__ import annotations

import atexit
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "artifacts" / "mac" / "videos"

_ACTIVE = None
_ACTIVE_LOCK = threading.RLock()
_HANDLERS_INSTALLED = False
_PREV_HANDLERS: dict[int, object] = {}

try:  # macOS-only; the recorder degrades to a no-op elsewhere
    import objc
    import Quartz
    import ScreenCaptureKit as SCK
    from CoreMedia import CMSampleBufferGetImageBuffer, CMTimeMake
    from Foundation import NSObject

    _HAS_SCK = True
except Exception:  # noqa: BLE001 - Windows tooling never imports this module
    _HAS_SCK = False
    NSObject = object  # type: ignore[assignment,misc]


def _enabled() -> bool:
    return os.environ.get("ORCA_BB_VIDEO", "1").strip().lower() not in (
        "0", "false", "no", "off")


def _fps() -> int:
    try:
        return max(1, min(10, int(os.environ.get("ORCA_BB_VIDEO_FPS", "5"))))
    except (TypeError, ValueError):
        return 5


def _safe_name(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in text)
    return cleaned.strip("._") or "case"


if _HAS_SCK:
    class _StreamGrabber(NSObject):
        """SCStreamOutput delegate: keep the latest frame as a CGImage."""

        def init(self):
            self = objc.super(_StreamGrabber, self).init()
            if self is None:
                return None
            self.lock = threading.Lock()
            self.active = True
            self.image = None
            self.seq = 0
            self.error = None
            self.ctx = Quartz.CIContext.context()
            return self

        def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buffer,
                                                 output_type):
            if not self.active:
                return
            try:
                pixel_buffer = CMSampleBufferGetImageBuffer(sample_buffer)
                if pixel_buffer is None:
                    raise RuntimeError("sample buffer has no image buffer")
                ci_image = Quartz.CIImage.imageWithCVPixelBuffer_(pixel_buffer)
                image = self.ctx.createCGImage_fromRect_(
                    ci_image, ci_image.extent())
                with self.lock:
                    self.image = image
                    self.seq += 1
            except Exception as exc:  # noqa: BLE001 - surfaced in the log
                self.error = repr(exc)

        def stream_didStopWithError_(self, stream, error):
            if error is not None and self.error is None:
                self.error = str(error)
else:  # pragma: no cover - only on non-macOS hosts
    _StreamGrabber = None  # type: ignore[assignment]


class Recorder:
    def __init__(self, driver, case: str, out_root: Path, fps: int):
        import cv2  # local import: only macOS recording needs it

        self.cv2 = cv2
        self.driver = driver
        self.case = case
        self.fps = fps
        self.out_dir = Path(out_root) / case
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = self.out_dir / f"{case}_{self.stamp}.mp4"
        self.timeline_path = self.out_dir / f"{case}_{self.stamp}.timeline.jsonl"
        self.meta_path = self.out_dir / f"{case}_{self.stamp}.meta.json"

        self.width, self.height = driver.screen_size()
        self._writer = cv2.VideoWriter(
            str(self.path), cv2.VideoWriter_fourcc(*"mp4v"), float(fps),
            (int(self.width), int(self.height)))
        if not self._writer.isOpened():
            raise RuntimeError(f"VideoWriter failed to open {self.path}")

        self._t0 = time.monotonic()
        self._started_wall = time.time()
        self._stop = threading.Event()
        self._stopped = False
        self._thread: threading.Thread | None = None
        self._frames = 0
        self._errors = 0
        self._stop_reason = ""
        self._timeline_lock = threading.Lock()
        self._timeline = self.timeline_path.open("w", encoding="utf-8")
        self._clicks: list[dict] = []
        self._last_state: tuple[float, str] | None = None
        self._last_mark: tuple[float, str] | None = None
        self._grabber = None
        self._stream = None
        self._last_seq = -1
        self._capture_mode = "sck-stream"

        try:
            self._start_stream()
        except Exception as exc:  # noqa: BLE001 - recording must never be fatal
            self._capture_mode = "cgl-fallback"
            print(f"[macos_video] SCK stream unavailable ({exc}); "
                  f"falling back to CGWindowListCreateImage "
                  f"(self-drawn dialogs may be missing)")

        self._event("start", case=case, fps=fps, capture=self._capture_mode,
                    width=self.width, height=self.height)

    # -- persistent ScreenCaptureKit stream ----------------------------
    def _start_stream(self) -> None:
        if not _HAS_SCK:
            raise RuntimeError("ScreenCaptureKit is not importable")
        event = threading.Event()
        state: dict = {}

        def handler(content, error):
            state["content"] = content
            state["error"] = error
            event.set()

        SCK.SCShareableContent \
            .getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
                False, True, handler)
        if not event.wait(10.0):
            raise RuntimeError("SCShareableContent timed out")
        if state.get("error") is not None:
            raise RuntimeError(f"SCShareableContent failed: {state['error']}")
        content = state["content"]
        displays = list(content.displays() or [])
        if not displays:
            raise RuntimeError("ScreenCaptureKit returned no displays")
        main_id = Quartz.CGMainDisplayID()
        display = next(
            (d for d in displays if int(d.displayID()) == int(main_id)),
            displays[0])
        content_filter = SCK.SCContentFilter.alloc() \
            .initWithDisplay_excludingApplications_exceptingWindows_(
                display, [], [])

        cfg = SCK.SCStreamConfiguration.alloc().init()
        cfg.setWidth_(int(self.width))
        cfg.setHeight_(int(self.height))
        cfg.setShowsCursor_(True)
        cfg.setPixelFormat_(0x42475241)  # 'BGRA'
        cfg.setMinimumFrameInterval_(CMTimeMake(1, int(self.fps)))
        if hasattr(cfg, "setIgnoreShadowsSingleWindow_"):
            cfg.setIgnoreShadowsSingleWindow_(True)

        grabber = _StreamGrabber.alloc().init()
        stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(
            content_filter, cfg, grabber)
        ok, error = stream.addStreamOutput_type_sampleHandlerQueue_error_(
            grabber, SCK.SCStreamOutputTypeScreen, None, None)
        if not ok:
            raise RuntimeError(f"SCStream.addStreamOutput failed: {error}")

        started = threading.Event()
        start_error: dict = {}

        def on_start(err):
            start_error["error"] = err
            started.set()

        stream.startCaptureWithCompletionHandler_(on_start)
        if not started.wait(10.0):
            raise RuntimeError("SCStream.startCapture timed out")
        if start_error.get("error") is not None:
            try:
                stream.stopCaptureWithCompletionHandler_(lambda _e: None)
            except Exception:
                pass
            raise RuntimeError(
                f"SCStream.startCapture failed: {start_error['error']}")

        self._grabber = grabber
        self._stream = stream

    def _stop_stream(self) -> None:
        if self._grabber is not None:
            self._grabber.active = False
        stream, self._stream = self._stream, None
        if stream is None:
            return
        stopped = threading.Event()
        try:
            stream.stopCaptureWithCompletionHandler_(lambda _e: stopped.set())
        except Exception:
            return
        stopped.wait(1.5)

    # -- timeline -----------------------------------------------------
    def _elapsed(self) -> float:
        return time.monotonic() - self._t0

    def _event(self, kind: str, **fields) -> None:
        payload = {"t": round(self._elapsed(), 3), "event": kind}
        payload.update(fields)
        line = json.dumps(payload, ensure_ascii=False)
        with self._timeline_lock:
            try:
                self._timeline.write(line + "\n")
                self._timeline.flush()
            except Exception:
                pass

    def mark(self, text: str) -> None:
        """Log line -> timeline; drives the PASS/FAIL chip overlay."""
        self._event("log", text=text)
        stripped = text.strip()
        if stripped.startswith("[PASS]"):
            self._last_state = (time.monotonic(), "PASS")
        elif stripped.startswith("[FAIL]"):
            self._last_state = (time.monotonic(), "FAIL")
        self._last_mark = (time.monotonic(), stripped)

    def note_click(self, x: float, y: float, *, button: str = "left",
                   clicks: int = 1) -> None:
        now = time.monotonic()
        self._clicks.append({"t": now, "x": float(x), "y": float(y)})
        if len(self._clicks) > 64:
            del self._clicks[:-64]
        self._event("click", x=round(float(x), 1), y=round(float(y), 1),
                    button=button, clicks=int(clicks), video_t=round(now - self._t0, 3))

    # -- frame conversion ---------------------------------------------
    def _cgimage_bgra(self, image) -> tuple[int, int, bytes]:
        width = int(Quartz.CGImageGetWidth(image))
        height = int(Quartz.CGImageGetHeight(image))
        buf = bytearray(width * height * 4)
        space = Quartz.CGColorSpaceCreateDeviceRGB()
        info = (Quartz.kCGImageAlphaPremultipliedFirst
                | Quartz.kCGBitmapByteOrder32Little)
        ctx = Quartz.CGBitmapContextCreate(
            buf, width, height, 8, width * 4, space, info)
        if ctx is None:
            raise RuntimeError("CGBitmapContextCreate failed")
        Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, width, height),
                                  image)
        return width, height, bytes(buf)

    def _grab_fallback(self) -> tuple[int, int, bytes]:
        q = Quartz
        image = q.CGWindowListCreateImage(
            q.CGRectInfinite, q.kCGWindowListOptionOnScreenOnly,
            q.kCGNullWindowID, q.kCGWindowImageDefault)
        if image is None:
            raise RuntimeError("CGWindowListCreateImage returned nil")
        return self._cgimage_bgra(image)

    def _next_image(self):
        """Return the newest CGImage, or None when the stream has not started."""
        if self._grabber is None:
            return None
        with self._grabber.lock:
            return self._grabber.image

    # -- capture loop --------------------------------------------------
    def _draw(self, bgr, now: float):
        cv2 = self.cv2
        alive = []
        for click in self._clicks:
            age = now - click["t"]
            if age > 1.2:
                continue
            alive.append(click)
            cx, cy = int(round(click["x"])), int(round(click["y"]))
            if not (0 <= cx < self.width and 0 <= cy < self.height):
                continue
            fade = max(0.0, 1.0 - age / 1.2)
            colour = (0, int(40 + 180 * fade), int(255 * fade))  # BGR: green->red
            radius = 10 + int(14 * (1.0 - fade))
            cv2.circle(bgr, (cx, cy), radius, colour, 3)
            cv2.line(bgr, (cx - 14, cy), (cx + 14, cy), colour, 1)
            cv2.line(bgr, (cx, cy - 14), (cx, cy + 14), colour, 1)
        self._clicks = alive

        elapsed = now - self._t0
        label = "%02d:%05.1f" % (int(elapsed // 60), elapsed % 60)
        cv2.putText(bgr, label, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(bgr, label, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (255, 255, 255), 2, cv2.LINE_AA)

        if self._last_state is not None:
            age = now - self._last_state[0]
            if age <= 5.0:
                state = self._last_state[1]
                colour = (60, 200, 60) if state == "PASS" else (40, 40, 220)
                cv2.putText(bgr, state, (self.width - 130, self.height - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4,
                            cv2.LINE_AA)
                cv2.putText(bgr, state, (self.width - 130, self.height - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2,
                            cv2.LINE_AA)
                cv2.circle(bgr, (self.width - 148, self.height - 30), 7,
                           colour, -1)
        return bgr

    def _loop(self) -> None:
        import numpy as np

        cv2 = self.cv2
        interval = 1.0 / self.fps
        next_t = time.monotonic()
        while not self._stop.is_set():
            try:
                image = self._next_image()
                if (image is None and self._frames == 0
                        and self._capture_mode == "sck-stream"
                        and self._elapsed() > 2.0):
                    self._capture_mode = "cgl-fallback"
                    print("[macos_video] SCK stream produced no frame; "
                          "falling back to CGWindowListCreateImage")
                if image is not None:
                    width, height, data = self._cgimage_bgra(image)
                elif self._capture_mode == "cgl-fallback":
                    width, height, data = self._grab_fallback()
                else:
                    width = height = 0
                    data = None
                if data is not None:
                    arr = np.frombuffer(data, np.uint8).reshape(
                        height, width, 4)
                    bgr = arr[:, :, :3].copy()
                    if (width, height) != (self.width, self.height):
                        bgr = cv2.resize(bgr, (self.width, self.height))
                    bgr = self._draw(bgr, time.monotonic())
                    self._writer.write(bgr)
                    self._frames += 1
                    self._errors = 0
            except Exception as exc:  # never take the case down with the video
                self._errors += 1
                if self._errors in (1, 10, 50):
                    print(f"[macos_video] capture error ({self._errors}): {exc}")
                if self._errors >= 50:
                    self._stop_reason = "capture-errors"
                    self._stop.set()
                    break
            next_t += interval
            delay = next_t - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            elif delay < -1.0:
                next_t = time.monotonic()

    def start(self) -> "Recorder":
        self._thread = threading.Thread(target=self._loop, name="macos-video",
                                        daemon=True)
        self._thread.start()
        print(f"[macos_video] recording {self.path} ({self.width}x{self.height}"
              f" @ {self.fps}fps, {self._capture_mode})")
        return self

    def stop(self, reason: str = "stop") -> None:
        if self._stopped:
            return
        self._stopped = True
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.5)
        if self._stop_reason:
            reason = self._stop_reason
        self._stop_reason = reason
        self._stop_stream()
        try:
            self._writer.release()
        except Exception:
            pass
        self._event("stop", reason=reason, frames=self._frames)
        try:
            self._timeline.close()
        except Exception:
            pass
        meta = {
            "case": self.case,
            "video": str(self.path),
            "timeline": str(self.timeline_path),
            "started_wall": self._started_wall,
            "duration_s": round(self._elapsed(), 3),
            "frames": self._frames,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "capture": self._capture_mode,
            "stop_reason": reason,
            "size_bytes": self.path.stat().st_size if self.path.exists() else 0,
        }
        try:
            self.meta_path.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
        except Exception:
            pass
        print(f"[macos_video] saved {self.path.name}: {self._frames} frames, "
              f"{meta['duration_s']:.1f}s, {meta['size_bytes'] / 1e6:.1f}MB "
              f"({reason})")


def _install_signal_handlers() -> None:
    global _HANDLERS_INSTALLED
    if _HANDLERS_INSTALLED or threading.current_thread() is not threading.main_thread():
        return
    _HANDLERS_INSTALLED = True

    def handler(signum, _frame):
        stop(reason=f"signal:{signum}")
        # Preserve the conventional exit status; the runner only cares that the
        # case is gone (and the video is finalized) before its SIGKILL step.
        os._exit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            _PREV_HANDLERS[sig] = signal.getsignal(sig)
            signal.signal(sig, handler)
        except Exception:
            pass


def start(driver, case: str | None = None, out_root: Path | str | None = None):
    """Start recording for this process; returns the active Recorder or None."""
    global _ACTIVE
    if not _enabled():
        return None
    with _ACTIVE_LOCK:
        if _ACTIVE is not None:
            return _ACTIVE
        name = _safe_name(case or Path(sys.argv[0]).stem or "case")
        root = Path(out_root or os.environ.get("ORCA_BB_VIDEO_DIR") or DEFAULT_OUT)
        try:
            rec = Recorder(driver, name, root, _fps())
        except Exception as exc:  # missing cv2 / writer backend: never fatal
            print(f"[macos_video] disabled ({exc})")
            return None
        _ACTIVE = rec
        _install_signal_handlers()
        atexit.register(stop, "atexit")
        return rec.start()


def stop(reason: str = "stop") -> None:
    global _ACTIVE
    with _ACTIVE_LOCK:
        rec, _ACTIVE = _ACTIVE, None
    if rec is not None:
        try:
            rec.stop(reason)
        except Exception as exc:
            print(f"[macos_video] stop error: {exc}")


def mark(text: str) -> None:
    rec = _ACTIVE
    if rec is not None:
        try:
            rec.mark(text)
        except Exception:
            pass


def note_click(x: float, y: float, *, button: str = "left",
               clicks: int = 1) -> None:
    rec = _ACTIVE
    if rec is not None:
        try:
            rec.note_click(x, y, button=button, clicks=clicks)
        except Exception:
            pass


def active() -> bool:
    return _ACTIVE is not None
