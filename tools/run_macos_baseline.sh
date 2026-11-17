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
CASE_TIMEOUT=${CASE_TIMEOUT:-600}
CASE_RETRIES=${CASE_RETRIES:-1}

run_case() {
  # Run one case with a watchdog; a hung Vision/AX call must not stall the run.
  local file="$1" log="$2" pid watcher rc
  $PY "$file" > "$log" 2>&1 &
  pid=$!
  ( sleep "$CASE_TIMEOUT"
    kill -TERM "$pid" 2>/dev/null
    sleep 5
    kill -KILL "$pid" 2>/dev/null ) >/dev/null 2>&1 &
  watcher=$!
  wait "$pid"
  rc=$?
  kill "$watcher" 2>/dev/null
  wait "$watcher" 2>/dev/null
  # A timed-out case leaves its app behind and the next launch would fail with
  # "another instance is already running".
  pkill -f "Snapmaker_Orca --datadir $ROOT/artifacts/mac/" 2>/dev/null
  sleep 1
  return $rc
}

for c in $CASES; do
  FILE=$($PY -c "from cases import macos_case_path; p=macos_case_path('$c'); print(p.as_posix() if p else '')")
  echo "=== $c ==="
  if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
    echo "[$c] RED: case file not found (${FILE:-<empty>})"
    FAIL=$((FAIL + 1))
    FAILED="$FAILED $c"
    continue
  fi
  rc=1
  attempt=0
  while [ $attempt -le "$CASE_RETRIES" ]; do
    if [ $attempt -eq 0 ]; then
      LOG="$OUT/${c}.log"
    else
      LOG="$OUT/${c}.retry${attempt}.log"
    fi
    run_case "$FILE" "$LOG"
    rc=$?
    [ $rc -eq 0 ] && break
    echo "[$c] attempt $((attempt + 1)) RED rc=$rc  log: $LOG"
    tail -8 "$LOG"
    attempt=$((attempt + 1))
    [ $attempt -le "$CASE_RETRIES" ] && echo "[$c] retrying..."
  done
  if [ $rc -eq 0 ]; then
    PASS=$((PASS + 1))
    echo "[$c] GREEN (rc=0)  log: $LOG"
    if [ "$LOG" != "$OUT/${c}.log" ]; then
      echo "[$c] GREEN on retry; first-attempt log: $OUT/${c}.log" \
        | tee -a "$OUT/${c}.log"
    fi
  else
    FAIL=$((FAIL + 1))
    FAILED="$FAILED $c"
    echo "[$c] RED rc=$rc  log: $LOG"
  fi
done

echo "=== MACOS BASELINE SUMMARY: PASS=$PASS FAIL=$FAIL ==="
[ -n "$FAILED" ] && echo "FAILED:$FAILED"
exit $((FAIL > 0 ? 1 : 0))
