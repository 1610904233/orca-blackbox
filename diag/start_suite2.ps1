# -*- coding: utf-8 -*-
"""start the m7 suite with FULL error capture (the silent register failure)."""
$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  $ErrorActionPreference = 'Continue'
  $sb = 'C:\coil\orca-blackbox'
  $a = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument '-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_m7_suite.ps1 m7h_context_delete m7e_rotate45 m7f_scale120 m7g_arrange m7j_change_filament m7t73 m7t74 m7t75 m7t77 m7t78 m7t81 m7t82 m7t84 m7t86 m7t88 m7t89 m7t109' `
        -WorkingDirectory $sb
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4)
  $p = New-ScheduledTaskPrincipal -GroupId 'INTERACTIVE'
  try {
    Register-ScheduledTask -TaskName suite -Action $a -Settings $st -Principal $p -Force -ErrorAction Stop | Out-Null
    'REGISTER-OK'
  } catch {
    'REGISTER-ERR: ' + $_.Exception.Message
  }
  try {
    Start-ScheduledTask -TaskName suite -ErrorAction Stop
    'START-OK: ' + (Get-ScheduledTask -TaskName suite).State
  } catch {
    'START-ERR: ' + $_.Exception.Message
  }
}
