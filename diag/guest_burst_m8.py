#!/usr/bin/env python3
# guest_burst_m8.ps1 generator — ONE-PS-Direct-call launcher for the m8
# batch, adapted from diag/guest_burst2.ps1 with TWO changes:
#   - NO git reset/clean (the m8 scripts are push_verify'd, uncommitted)
#   - PYTHONUNBUFFERED=1 so a killed case still leaves its partial log
# Usage: python diag/guest_burst_m8.py            (default case order)
#        python diag/guest_burst_m8.py m8e_... m8d_...
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PS1 = HERE / "artifacts" / "burst_m8.ps1"

CASES = ["m8e_purifier_weakcool", "m8d_purifier_gcode",
         "m8c_temp_mix_gate", "m8f_nozzle_flow",
         "m8b_official_color", "m8a_fit_view"]

TEMPLATE = """$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {{
  $sb = 'C:\\coil\\orca-blackbox'
  $py = 'C:\\Python311\\python.exe'
  $cases = @('{cases}')
  $caseList = $cases -join ' '
  $runner = @"
if (`$args) {{ `$cases = @((`$args -join ' ') -split '\\s+' | Where-Object {{ `$_ }}) }}
`$env:PYTHONIOENCODING = 'utf-8'
`$env:PYTHONUNBUFFERED = '1'
`$sb = '$sb'
Set-Location `$sb
New-Item -ItemType Directory -Force artifacts | Out-Null
Remove-Item C:\\coil\\regress_summary.txt -ErrorAction SilentlyContinue
'M8 RUN: ' + `$cases.Count + ' cases ' + (Get-Date -Format T) | Set-Content C:\\coil\\regress_progress.txt
`$pass = 0; `$fail = 0
foreach (`$c in `$cases) {{
  '=== ' + `$c + ' ===' | Add-Content C:\\coil\\regress_progress.txt
  & '$py' ('tests\\' + `$c + '.py') 2>&1 |
    Out-File -FilePath ('artifacts\\regress_' + `$c + '.log') -Encoding utf8
  if (`$LASTEXITCODE -eq 0) {{ `$pass++; 'GREEN ' + `$c | Add-Content C:\\coil\\regress_progress.txt }}
  else {{ `$fail++; 'RED ' + `$c + ' rc=' + `$LASTEXITCODE | Add-Content C:\\coil\\regress_progress.txt }}
}}
'SUMMARY: PASS=' + `$pass + ' FAIL=' + `$fail | Set-Content C:\\coil\\regress_summary.txt
"@
  [IO.File]::WriteAllText('C:\\coil\\run_m8_suite.ps1', $runner)
  Unregister-ScheduledTask -TaskName suite -Confirm:$false -ErrorAction SilentlyContinue
  $a = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument ('-NoProfile -ExecutionPolicy Bypass -File C:\\coil\\run_m8_suite.ps1 ' + $caseList) `
        -WorkingDirectory $sb
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4)
  $p = New-ScheduledTaskPrincipal -GroupId 'INTERACTIVE'
  Register-ScheduledTask -TaskName suite -Action $a -Settings $st -Principal $p -Force | Out-Null
  Set-ScheduledTask -TaskName suite -Settings $st | Out-Null
  Remove-Item C:\\coil\\regress_progress.txt -ErrorAction SilentlyContinue
  Start-ScheduledTask -TaskName suite
  'SUITE-LAUNCHED ' + (Get-ScheduledTask suite).State
}}
"""


def main() -> int:
    cases = sys.argv[1:] or CASES
    quoted = "' '".join(cases)
    PS1.write_text(TEMPLATE.format(cases=quoted), encoding="utf-8")
    sys.path.insert(0, str(HERE / "runner"))
    from relay_run import relay_transact
    out = relay_transact(PS1.read_text(encoding="utf-8"), timeout_s=240)
    print(out)
    return 0 if out and "SUITE-LAUNCHED" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
