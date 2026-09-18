#!/usr/bin/env python3
"""feishu_tester_items.py — publish the tester-facing case list into the Base.

The tester doc (`docs/UI_TESTER_GUIDE.md`) is prose people read top-to-bottom; this
script parses its per-group tables into the SAME items so the Base gets a
filterable twin. One source of truth: edit the doc, re-run, the table follows —
no retyping, no drift between doc and table.

Priority is assigned here from the execution plan (§七 of the doc), because it
is a scheduling decision rather than something the table rows carry.

Usage:
    python tools/feishu_tester_items.py --out artifacts/feishu_u1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DOC = ROOT / "docs" / "UI_TESTER_GUIDE.md"

# Test ids first executed, per the doc's §七 execution advice.
P0 = re.compile(r"^(C\d+|D\d+)$")
P1 = {"A2", "A4", "A5", "B1", "B4", "B9", "B13", "B16",
      "E1", "E2", "E3", "G1", "G3", "G5", "H1", "H2", "H3", "H4"}


def priority(tid: str, group: str) -> str:
    if P0.match(tid):
        return "P0"
    if tid in P1 or group.startswith("对象列表"):
        return "P1"
    return "P2"


def split_row(line: str) -> list[str]:
    """Split a GFM row, honouring inline code and \\| escapes."""
    cells, buf, in_code, i = [], [], False, 0
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
            buf.append(ch)
        elif ch == "|" and not in_code:
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return [c.replace("**", "").strip() for c in cells]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "artifacts" / "feishu_u1"))
    args = ap.parse_args()

    lines = DOC.read_text(encoding="utf-8").splitlines()
    group = ""
    rows: list[list[str]] = []
    for line in lines:
        m = re.match(r"^###\s+(.*)$", line)
        if m:
            group = m.group(1).strip()
            continue
        if not line.startswith("|"):
            continue
        cells = split_row(line)
        if len(cells) < 5 or not re.match(r"^[A-Z]\d+$", cells[0]):
            continue                      # header / separator / non-item row
        tid, item, steps, expect, judge = cells[0], cells[1], cells[2], cells[3], cells[4]
        rows.append([tid, group, item, steps, expect, judge, priority(tid, group)])

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "tester_items.json"
    dest.write_text(json.dumps({
        "fields": ["编号", "分组", "测试项", "操作步骤", "预期结果", "判定方式", "优先级"],
        "rows": rows,
    }, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    c = Counter(r[6] for r in rows)
    g = Counter(r[1] for r in rows)
    print(f"parsed {len(rows)} test items -> {dest}")
    print("by priority:", dict(sorted(c.items())))
    for k, v in g.items():
        print(f"  {v:3}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
