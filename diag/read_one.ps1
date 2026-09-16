$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  Get-Content C:\coil\orca-blackbox\artifacts\regress_m7t73.log -Tail 12 -ErrorAction SilentlyContinue
  '---HEAD---'
  & 'C:\coil\tools\mingit\cmd\git.exe' -C C:\coil\orca-blackbox log --oneline -1
}
