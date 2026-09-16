$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  'UPTIME-H: ' + [math]::Round(((Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime).TotalHours, 1)
  'SUITE-TASK: ' + (Get-ScheduledTask -TaskName suite -ErrorAction SilentlyContinue).State
  'PROGRESS: ' + (Test-Path C:\coil\regress_progress.txt)
  'RUNNER: ' + (Test-Path C:\coil\run_m7_suite.ps1)
  'GIT: ' + (Get-Content C:\coil\orca-blackbox\.git\HEAD -ErrorAction SilentlyContinue).Trim()
}
