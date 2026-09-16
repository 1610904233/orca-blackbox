$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  Unregister-ScheduledTask -TaskName suite -Confirm:$false -ErrorAction SilentlyContinue
  'UNREGISTERED (stale instance cleared)'
}
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  # re-register identical task (Unregister deleted it) then start fresh
  $sb = 'C:\coil\orca-blackbox'
  $py = 'C:\Python311\python.exe'
  $a = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument '-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_m7_suite.ps1 m7h_context_delete m7e_rotate45 m7f_scale120 m7g_arrange m7j_change_filament m7t73 m7t74 m7t75 m7t77 m7t78 m7t81 m7t82 m7t84 m7t86 m7t88 m7t89 m7t109' `
        -WorkingDirectory $sb
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4) -MultipleInstancesPolicy Parallel
  $p = New-ScheduledTaskPrincipal -GroupId 'INTERACTIVE'
  Register-ScheduledTask -TaskName suite -Action $a -Settings $st -Principal $p -Force | Out-Null
  Set-ScheduledTask -TaskName suite -Settings $st | Out-Null
  Remove-Item C:\coil\regress_progress.txt -ErrorAction SilentlyContinue
  Start-ScheduledTask -TaskName suite
  'STARTED ' + (Get-ScheduledTask suite).State
}
