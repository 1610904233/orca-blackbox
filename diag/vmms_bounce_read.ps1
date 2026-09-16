Restart-Service vmms -Force
Start-Sleep 12
'SVC: ' + (Get-Service vmms).Status
$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
try {
  $r = Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
    Get-Content C:\coil\regress_summary.txt -Tail 3 -ErrorAction SilentlyContinue
    Get-Content C:\coil\regress_progress.txt -Tail 12 -ErrorAction SilentlyContinue
  } -ErrorAction Stop
  $r
} catch {
  'PSDIRECT-ERR: ' + $_.Exception.Message.Substring(0, 60)
}
