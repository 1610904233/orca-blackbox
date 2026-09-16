# fetch_from_guest.ps1 <guestPath> <hostPath> — pull a file out of the guest via PS Direct (byte[] round-trip).
param([string]$GuestPath,[string]$HostPath)
$cred = New-Object System.Management.Automation.PSCredential("test",(ConvertTo-SecureString "123456" -AsPlainText -Force))
$b = Invoke-Command -VMName win11-test -Credential $cred -ScriptBlock { param($p) [IO.File]::ReadAllBytes($p) } -ArgumentList $GuestPath
[IO.File]::WriteAllBytes($HostPath, [byte[]]$b)
"written $HostPath $((Get-Item $HostPath).Length) bytes"
