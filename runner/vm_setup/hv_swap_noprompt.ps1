$vm = "win11-test"
Stop-VM -Name $vm -TurnOff -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
# 移除两个旧光驱
Get-VMDvdDrive -VMName $vm | Remove-VMDvdDrive
# 挂载重制的 noprompt 一体化 ISO
Add-VMDvdDrive -VMName $vm -Path "C:\coil\vm_setup\win11-setup.iso"
# 设为首选启动设备
Set-VMFirmware -VMName $vm -FirstBootDevice (Get-VMDvdDrive -VMName $vm)
Start-VM -Name $vm
Get-VM -Name $vm | Format-Table Name, State, CPUUsage
Write-Host "Booting noprompt media - install is now fully unattended."
