"""macOS OCR via Vision (on-device, no tesseract/Homebrew).

``recognize_text(frame, region=None)`` turns a ``Frame`` (BGRA, top-down,
physical pixels) into ``OcrWord`` objects with top-left pixel rectangles.
Vision's bounding boxes are normalised and bottom-left-origin, so they are
converted here once; callers never deal with that.

This module imports PyObjC, so only import it on macOS (the macOS probes do).
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass

import Quartz
import Vision

from .base import Frame, Rect

__all__ = ["OcrWord", "OcrError", "recognize_text", "joined_text", "find_text"]

#: Vision occasionally blocks inside its detector queue (observed: a whole
#: case stuck in VNCRImageReaderDetector for 18+ minutes).  Run the request in
#: a daemon thread and fail loudly instead of hanging the suite.
DEFAULT_TIMEOUT_S = float(os.environ.get("ORCA_BB_OCR_TIMEOUT", "30"))


class OcrError(RuntimeError):
    pass


@dataclass(frozen=True)
class OcrWord:
    text: str
    rect: Rect
    confidence: float

    def __str__(self) -> str:
        return f"{self.text!r} @ {self.rect.to_xywh()} ({self.confidence:.2f})"


def _frame_to_cgimage(frame: Frame):
    data = Quartz.CFDataCreate(None, frame.data, len(frame.data))
    if data is None:
        raise OcrError("CFDataCreate failed")
    provider = Quartz.CGDataProviderCreateWithCFData(data)
    if provider is None:
        raise OcrError("CGDataProviderCreateWithCFData failed")
    space = Quartz.CGColorSpaceCreateDeviceRGB()
    info = (Quartz.kCGImageAlphaPremultipliedFirst
            | Quartz.kCGBitmapByteOrder32Little)
    image = Quartz.CGImageCreate(
        frame.width, frame.height, 8, 32, frame.width * 4,
        space, info, provider, None, False,
        Quartz.kCGRenderingIntentDefault)
    if image is None:
        raise OcrError("CGImageCreate failed")
    return image


def _recognize_text_sync(frame: Frame, region: Rect | None = None,
                         *, level: str = "accurate",
                         languages: tuple[str, ...] = ("en-US",),
                         uses_language_correction: bool = True) -> list[OcrWord]:
    """OCR a Frame (or a crop) and return words in top-left pixel coordinates."""
    crop = frame if region is None else frame.crop(region)
    if crop.width <= 0 or crop.height <= 0:
        return []
    origin_x = 0.0 if region is None else region.x
    origin_y = 0.0 if region is None else region.y

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(
        Vision.VNRequestTextRecognitionLevelAccurate
        if level == "accurate" else Vision.VNRequestTextRecognitionLevelFast)
    if languages:
        request.setRecognitionLanguages_(list(languages))
    request.setUsesLanguageCorrection_(bool(uses_language_correction))

    handler = Vision.VNImageRequestHandler.alloc() \
        .initWithCGImage_options_(_frame_to_cgimage(crop), None)
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise OcrError(f"Vision OCR failed: {error}")

    words: list[OcrWord] = []
    for observation in (request.results() or []):
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        text = (candidate.string() or "").strip()
        if not text:
            continue
        try:
            confidence = float(candidate.confidence())
        except Exception:
            confidence = 0.0
        bbox = observation.boundingBox()
        x = origin_x + bbox.origin.x * crop.width
        y = origin_y + (1.0 - bbox.origin.y - bbox.size.height) * crop.height
        w = bbox.size.width * crop.width
        h = bbox.size.height * crop.height
        words.append(OcrWord(text=text, rect=Rect(x, y, w, h),
                             confidence=confidence))
    return words


def recognize_text(frame: Frame, region: Rect | None = None,
                   *, level: str = "accurate",
                   languages: tuple[str, ...] = ("en-US",),
                   uses_language_correction: bool = True,
                   timeout_s: float | None = None) -> list[OcrWord]:
    """Time-bounded :func:`_recognize_text_sync` (see DEFAULT_TIMEOUT_S)."""
    timeout = DEFAULT_TIMEOUT_S if timeout_s is None else float(timeout_s)
    box: dict = {}

    def run() -> None:
        try:
            box["result"] = _recognize_text_sync(
                frame, region, level=level, languages=languages,
                uses_language_correction=uses_language_correction)
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            box["error"] = exc

    worker = threading.Thread(target=run, name="vision-ocr", daemon=True)
    worker.start()
    worker.join(max(0.1, timeout))
    if worker.is_alive():
        raise OcrError(
            f"Vision OCR timed out after {timeout:.1f}s "
            f"(detector queue blocked; see docs/PITFALLS.md)")
    if "error" in box:
        raise box["error"]
    return box.get("result", [])


def joined_text(words: list[OcrWord], sep: str = " ") -> str:
    return sep.join(w.text for w in words)


def find_text(words: list[OcrWord], needle: str,
              *, casefold: bool = True) -> OcrWord | None:
    hay = needle.casefold() if casefold else needle
    for word in words:
        text = word.text.casefold() if casefold else word.text
        if hay in text:
            return word
    return None
