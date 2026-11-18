"""Small platform-neutral gcode oracles for the macOS ports.

``tests/m8_common.py`` holds the Windows versions but imports Win32 helpers at
module import time, so the macOS cases cannot reuse it.  These parsers are
copied verbatim from that module (keep the regexes in sync).
"""

from __future__ import annotations

import re

PURIFIER_RE = re.compile(rb"SET_PURIFIER_MODE[^\r\n]*")


def purifier_params(gcode_bytes: bytes) -> dict | None:
    """Parse the first SET_PURIFIER_MODE line into a dict (None if absent)."""
    match = PURIFIER_RE.search(gcode_bytes)
    if not match:
        return None
    line = match.group(0)
    out = {}
    for key in (b"MODE", b"DESIRE_TEMP", b"ALARM_TEMP", b"FAN_SPEED",
                b"DELAY_OFF"):
        km = re.search(key + rb"=([-\w.]+)", line)
        out[key.decode()] = km.group(1).decode() if km else None
    return out


def used_filaments(gcode_bytes: bytes) -> list[int]:
    """1-based slots with a nonzero '; filament used [g]' weight."""
    match = re.search(rb"; filament used \[g\] ?= ?([\d., ]+)", gcode_bytes)
    if not match:
        return []
    vals = [float(v) for v in re.split(rb"[, ]+", match.group(1).strip()) if v]
    return [i + 1 for i, v in enumerate(vals) if v > 0]


def tool_changes(gcode_bytes: bytes) -> list[str]:
    """Distinct ^T<n> tool-change commands (mixing-slice evidence)."""
    seen: list[str] = []
    for match in re.finditer(rb"^T(\d+)\b", gcode_bytes, re.M):
        tool = f"T{int(match.group(1))}"
        if tool not in seen:
            seen.append(tool)
    return seen
