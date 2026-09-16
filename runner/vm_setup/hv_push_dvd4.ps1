# hv_push_dvd4.ps1 — HOST, ELEVATED. guest_dvd3.iso already built & attached; just run.
Start-Transcript -Path "C:\coil\vm_setup\hv_push_dvd4.log" -Force
$vm = "win11-test"
$cred = New-Object System.Management.Automation.PSCredential("test", (ConvertTo-SecureString "123456" -AsPlainText -Force))

Write-Host "[0] ensuring DVD attached + VM on..."
$d = Get-VMDvdDrive -VMName $vm
$d | Select-Object Id, Path | Format-Table -AutoSize
if (-not ($d | Where-Object Path -like "*guest_dvd3.iso")) {
    Stop-VM -Name $vm -TurnOff -Force; Start-Sleep -Seconds 3
    $slot = $d | Where-Object { -not $_.Path -or $_.Path -notlike "*Win11_25H2*" } | Select-Object -First 1
    Set-VMDvdDrive -VMDvdDrive $slot -Path "C:\coil\vm_setup\guest_dvd3.iso"
    Start-VM -Name $vm; Start-Sleep -Seconds 90
}

Write-Host "[1] in-guest: robocopy bundle from DVD..."
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    $drv = (Get-Volume | Where-Object { $_.DriveType -eq 'CD-ROM' -and (Test-Path "$($_.DriveLetter):\bundle") } | Select-Object -First 1).DriveLetter
    if (-not $drv) { throw "bundle DVD not found in guest" }
    "copying from ${drv}: ..."
    robocopy "${drv}:\bundle" C:\coil\bx /E /NFL /NDL /NJH /NJS | Out-Null
    Copy-Item "${drv}:\hv_provision3.ps1" C:\hv_provision3.ps1 -Force
    "copied: " + [math]::Round(((Get-ChildItem C:\coil\bx -Recurse | Measure-Object Length -Sum).Sum)/1MB) + " MB"
}

Write-Host "[2] provisioner (10-15 min)..."
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    powershell -ExecutionPolicy Bypass -File C:\hv_provision3.ps1
}
Write-Host "[3] GL result:"
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock { Get-Content C:\coil\gl_probe_result.txt -ErrorAction SilentlyContinue }
Stop-Transcript
