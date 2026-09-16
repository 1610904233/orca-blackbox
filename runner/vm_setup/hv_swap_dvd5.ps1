# hv_swap_dvd5.ps1 — HOST, ELEVATED. Swap to guest_dvd5.iso, copy 7z in guest, provision.
Start-Transcript -Path "C:\coil\vm_setup\hv_swap_dvd5.log" -Force
$vm = "win11-test"
$cred = New-Object System.Management.Automation.PSCredential("test", (ConvertTo-SecureString "123456" -AsPlainText -Force))

Write-Host "[1] swap DVD..."
Stop-VM -Name $vm -TurnOff -Force
Start-Sleep -Seconds 3
Get-VMDvdDrive -VMName $vm | Where-Object { $_.Path -like "*guest_dvd*" -or $_.Path -like "*unattend*" } |
    ForEach-Object { Set-VMDvdDrive -VMDvdDrive $_ -Path "C:\coil\vm_setup\guest_dvd5.iso" }
Start-VM -Name $vm
Start-Sleep -Seconds 90

Write-Host "[2] copy 7z bundle from DVD (406MB, one file - fast)..."
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    # kill any stuck robocopy from earlier
    Stop-Process -Name robocopy -Force -ErrorAction SilentlyContinue
    $drv = (Get-Volume | Where-Object { $_.DriveType -eq 'CD-ROM' -and (Test-Path "$($_.DriveLetter):\src_bundle\bundle.7z") } | Select-Object -First 1).DriveLetter
    if (-not $drv) { throw "bundle7z DVD not found" }
    New-Item -ItemType Directory -Force -Path C:\coil\src_bundle | Out-Null
    Copy-Item "${drv}:\src_bundle\*" C:\coil\src_bundle\ -Force
    "copied 7z: " + [math]::Round((Get-Item C:\coil\src_bundle\bundle.7z).Length/1MB) + " MB"
}

Write-Host "[3] provisioner (extract + installs, ~15 min)..."
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    powershell -ExecutionPolicy Bypass -File C:\coil\src_bundle\hv_provision4.ps1
}
Write-Host "[4] GL result:"
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock { Get-Content C:\coil\gl_probe_result.txt -ErrorAction SilentlyContinue }
Stop-Transcript
