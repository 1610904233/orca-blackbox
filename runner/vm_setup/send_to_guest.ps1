# send_to_guest.ps1 — HOST. Builds a relay_cmd.txt that pushes <file> into the guest
# as C:\<destName> and then runs <guestRunPath> via PS Direct. Usage:
#   powershell -File send_to_guest.ps1 <localFile> <guestDestPath> [<guestRunCmd>>
param(
    [Parameter(Mandatory=$true)][string]$LocalFile,
    [Parameter(Mandatory=$true)][string]$GuestDest,
    [string]$GuestRun = ""
)
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($LocalFile))
$inner = "param(`$b64); [IO.File]::WriteAllBytes('$GuestDest', [Convert]::FromBase64String(`$b64))"
if ($GuestRun) { $inner += "; powershell -ExecutionPolicy Bypass -File $GuestRun" }
$cmd = 'Invoke-Command -VMName win11-test -Credential (New-Object System.Management.Automation.PSCredential("test",(ConvertTo-SecureString "123456" -AsPlainText -Force))) -ScriptBlock { ' + $inner + ' } -ArgumentList "' + $b64 + '"'
Set-Content -Path "C:\coil\vm_setup\relay_cmd.txt" -Value $cmd -Encoding ASCII
Write-Host "relay command queued ($([math]::Round($b64.Length/1KB)) KB)"
