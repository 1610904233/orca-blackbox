#!/usr/bin/env python3
"""batch_driver.py — autonomous small-batch verification on the guest.

The guest desktop (dwm) degrades after ~90 min of GUI load (PITFALLS §20
addendum), so the remaining 15 cases run in SMALL batches, each on a freshly
reset VM:
  watchdog flag (VM reset, ~4 min) -> queue burst (git reset to origin/main
  + register suite with the batch list) -> poll regress_summary (~25 min)
  -> record verdicts -> next batch.
Run from the repo root; appends artifacts/batch_driver2.txt.
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "runner"))
from relay_run import relay_transact  # noqa: E402

WATCHDOG = "OrcaRelayWatchdog"
FLAG = r"C:\coil\vm_setup\vm_reset.flag"
BURST_PS1 = r"C:\coil\Projects\orca-blackbox\diag\guest_burst2.ps1"
RESULTS = HERE / "artifacts" / "batch_driver2.txt"

BATCHES = [
    ["m7f_scale120", "m7j_change_filament"],
    ["m7t73", "m7t74", "m7t75"],
    ["m7t77", "m7t78", "m7t81"],
    ["m7t82", "m7t84", "m7t86"],
    ["m7t88", "m7t89", "m7t109"],
]


def relay(cmd, timeout_s=240):
    return relay_transact(cmd, timeout_s=timeout_s)


def schtasks_run():
    subprocess.run(["schtasks", "/Run", "/TN", WATCHDOG],
                   capture_output=True, text=True)


def vm_reset_cycle():
    """Watchdog flag -> VM reset + fresh daemon (done marker appears)."""
    Path(FLAG).write_text("")   # touch
    schtasks_run()
    t0 = time.time()
    done = Path(r"C:\coil\vm_setup\vm_reset.done")
    while time.time() - t0 < 300:
        time.sleep(15)
        if done.exists():
            out = done.read_text(errors="replace").strip()
            done.unlink()
            return out
    return "RESET-TIMEOUT"


def queue_burst(batch):
    case_str = " ".join(batch)
    cmd = (f"powershell -NoProfile -ExecutionPolicy Bypass -File {BURST_PS1} "
           f"-Cases '{case_str}'")
    with open(r"C:\coil\vm_setup\relay_cmd.txt", "w", encoding="ascii") as f:
        f.write(cmd)


def wait_suite(timeout_s=2400):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        time.sleep(60)
        out = relay("powershell -NoProfile -Command \"Invoke-Command -VMName "
                    "win11-test -Credential (New-Object "
                    "System.Management.Automation.PSCredential('test',"
                    "(ConvertTo-SecureString '123456' -AsPlainText -Force))) "
                    "-ScriptBlock { Test-Path C:\\coil\\regress_summary.txt }\"",
                    timeout_s=180)
        if out and "True" in out:
            relay("powershell -NoProfile -Command \"Invoke-Command -VMName "
                  "win11-test -Credential (New-Object "
                  "System.Management.Automation.PSCredential('test',"
                  "(ConvertTo-SecureString '123456' -AsPlainText -Force))) "
                  "-ScriptBlock { Remove-Item C:\\coil\\regress_summary.txt "
                  "-Force }\"", timeout_s=180)
            return True
        if out is None:
            continue
    return False


def read_progress():
    out = relay("powershell -NoProfile -ExecutionPolicy Bypass -File "
                "C:\\coil\\Projects\\orca-blackbox\\diag\\read_progress.ps1",
                timeout_s=240)
    return out or ""


def main():
    RESULTS.parent.mkdir(exist_ok=True)
    for batch in BATCHES:
        reset = vm_reset_cycle()
        time.sleep(60)          # let autologon settle
        queue_burst(batch)
        time.sleep(45)          # daemon pickup + pull + launch
        ok = wait_suite(timeout_s=max(600, len(batch) * 420))
        prog = read_progress() if ok else "(suite did not report)"
        lines = [ln for ln in prog.splitlines()
                 if ln.startswith(("GREEN", "RED")) or "SUMMARY" in ln]
        stamp = time.strftime("%H:%M")
        block = (f"=== batch {stamp}: {' '.join(batch)} ===\n"
                 f"reset={reset} reported={ok}\n" + "\n".join(lines) + "\n")
        print(block, flush=True)
        with RESULTS.open("a", encoding="utf-8") as rf:
            rf.write(block + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
