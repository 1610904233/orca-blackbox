#!/usr/bin/env python3
# feishu_writeback.py — host-side closeout step: patch the Feishu Base table's
# 自动化状态 field for a batch's GREEN cases, in the SAME payload shape as
# the historical writebacks (artifacts/feishu_base/wb_*.json):
#   {"record_id_list": [...], "patch": {"自动化状态": "已自动化"}}
#
# Mapping source is a JSON file record_id -> {"case": ..., ...} (the shape of
# diag/feishu_0908/writeback_map.json). Case names come from argv — use the
# names the batch log printed (regress_progress.txt). A map entry matches a
# name when any "/"-separated token of its "case" value equals the name or is
# its prefix at a "_" boundary ("m7a" matches "m7a_boot_shutdown", "m2/m3a"
# matches "m3a_empty_slice").
#
# Safety:
#   - default is DRY-RUN: payload files + the exact lark-cli command printed,
#     nothing written to the Base;
#   - any requested case name with ZERO matching records aborts the whole
#     writeback (exit 2) — never patch a partial set silently;
#   - --apply executes lark-cli base +record-batch-update (host npm global;
#     the guest has no lark-cli and no credentials — writeback is host-side
#     by design), then reads every record back and checks the field value
#     before reporting success (read-back rule, 09-16 session);
#   - batches of >200 records are chunked (platform limit per call).
#
# Usage:
#   python tools/feishu_writeback.py m7a_boot_shutdown m7c_import_stl       # dry-run
#   python tools/feishu_writeback.py m7a_boot_shutdown --apply              # write + verify
#   python tools/feishu_writeback.py --map diag/feishu_0908/writeback_map.json m7d_import_corrupt
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DEFAULT_MAP = ROOT / "diag" / "feishu_0908" / "writeback_map.json"
DEFAULT_BASE = "EDUAbYWcbaL2HOsgFM1cXmBpn5f"   # FEISHU_BASELINE.md header
DEFAULT_TABLE = "tblvh0eGrID9JQ02"              # FEISHU_BASELINE.md header
BATCH_LIMIT = 200  # platform limit for +record-batch-update (tools/feishu_u1_base.py:31)


def load_map(path: Path) -> dict[str, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"map must be a JSON object: {path}")
    return raw


def case_tokens(entry: dict) -> set[str]:
    value = entry.get("case", "")
    return {t.strip() for t in str(value).split("/") if t.strip()}


def matches(name: str, entry: dict) -> bool:
    return any(name == t or name.startswith(t + "_") for t in case_tokens(entry))


def resolve(map: dict[str, dict], cases: list[str]) -> tuple[list[str], list[str]]:
    """Return (record_ids, unmatched_case_names)."""
    found: list[str] = []
    for name in cases:
        hits = [rid for rid, entry in map.items() if matches(name, entry)]
        if not hits:
            return [], [name]  # abort on the FIRST gap; caller reports all later
        found.extend(hits)
    # preserve map order, drop duplicates
    seen: set[str] = set()
    ordered = [rid for rid in found if not (rid in seen or seen.add(rid))]
    return ordered, []


def chunked(ids: list[str], limit: int = BATCH_LIMIT) -> list[list[str]]:
    return [ids[i:i + limit] for i in range(0, len(ids), limit)]


def write_payloads(chunks: list[list[str]], field: str, value: str,
                   out_dir: Path, stem: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, chunk in enumerate(chunks, start=1):
        payload = {"record_id_list": chunk, "patch": {field: value}}
        base = stem if len(chunks) == 1 else f"{stem}_{i}"
        path = out_dir / f"{base}.json"
        n = 2
        while path.exists():  # never silently overwrite an earlier batch's payload
            path = out_dir / f"{base}_{n}.json"
            n += 1
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        paths.append(path)
    return paths


def lark_cmd(*args: str) -> list[str]:
    exe = shutil.which("lark-cli")
    if not exe:
        sys.stderr.write("lark-cli not found on PATH — install it on the HOST (npm global);\n"
                         "the guest has no lark-cli and no credentials: writeback is host-side.\n")
        sys.exit(3)
    return [exe, *args]


def run_lark(args: list[str]) -> dict | None:
    """Run lark-cli; return parsed JSON, or None when stdout is not JSON."""
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)
    if proc.returncode != 0:
        sys.stderr.write(f"lark-cli failed rc={proc.returncode}\n{proc.stderr[-2000:]}\n")
        sys.exit(3)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def update_records(payload_paths: list[Path], base: str, table: str) -> None:
    for path in payload_paths:
        print(f"[writeback] applying {path} ...")
        run_lark(lark_cmd("base", "+record-batch-update",
                          "--base-token", base, "--table-id", table,
                          "--json", f"@{path}"))


