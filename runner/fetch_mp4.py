#!/usr/bin/env python3
"""fetch_mp4.py <guestPath> <hostPath> — pull a file from the guest via
relay + PS Direct + base64. v2: races the DONE marker by requiring the
relay_out header line to CHANGE after the cmd is queued, then waits for
size stability before parsing (big base64 payloads take a while to flush).

Ported from C:\\coil\\vm_setup\\fetch_mp4.py (un-versioned). Guest/relay
parameters come from env (see runner/_common.ps1 for the full list):
ORCA_BB_VM_SETUP, ORCA_BB_VM, ORCA_BB_GUEST_USER, ORCA_BB_GUEST_PASS."""
import base64, os, sys, time

VM_SETUP = os.environ.get("ORCA_BB_VM_SETUP", r"C:\coil\vm_setup")
GUEST_VM = os.environ.get("ORCA_BB_VM", "win11-test")
GUEST_USER = os.environ.get("ORCA_BB_GUEST_USER", "test")
GUEST_PASS = os.environ.get("ORCA_BB_GUEST_PASS", "123456")
CMD = VM_SETUP + r"\relay_cmd.txt"
OUT = VM_SETUP + r"\relay_out.txt"

def main():
    guest, host = sys.argv[1], sys.argv[2]
    prev_header = ""
    try:
        with open(OUT, "r", errors="replace") as f:
            prev_header = f.readline().strip()
    except OSError:
        pass
    # $cred MUST be assigned: a bare `New-Object PSCredential(...)` leaks the
    # object into the relay's 2>&1|Out-String pipeline, where it formats as a
    # two-row table that lands in front of the base64 body (measured 09-18:
    # every fetched mp4 carried a 35-byte text prefix and failed to play).
    cred = (f'$cred = New-Object System.Management.Automation.PSCredential("{GUEST_USER}",'
            f'(ConvertTo-SecureString "{GUEST_PASS}" -AsPlainText -Force))')
    cmd = (cred + f'; Invoke-Command -VMName {GUEST_VM} -Credential $cred -ScriptBlock '
           '{ [Convert]::ToBase64String([IO.File]::ReadAllBytes("%s")) }' % guest)
    with open(CMD, "w") as f:
        f.write(cmd)
    t0 = time.time()
    stable = 0
    last_size = -1
    while time.time() - t0 < 420:
        time.sleep(3)
        try:
            with open(OUT, "r", errors="replace") as f:
                header = f.readline().strip()
                raw = f.read()
        except OSError:
            continue
        if header == prev_header or "=== RUN" not in header:
            continue
        if "=== DONE" not in raw:
            continue
        # Standard base64 output is ALWAYS a multiple of 4 chars (with
        # padding) — a truncated flush is not. Requiring this plus a longer
        # stable window closes the race where the DONE marker appears while
        # the payload is still flushing (measured 09-18: 4/6 pulls came back
        # short with only the size-stability check).
        b64len = len("".join(raw[:raw.index("=== DONE")].split()))
        stable = stable + 1 if (size := len(raw)) == last_size and b64len % 4 == 0 else 0
        last_size = size
        if stable >= 2:
            break
    else:
        print(f"TIMEOUT waiting for relay ({guest})"); sys.exit(1)
    b64 = "".join(raw[:raw.index("=== DONE")].split())
    data = base64.b64decode(b64)
    with open(host, "wb") as f:
        f.write(data)
    print(f"{host}: {len(data)} bytes ({len(data)/1e6:.1f} MB)")

if __name__ == "__main__":
    main()
