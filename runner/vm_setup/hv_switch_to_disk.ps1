# hv_switch_to_disk.ps1 — run in ELEVATED PowerShell, DURING setup's "Installing" phase
# (while the VHDX is already populated enough to boot). Switches first boot device to HDD
# so the post-install reboot goes to disk instead of re-running DVD setup (infinite reinstall loop).
Start-Transcript -Path "C:\coil\vm_setup\hv_switch_to_disk.log" -Force
Stop-VM win11-test -TurnOff -Force
Start-Sleep -Seconds 3
Set-VMFirmware -VMName win11-test -FirstBootDevice (Get-VMHardDiskDrive -VMName win11-test)
Start-VM -Name win11-test
Start-Sleep -Seconds 5
Get-VM win11-test | Format-Table Name,State,CPUUsage
(Get-VMFirmware -VMName win11-test).FirstBootDevice | Format-List BootType
Stop-Transcript