def cell_value(row: object) -> object:
    """Single-select cells arrive as a list of strings in record-get output."""
    if isinstance(row, list) and row and isinstance(row[0], list) and row[0]:
        return row[0][0]
    return row


def verify_records(ids: list[str], base: str, table: str, field: str, value: str) -> None:
    print(f"[writeback] read-back verify: {len(ids)} record(s), field '{field}' == '{value}' ...")
    resp = run_lark(lark_cmd("base", "+record-get",
                             "--base-token", base, "--table-id", table,
                             "--field-id", field, "--format", "json",
                             "--json", json.dumps({"record_id_list": ids})))
    if not resp or not isinstance(resp.get("data"), dict):
        sys.stderr.write("read-back failed: unexpected response shape, cannot verify\n")
        sys.exit(3)
    rows = resp["data"].get("data", [])
    got = {}
    for row in rows:
        if isinstance(row, list) and len(row) >= 2:
            got[str(row[0])] = cell_value(row[1])
    bad = {rid: got.get(rid) for rid in ids if got.get(rid) != value}
    if bad:
        sample = ", ".join(f"{rid}={v!r}" for rid, v in list(bad.items())[:5])
        sys.stderr.write(f"read-back MISMATCH on {len(bad)} record(s): {sample}\n")
        sys.exit(3)
    print(f"[writeback] verified: {len(ids)} record(s) == '{value}'")


def main() -> int:
    ap = argparse.ArgumentParser(description="Feishu 自动化状态 writeback (host-side closeout)")
    ap.add_argument("cases", nargs="+", help="GREEN case names from the batch log (regress_progress.txt)")
    ap.add_argument("--map", type=Path, default=DEFAULT_MAP, help="record_id -> {case,...} JSON")
    ap.add_argument("--base-token", default=DEFAULT_BASE)
    ap.add_argument("--table-id", default=DEFAULT_TABLE)
    ap.add_argument("--field", default="自动化状态")
    ap.add_argument("--value", default="已自动化")
    ap.add_argument("--apply", action="store_true", help="execute the update (default: dry-run)")
    ap.add_argument("--no-verify", action="store_true", help="skip read-back check (with --apply)")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "feishu_base")
    args = ap.parse_args()

    if not args.map.exists():
        sys.stderr.write(f"map not found: {args.map} (pass --map <json>; "
                         f"emit one per batch, shape = diag/feishu_0908/writeback_map.json)\n")
        return 2
    mapping = load_map(args.map)
    ids, unmatched = resolve(mapping, args.cases)
    if unmatched:
        sys.stderr.write(f"aborted: no map entry for: {', '.join(unmatched)} "
                         f"(map has {len(mapping)} records)\n")
        return 2
    if not ids:
        sys.stderr.write("aborted: zero records resolved\n")
        return 2

    stem = f"wb_green_{time.strftime('%Y%m%d_%H%M%S')}"
    payloads = write_payloads(chunked(ids), args.field, args.value, args.out_dir, stem)
    for p in payloads:
        print(f"[writeback] payload: {p} ({json.loads(p.read_text(encoding='utf-8'))['record_id_list'].__len__()} records)")

    if args.apply:
        update_records(payloads, args.base_token, args.table_id)
        if not args.no_verify:
            verify_records(ids, args.base_token, args.table_id, args.field, args.value)
        print("[writeback] DONE (applied + verified)" if not args.no_verify
              else "[writeback] DONE (applied, read-back skipped)")
        return 0

    for p in payloads:
        print("  dry-run command:")
        print("    lark-cli base +record-batch-update "
              f"--base-token {args.base_token} --table-id {args.table_id} --json @{p}")
    print("[writeback] DRY-RUN complete — re-run with --apply to write + verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
