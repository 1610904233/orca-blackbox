$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  'UPTIME-H: ' + [math]::Round(((Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime).TotalHours, 1)
  'TASK: ' + (Get-ScheduledTask -TaskName suite -ErrorAction SilentlyContinue).State
  'PY: ' + (Get-Process python -ErrorAction SilentlyContinue).Count + ' ORCA: ' + (Get-Process snapmaker-orca -ErrorAction SilentlyContinue).Count
  '--- WER/AppErrors (last 6) ---'
  try {
    Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000,1001} -MaxEvents 6 -ErrorAction Stop |
      ForEach-Object { $_.TimeCreated.ToString('HH:mm') + ' id=' + $_.Id + ' ' + ($_.Message -split "`r`n")[0..2] -join ' | ' }
  } catch { 'no events: ' + $_.Exception.Message.Substring(0,60) }
  '--- PROGRESS TAIL ---'
  Get-Content C:\coil\regress_progress.txt -Tail 10 -ErrorAction SilentlyContinue
}
