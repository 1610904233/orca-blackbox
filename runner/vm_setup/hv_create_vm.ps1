# hv_create_vm.ps1 — MUST RUN ELEVATED. v2: transcript logging + diskpart
# for deterministic drive letters.
$ErrorActionPreference = "Continue"
Start-Transcript -Path "C:\coil\vm_setup\hv_create_vm.log" -Force

$iso  = "C:\coil\vm_setup\Win11_25H2_English_x64.iso"
$vhdx = "C:\coil\vm_setup\win11.vhdx"
$vmName = "win11-test"

if (Test-Path $vhdx) { Remove-Item $vhdx -Force }
if (Get-VM -Name $vmName -ErrorAction SilentlyContinue) { Remove-VM -Name $vmName -Force }

Write-Host "[1] mounting ISO"
$img = Mount-DiskImage -ImagePath $iso -PassThru
$vol = ($img | Get-Volume).DriveLetter
$wim = "${vol}:\sources\install.wim"
Write-Host "  wim = $wim"

Write-Host "[2] locating 'Windows 11 Pro' index"
$images = Get-WindowsImage -ImagePath $wim
$pro = $images | Where-Object { $_.ImageName -eq "Windows 11 Pro" } | Select-Object -First 1
if (-not $pro) { $pro = $images | Where-Object { $_.ImageName -like "*Pro*" } | Select-Object -First 1 }
Write-Host "  index $($pro.ImageIndex) = $($pro.ImageName)"

Write-Host "[3] creating + attaching vhdx (diskpart)"
Set-Content -Path "C:\coil\vm_setup\dp_create.txt" -Value @"
create vdisk file="$vhdx" maximum=102400 type=expandable
select vdisk file="$vhdx"
attach vdisk
convert gpt
create partition efi size=200
format quick fs=fat32 label=System
assign letter=S
create partition msr size=16
create partition primary
format quick fs=ntfs label=Windows
assign letter=W
"@
diskpart /s "C:\coil\vm_setup\dp_create.txt"

Write-Host "[4] applying image (10-20 min)..."
dism /Apply-Image /ImageFile:"$wim" /ApplyIndex:$($pro.ImageIndex) /ApplyDir:"W:\"
if ($LASTEXITCODE -ne 0) { throw "dism apply failed: $LASTEXITCODE" }

Write-Host "[5] boot files"
bcdboot "W:\Windows" /s "S:" /f UEFI

Write-Host "[6] injecting unattend + bundle"
New-Item -Path "W:\Windows\Panther" -ItemType Directory -Force | Out-Null
Copy-Item "C:\coil\vm_setup\autounattend.xml" "W:\Windows\Panther\unattend.xml" -Force
Copy-Item "C:\coil\vm_setup\guest_bundle.zip" "W:\guest_bundle.zip" -Force
Copy-Item "C:\coil\vm_setup\hv_provision.ps1" "W:\hv_provision.ps1" -Force

Write-Host "[7] detaching vhdx + iso"
Set-Content -Path "C:\coil\vm_setup\dp_detach.txt" -Value @"
select vdisk file="$vhdx"
detach vdisk
"@
diskpart /s "C:\coil\vm_setup\dp_detach.txt"
Dismount-DiskImage -ImagePath $iso | Out-Null

Write-Host "[8] creating + starting VM"
New-VM -Name $vmName -Generation 2 -MemoryStartupBytes 8GB -VHDPath $vhdx -SwitchName "Default Switch"
Set-VMProcessor -VMName $vmName -Count 4
Set-VMMemory -VMName $vmName -DynamicMemoryEnabled:$false
Enable-VMIntegrationService -VMName $vmName -Name "Guest Service Interface"
Start-VM -Name $vmName
Start-Sleep -Seconds 10
Get-VM -Name $vmName | Format-Table Name, State, CPUUsage, MemoryAssigned
Write-Host "VM CREATED AND STARTED — run hv_orchestrate.ps1 next."
Stop-Transcript
