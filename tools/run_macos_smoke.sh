#!/bin/bash
# run_macos_smoke.sh — run the macOS-only smoke suite registered in cases.py.
#
# The list comes from cases.MACOS_SMOKE (never hardcode case names here).
# This runner is macOS-only: the probes need PyObjC + ScreenCaptureKit and a
# granted Accessibility/Screen Recording session.
#
# Usage (from anywhere):
#   tools/run_macos_smoke.sh
#
# Per-case logs: artifacts/mac/smoke/<case>.log
# Each probe also writes its own artifacts/mac/<m0|m1|m2>/ report + screenshots.

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 2

if [ "$(uname -s)" != "Darwin" ]; then
  echo "ERROR: run_macos_smoke.sh is macOS-only (found $(uname -s))"
  exit 2
fi

PY=./.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "ERROR: $PY not found. Create the macOS venv first:"
  echo "  python3 -m venv .venv && .venv/bin/pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-ApplicationServices pyobjc-framework-ScreenCaptureKit"
  exit 2
fi

OUT=artifacts/mac/smoke
mkdir -p "$OUT"

CASES=$($PY -c "from cases import macos_smoke_cases; print(' '.join(macos_smoke_cases()))")
if [ -z "$CASES" ]; then
  echo "ERROR: empty macOS smoke list from cases.MACOS_SMOKE"
  exit 2
fi

PASS=0
FAIL=0
FAILED=""
for c in $CASES; do
  FILE=$($PY -c "from cases import macos_case_path; p=macos_case_path('$c'); print(p.as_posix() if p else '')")
  echo "=== $c ==="
  if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
    echo "[$c] RED: case file not found (${FILE:-<empty>})"
    FAIL=$((FAIL + 1))
    FAILED="$FAILED $c"
    continue
  fi
  $PY "$FILE" > "$OUT/${c}.log" 2>&1
  rc=$?
  if [ $rc -eq 0 ]; then
    PASS=$((PASS + 1))
    echo "[$c] GREEN (rc=0)  log: $OUT/${c}.log"
  else
    FAIL=$((FAIL + 1))
    FAILED="$FAILED $c"
    echo "[$c] RED rc=$rc  log: $OUT/${c}.log"
    tail -8 "$OUT/${c}.log"
  fi
done

echo "=== MACOS SMOKE SUMMARY: PASS=$PASS FAIL=$FAIL ==="
[ -n "$FAILED" ] && echo "FAILED:$FAILED"
exit $((FAIL > 0 ? 1 : 0))
