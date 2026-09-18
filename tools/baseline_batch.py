#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""baseline_batch.py — drive tests/m9_baseline.py over every input project.

One app instance PER PROJECT (isolation: a failed load must never let the next
export inherit a stale scene) and, since the Hyper-V guest proved it, a
PER-PROJECT datadir too. A failure is recorded and skipped — the batch always
walks the whole list.

    python tools/baseline_batch.py
    python tools/baseline_batch.py --indir C:\\coil\\baseline_in \\
        --outdir C:\\coil\\baseline_out --resume

Writes baseline_report.json next to the gcode output.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # repo root
WORKER = HERE / "tests" / "m9_baseline.py"
# The interpreter running THIS driver also runs the worker: the host has a
# repo .venv, the Hyper-V guest only a system python that already carries
# cv2/numpy — a hardcoded venv path does not exist there.
PY = Path(sys.executable)

REVIEW = Path(r"C:\coil\云切片专项审查")
INPUT_DIRS = [REVIEW / "基准", REVIEW / "组合"]
OUTDIR = REVIEW / "baseline_gcode"

DEFAULT_EXE = Path(r"C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe")


def load_worker():
    spec = importlib.util.spec_from_file_location("m9_worker", WORKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def artifact_path(outdir: Path, stem: str, plate: int, n_plates: int) -> Path:
    return outdir / (f"{stem}-plate{plate}-baseline.gcode" if n_plates > 1
                     else f"{stem}-baseline.gcode")


def recheck(w, model: Path, outdir: Path) -> dict | None:
    """Record for a project whose artifacts already exist on disk, or None
    when they do not (so the project must actually run).

    Resume RE-VERIFIES rather than trusting an old verdict: a stored record
    predates any change to the comparison rules, and the artifact is the
    ground truth anyway."""
    try:
        expected = w.project_config(model)
        plates = w.project_plates(model)
    except Exception:  # noqa: BLE001
        return None
    rec = {"model": str(model), "stem": model.stem, "plates": plates,
           "outputs": [], "error": None, "seconds": 0.0, "resumed": True}
    for plate in plates:
        p = artifact_path(outdir, model.stem, plate, len(plates))
        if not p.exists() or p.stat().st_size == 0:
            return None
        data = p.read_bytes()
        plain, why = w.is_plain_gcode(p)
        checks = w.verify(data, expected)
        bad = [k for k, c in checks.items() if not c["ok"] and c["required"]]
        rec["outputs"].append({
            "plate": plate, "path": str(p), "ok": plain and not bad,
            "error": "" if (plain and not bad)
                     else (why or "verification failed: " + ",".join(bad)),
            "size": len(data), "plain_gcode": plain,
            "layers": w.total_layers(data), "checks": checks,
            "identity_notes": [f"{k}: {c['actual']!r} vs input {c['expected']!r}"
                               for k, c in checks.items()
                               if not c["ok"] and not c["required"]],
        })
    if len(plates) > 1:
        # The worker asserts consecutive plates differ; resume must not be
        # weaker (measured 09-18: a resumed multi-plate record passed while
        # its plate1/plate2 artifacts were byte-identical — a plate switch
        # that never took, re-verified into a false OK).
        for a, b in zip(rec["outputs"], rec["outputs"][1:]):
            if a["ok"] and b["ok"] and \
                    Path(a["path"]).read_bytes() == Path(b["path"]).read_bytes():
                b["ok"] = False
                b["error"] = (f"identical to plate {a['plate']} — one plate "
                              f"exported twice")
    return rec


def inputs() -> list[Path]:
    out: list[Path] = []
    for d in INPUT_DIRS:
        out += sorted(p for p in d.glob("*.3mf") if p.suffix == ".3mf")
    return out


def run_one(exe: Path, datadir: Path, model: Path, outdir: Path,
            timeout: float, worker_args: list[str] | None = None,
            worker_shots: bool = False) -> dict:
    """One project, one process.

    `datadir` is a BASE: each project gets its own subdirectory. A shared
    datadir let a still-shutting-down app write its state back after the next
    seed, and the harness documents that a used datadir blocks the CLI model
    auto-load — on the slower Hyper-V guest that surfaced as "Slice click
    never took" on every second project.
    """
    cmd = [str(PY), str(WORKER), "--exe", str(exe), "--datadir", str(datadir),
           "--model", str(model), "--outdir", str(outdir),
           "--timeout", str(int(min(timeout, 900)))]
    cmd += list(worker_args or [])
    if not worker_shots:
        cmd.append("--no-shots")
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, cwd=str(HERE))
    except subprocess.TimeoutExpired:
        return {"model": str(model), "stem": model.stem, "plates": [],
                "outputs": [],
                "error": f"worker exceeded {timeout:.0f}s and was killed",
                "seconds": round(time.time() - t0, 1)}
    rec = None
    for line in reversed((p.stdout or "").splitlines()):
        if line.startswith("BASELINE_RESULT "):
            rec = json.loads(line[len("BASELINE_RESULT "):])
            break
    if rec is None:
        rec = {"model": str(model), "stem": model.stem, "outputs": [], "plates": [],
               "error": f"worker produced no result (exit {p.returncode}); "
                        f"stderr tail: {(p.stderr or '')[-800:]}"}
    rec["seconds"] = round(time.time() - t0, 1)
    rec["log_tail"] = (p.stdout or "")[-4000:]
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    ap.add_argument("--datadir", type=Path, default=Path(r"C:\coil\work\m9_profile"))
    ap.add_argument("--outdir", type=Path, default=OUTDIR)
    ap.add_argument("--indir", type=Path, action="append", default=None,
                    help="directory of input .3mf (repeatable); default = the "
                         "host review folders")
    ap.add_argument("--timeout", type=float, default=3600.0)
    ap.add_argument("--only", default=None, help="substring filter on the file stem")
    ap.add_argument("--resume", action="store_true",
                    help="re-verify projects whose gcode already exists instead "
                         "of re-slicing them")
    ap.add_argument("--skip-index", type=int, action="append", default=None,
                    help="1-based position in the job list to skip (repeatable); "
                         "ASCII-only so it survives a non-UTF8 command line")
    ap.add_argument("--worker-arg", action="append", default=None,
                    help="extra flag forwarded to the worker (repeatable), "
                         "e.g. --worker-arg=--no-shots")
    ap.add_argument("--worker-shots", action="store_true",
                    help="keep the worker's screen archiver (mp4) ON for the "
                         "whole batch. Default OFF: measured 09-18 on the "
                         "Hyper-V guest the 5fps full-screen encoder starved "
                         "cv2 (47.6 MB alloc failure in matchTemplate) and "
                         "killed the run mid-slice. Single m9 runs still "
                         "record by default.")
    args = ap.parse_args()

    global INPUT_DIRS
    if args.indir:
        INPUT_DIRS = args.indir
    jobs = inputs()
    if args.only:
        jobs = [j for j in jobs if args.only in j.stem]
    args.outdir.mkdir(parents=True, exist_ok=True)
    args.datadir.mkdir(parents=True, exist_ok=True)
    w = load_worker()
    print(f"[batch] {len(jobs)} projects -> {args.outdir}", flush=True)

    report: list[dict] = []
    t0 = time.time()
    for i, model in enumerate(jobs, 1):
        if args.skip_index and i in args.skip_index:
            print(f"[batch] {i}/{len(jobs)} SKIPPED by request", flush=True)
            continue
        if args.resume:
            rec = recheck(w, model, args.outdir)
            if rec is not None:
                report.append(rec)
                n_ok = sum(1 for o in rec["outputs"] if o["ok"])
                print(f"[batch] {i}/{len(jobs)} {rec['stem']}: RESUMED "
                      f"{n_ok}/{len(rec['outputs'])} ok", flush=True)
                continue
        print(f"\n[batch] === {i}/{len(jobs)} {model.name} ===", flush=True)
        rec = run_one(args.exe, args.datadir / f"p{i}", model, args.outdir,
                      args.timeout, args.worker_arg, args.worker_shots)
        report.append(rec)
        ok = bool(rec["outputs"]) and all(o["ok"] for o in rec["outputs"])
        print(f"[batch] {rec['stem']}: {'OK' if ok else 'FAIL'} "
              f"({rec['seconds']}s) {rec.get('error') or ''}", flush=True)
        # incremental write: a killed batch still leaves the finished part
        (args.outdir / "baseline_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    (args.outdir / "baseline_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    n_ok = sum(1 for r in report
               if r["outputs"] and all(o["ok"] for o in r["outputs"]))
    print(f"\n[batch] done in {time.time() - t0:.0f}s — "
          f"{n_ok} ok / {len(report) - n_ok} failed", flush=True)
    return 0 if n_ok == len(report) else 1


if __name__ == "__main__":
    sys.exit(main())
