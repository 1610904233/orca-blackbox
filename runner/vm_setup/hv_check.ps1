# hv_check.ps1 — ELEVATED. Verify VM guest state via PowerShell Direct.
Start-Transcript -Path "C:\coil\vm_setup\hv_check.log" -Force
$pw = ConvertTo-SecureString '123456' -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential('test', $pw)
Invoke-Command -VMName win11-test -Credential $cred -ScriptBlock {
  "ComputerName: $env:COMPUTERNAME"
  "OS: " + (Get-CimInstance Win32_OperatingSystem).Caption
  "FreeGB: " + [math]::Round((Get-PSDrive C).Free/1GB,1)
  "Uptime: " + ((Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime)
  "IP: " + ((Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notlike '169.*'} | Select-Object -First 1).IPAddress)
  "setup_done: " + (Test-Path C:\setup_done.txt)
}
Stop-Transcript
