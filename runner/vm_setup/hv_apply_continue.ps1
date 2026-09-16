# hv_apply_continue.ps1 — MUST RUN ELEVATED (admin PowerShell).
# Resumes hv_create_vm after the dism error-87 (trailing-backslash quote
# mangling). VHDX should still be attached with W:/S: letters assigned.

$ErrorActionPreference = "Stop"
Start-Transcript -Path "C:\coil\vm_setup\hv_apply_continue.log" -Force

$iso  = "C:\coil\vm_setup\Win11_25H2_English_x64.iso"
$vhdx = "C:\coil\vm_setup\win11.vhdx"
$vmName = "win11-test"

# 0) ensure vhdx attached
$attached = Get-DiskImage -ImagePath $vhdx -ErrorAction SilentlyContinue
if (-not $attached -or -not $attached.Attached) {
    Mount-VHD -Path $vhdx
    Start-Sleep -Seconds 3
}

# 1) mount ISO
$img = Get-DiskImage -ImagePath $iso
if (-not $img.Attached) {
    $img = Mount-DiskImage -ImagePath $iso -PassThru
    Start-Sleep -Seconds 3
}
$vol = ($img | Get-Volume).DriveLetter
Write-Host "ISO at ${vol}:"

# 2) pick Pro index
$images = Get-WindowsImage -ImagePath "${vol}:\sources\install.wim"
$pro = $images | Where-Object { $_.ImageName -eq "Windows 11 Pro" } | Select-Object -First 1
Write-Host "index $($pro.ImageIndex) = $($pro.ImageName)"

# 3) apply — NOTE: /ApplyDir without a trailing backslash (error-87 fix)
dism /Apply-Image "/ImageFile:${vol}:\sources\install.wim" "/ApplyIndex:$($pro.ImageIndex)" "/ApplyDir:W:"
if ($LASTEXITCODE -ne 0) { throw "dism apply failed: $LASTEXITCODE" }

# 4) boot files
bcdboot "W:\Windows" /s "S:" /f UEFI

# 5) inject unattend + bundle
New-Item -Path "W:\Windows\Panther" -ItemType Directory -Force | Out-Null
Copy-Item "C:\coil\vm_setup\autounattend.xml" "W:\Windows\Panther\unattend.xml" -Force
Copy-Item "C:\coil\vm_setup\guest_bundle.zip" "W:\guest_bundle.zip" -Force
Copy-Item "C:\coil\vm_setup\hv_provision.ps1" "W:\hv_provision.ps1" -Force

# 6) detach vhdx + iso
diskpart /s "C:\coil\vm_setup\dp_detach.txt"
Dismount-DiskImage -ImagePath $iso | Out-Null

# 7) create + start VM
if (Get-VM -Name $vmName -ErrorAction SilentlyContinue) { Remove-VM -Name $vmName -Force }
New-VM -Name $vmName -Generation 2 -MemoryStartupBytes 8GB -VHDPath $vhdx -SwitchName "Default Switch"
Set-VMProcessor -VMName $vmName -Count 4
Set-VMMemory -VMName $vmName -DynamicMemoryEnabled:$false
Enable-VMIntegrationService -VMName $vmName -Name "Guest Service Interface"
Start-VM -Name $vmName
Start-Sleep -Seconds 10
Get-VM -Name $vmName | Format-Table Name, State, CPUUsage, MemoryAssigned
Write-Host "VM CREATED AND STARTED — next: hv_orchestrate.ps1"
