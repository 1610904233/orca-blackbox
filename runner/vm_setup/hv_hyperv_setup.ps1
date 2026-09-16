# hv_hyperv_setup.ps1 - MUST RUN ELEVATED.
# Creates the Gen2 VM that boots from the Win11 ISO (media's own DISM does
# the install -> no host DISM format limits). The user presses ONE key at
# the media's 'Press any key' prompt in the VM console; autounattend.xml
# (on the second DVD) drives everything after that.

$ErrorActionPreference = "Stop"
$vm = "win11-test"

if (Get-VM -Name $vm -ErrorAction SilentlyContinue) { Remove-VM -Name $vm -Force }
if (Test-Path "C:\coil\vm_setup\win11.vhdx") { Remove-Item "C:\coil\vm_setup\win11.vhdx" -Force }

New-VM -Name $vm -MemoryStartupBytes 8GB -Generation 2 `
    -NewVHDPath "C:\coil\vm_setup\win11.vhdx" -NewVHDSizeBytes 127GB `
    -SwitchName "Default Switch"
Set-VMProcessor -VMName $vm -Count 4
Set-VMMemory -VMName $vm -DynamicMemoryEnabled:$false

Add-VMDvdDrive -VMName $vm -Path "C:\coil\vm_setup\Win11_25H2_English_x64.iso"
Add-VMDvdDrive -VMName $vm -Path "C:\coil\vm_setup\unattend.iso"

# boot from the FIRST dvd (the Win11 setup media)
$dvd = Get-VMDvdDrive -VMName $vm | Where-Object { $_.Path -like "*Win11_25H2*" }
Set-VMFirmware -VMName $vm -FirstBootDevice $dvd

Enable-VMIntegrationService -VMName $vm -Name "Guest Service Interface"

Start-VM -Name $vm
Start-Sleep -Seconds 5
Get-VM -Name $vm | Format-Table Name, State, CPUUsage, MemoryAssigned
Write-Host "VM RUNNING - open the console in Hyper-V Manager and press a key at the 'Press any key' prompt."
