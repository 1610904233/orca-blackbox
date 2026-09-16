# guest_burst2.ps1 — ONE-PS-Direct-call: hard-sync the guest checkout to
# origin/main (the push_verify'd untracked copies are superseded by the
# committed round-3 code) and launch the remaining-cases suite autonomously.
# -Cases 'a b c' overrides the default list (batch driver uses this to run
# small batches under the dwm degradation window).
param([string]$Cases = '')
$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  $git = 'C:\coil\tools\mingit\cmd\git.exe'
  $sb = 'C:\coil\orca-blackbox'
  'FETCH: ' + ((& $git -C $sb fetch origin 2>&1 | Select-Object -Last 1))
  'RESET: ' + ((& $git -C $sb reset --hard origin/main 2>&1 | Select-Object -Last 1))
  'CLEAN: ' + ((& $git -C $sb clean -fd tests harness runner 2>&1 | Select-Object -Last 1))
  'HEAD: ' + (& $git -C $sb log --oneline -1)
  $py = 'C:\Python311\python.exe'
  if ($Cases) { $cases = @($Cases -split '\s+' | Where-Object { $_ }) }
  else {
    $cases = @('m7h_context_delete',
               'm7e_rotate45', 'm7f_scale120', 'm7g_arrange',
               'm7j_change_filament', 'm7t73', 'm7t74', 'm7t75',
               'm7t77', 'm7t78', 'm7t81', 'm7t82', 'm7t84',
               'm7t86', 'm7t88', 'm7t89', 'm7t109')
  }
  $caseList = $cases -join ' '
  $runner = @"
if (`$args) { `$cases = @((`$args -join ' ') -split '\s+' | Where-Object { `$_ }) }
`$env:PYTHONIOENCODING = 'utf-8'
`$sb = '$sb'
Set-Location `$sb
New-Item -ItemType Directory -Force artifacts | Out-Null
Remove-Item C:\coil\regress_summary.txt -ErrorAction SilentlyContinue
'REGRESSION RUN: ' + `$cases.Count + ' cases' | Set-Content C:\coil\regress_progress.txt
`$pass = 0; `$fail = 0
foreach (`$c in `$cases) {
  '=== ' + `$c + ' ===' | Add-Content C:\coil\regress_progress.txt
  & '$py' ('tests\' + `$c + '.py') 2>&1 |
    Out-File -FilePath ('artifacts\regress_' + `$c + '.log') -Encoding utf8
  if (`$LASTEXITCODE -eq 0) { `$pass++; 'GREEN ' + `$c | Add-Content C:\coil\regress_progress.txt }
  else { `$fail++; 'RED ' + `$c + ' rc=' + `$LASTEXITCODE | Add-Content C:\coil\regress_progress.txt }
}
'SUMMARY: PASS=' + `$pass + ' FAIL=' + `$fail | Set-Content C:\coil\regress_summary.txt
"@
  [IO.File]::WriteAllText('C:\coil\run_m7_suite.ps1', $runner)
  Unregister-ScheduledTask -TaskName suite -Confirm:$false -ErrorAction SilentlyContinue
  $a = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument ('-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_m7_suite.ps1 ' + $caseList) `
        -WorkingDirectory $sb
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4)
  $p = New-ScheduledTaskPrincipal -GroupId 'INTERACTIVE'
  Register-ScheduledTask -TaskName suite -Action $a -Settings $st -Principal $p -Force | Out-Null
  Set-ScheduledTask -TaskName suite -Settings $st | Out-Null
  Remove-Item C:\coil\regress_progress.txt -ErrorAction SilentlyContinue
  Start-ScheduledTask -TaskName suite
  'SUITE-LAUNCHED ' + (Get-ScheduledTask suite).State
}
