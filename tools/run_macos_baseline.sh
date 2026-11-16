#!/bin/bash
# run_macos_baseline.sh — run the macOS ports registered in cases.MACOS_BASELINE.
#
# These are macOS ports of ENABLED Windows baseline cases.  They are kept
# separate from CASES so the Windows suite never collects them.  The list
# comes from cases.py (never hardcode case names here).
#
# Usage (from anywhere):
#   tools/run_macos_baseline.sh
#
# Per-case logs: artifacts/mac/baseline/<case>.log
# Each probe also writes its own artifacts/mac/pilot/... evidence.

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 2

if [ "$(uname -s)" != "Darwin" ]; then
  echo "ERROR: run_macos_baseline.sh is macOS-only (found $(uname -s))"
  exit 2
fi

PY=./.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "ERROR: $PY not found; create the macOS venv first"
  exit 2
fi

OUT=artifacts/mac/baseline
mkdir -p "$OUT"

CASES=$($PY -c "from cases import macos_baseline_cases; print(' '.join(macos_baseline_cases()))")
if [ -z "$CASES" ]; then
  echo "ERROR: empty macOS baseline list from cases.MACOS_BASELINE"
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

echo "=== MACOS BASELINE SUMMARY: PASS=$PASS FAIL=$FAIL ==="
[ -n "$FAILED" ] && echo "FAILED:$FAILED"
exit $((FAIL > 0 ? 1 : 0))
