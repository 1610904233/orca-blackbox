#!/usr/bin/env python3
"""tools/check_windows_impact.py — "do I need Windows verification?".

Read-only classifier for the macOS-port workflow.  It compares the current
branch (and, by default, the uncommitted working tree) against a base and
answers one question:

    Does this change need Windows-side verification?

Categories
----------
macos-only   macOS probes / platform backend.  Windows never imports or
             collects these -> no Windows check.
windows-static
             Shared registry/tooling (cases.py, check_registry.py, ...).
             Run check_registry + pytest --collect-only on Windows; no GUI.
windows-behavior
             Windows runtime / test shell / templates / fixtures.
             Run the static pair, plus one smoke case (or full before merge).
neutral      docs/diag/README etc.
unknown      Not classified; review manually.

Usage
-----
    python tools/check_windows_impact.py
    python tools/check_windows_impact.py --base origin/main
    python tools/check_windows_impact.py --base origin/feat/macos-port --no-worktree
    python tools/check_windows_impact.py --json
    python tools/check_windows_impact.py --strict   # exit 2 when a check is needed

Exit: 0 = no Windows check needed; 2 = check needed (only with --strict);
      1 = git/argument error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- classification ---------------------------------------------------------

MACOS_ONLY_PREFIXES = (
    "harness/platform/",
    "tests/engine/macos_pilot/",
)
MACOS_ONLY_NAMES = {
    "tests/engine/mac_common.py",
    "tests/engine/m0_platform_contract.py",
    "tests/engine/m0_macos_boot_check.py",
    "tests/engine/m1_macos_tab_switch.py",
    "tests/engine/m2_macos_slice_chain.py",
    "tools/run_macos_smoke.sh",
}

WINDOWS_STATIC_NAMES = {
    "cases.py",
    "tools/check_registry.py",
    "tools/check_feishu_map.py",
    "pytest.ini",
    "requirements.txt",
}
WINDOWS_STATIC_PREFIXES = (
    "tools/",
)

WINDOWS_BEHAVIOR_PREFIXES = (
    "harness/",
    "runner/",
    "tests/",          # Windows case scripts; macOS probes match first
    "resources/",
    "fixtures/",
)
WINDOWS_BEHAVIOR_NAMES = {
    "tests/conftest.py",
    "tests/test_blackbox.py",
    "ui_runner.py",
    "mcp_server.py",
    "tools/run_regression.sh",
    "tools/build_ui.bat",
}

NEUTRAL_PREFIXES = (
    "docs/",
    "diag/",
    ".github/",
)
NEUTRAL_NAMES = {
    "README.md",
    ".gitignore",
    "AGENTS.md",
    ".DS_Store",       # Finder noise; untracked but not gitignored
    "tools/check_windows_impact.py",
}


def classify(path: str) -> str:
    p = path.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    if p in MACOS_ONLY_NAMES or any(p.startswith(x) for x in MACOS_ONLY_PREFIXES):
        return "macos-only"
    # Neutral first: docs/diag and the classifier itself must not trigger a
    # Windows check just because they live under a matching prefix.
    if p in NEUTRAL_NAMES or any(p.startswith(x) for x in NEUTRAL_PREFIXES):
        return "neutral"
    if p in WINDOWS_STATIC_NAMES:
        return "windows-static"
    if p in WINDOWS_BEHAVIOR_NAMES:
        return "windows-behavior"
    if any(p.startswith(x) for x in WINDOWS_BEHAVIOR_PREFIXES):
        return "windows-behavior"
    if any(p.startswith(x) for x in WINDOWS_STATIC_PREFIXES):
        return "windows-static"
    return "unknown"


# --- git helpers ------------------------------------------------------------

def _git(args: list[str], *, check: bool = False) -> list[str]:
    proc = subprocess.run(["git", *args], cwd=str(ROOT),
                          capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()}")
    if proc.returncode != 0:
        return []
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]


def _resolve_base(base: str | None) -> str:
    candidates = [base] if base else ["origin/main", "main"]
    for cand in candidates:
        if cand and _git(["rev-parse", "--verify", "--quiet", cand]):
            return cand
    raise RuntimeError(
        "cannot resolve base (tried "
        + ", ".join(str(c) for c in candidates)
        + "); pass --base <ref>")


def _changed_files(base: str, include_worktree: bool) -> list[str]:
    files: set[str] = set(_git(["diff", "--name-only", f"{base}...HEAD"]))
    if include_worktree:
        files.update(_git(["diff", "--name-only"]))
        files.update(_git(["diff", "--cached", "--name-only"]))
        files.update(_git(["ls-files", "--others", "--exclude-standard"]))
    return sorted(files)


# --- reporting --------------------------------------------------------------

def _print_group(title: str, files: list[str], max_list: int = 30) -> None:
    if not files:
        return
    print(f"\n[{title}] {len(files)}")
    shown = files[:max_list]
    for f in shown:
        print(f"  {f}")
    if len(files) > len(shown):
        print(f"  ... ({len(files) - len(shown)} more)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=None,
                    help="git base ref (default: origin/main, then main)")
    ap.add_argument("--no-worktree", action="store_true",
                    help="only committed changes, ignore staged/unstaged/untracked")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true",
                    help="exit 2 when Windows verification is needed")
    ap.add_argument("--max-list", type=int, default=30,
                    help="max files printed per category (default 30)")
    args = ap.parse_args()

    try:
        base = _resolve_base(args.base)
        changed = _changed_files(base, not args.no_worktree)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    groups: dict[str, list[str]] = {
        k: [] for k in ("macos-only", "windows-static",
                        "windows-behavior", "neutral", "unknown")
    }
    for f in changed:
        groups[classify(f)].append(f)

    if groups["windows-behavior"]:
        severity = "behavior"
        verdict = "WINDOWS BEHAVIOR CHECK RECOMMENDED"
    elif groups["windows-static"] or groups["unknown"]:
        severity = "static"
        verdict = "WINDOWS STATIC CHECK REQUIRED"
    else:
        severity = "none"
        verdict = "NO WINDOWS VERIFICATION NEEDED"

    commands = [
        "python tools/check_registry.py",
        "python -m pytest tests/test_blackbox.py --collect-only -q",
        "python -c \"from cases import CASES, enabled_cases; "
        "print(len(CASES), len(enabled_cases()), "
        "len(enabled_cases('regression')), len(enabled_cases('smoke')))\"",
    ]

    if args.json:
        print(json.dumps({
            "base": base,
            "head": "HEAD",
            "include_worktree": not args.no_worktree,
            "changed": changed,
            "groups": groups,
            "severity": severity,
            "verdict": verdict,
            "commands": commands if severity != "none" else [],
        }, indent=2))
    else:
        print("=== Windows impact check ===")
        print(f"base: {base}")
        print(f"include_worktree: {not args.no_worktree}")
        print(f"changed files: {len(changed)}")
        _print_group("macOS-only (no Windows check)", groups["macos-only"],
                     args.max_list)
        _print_group("Windows static (check_registry + collect-only)",
                     groups["windows-static"], args.max_list)
        _print_group("Windows behavior (static + smoke/full)",
                     groups["windows-behavior"], args.max_list)
        _print_group("neutral", groups["neutral"], args.max_list)
        _print_group("unknown (review manually)", groups["unknown"],
                     args.max_list)
        print(f"\nVERDICT: {verdict}")
        if severity != "none":
            print("\nRun on Windows:")
            for cmd in commands:
                print(f"  {cmd}")
        if severity == "behavior":
            print("\nAlso run one smoke case on main and this branch and compare "
                  "rc/verdict (e.g. m2_slice_chain); full suite only before merge.")
        elif severity == "none":
            print("\nAll changed files are macOS-only or neutral; "
                  "Windows runtime/registry paths are untouched.")

    if args.strict and severity != "none":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
