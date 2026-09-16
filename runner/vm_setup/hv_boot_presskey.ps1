# hv_boot_presskey.ps1 — restart VM and auto-press a key at the CD/DVD boot prompt
$ErrorActionPreference = "Continue"
Start-Transcript -Path "C:\coil\vm_setup\hv_boot_presskey.log" -Force
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;using System.Runtime.InteropServices;
public class W{
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int n);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint dx,uint dy,uint d,UIntPtr e);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
 public struct RECT{public int L,T,Rt,B;}
}
'@
$vm = "win11-test"
Stop-VM -Name $vm -TurnOff -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Copy-Item "C:\Users\snapmaker\Downloads\unattend.iso" "C:\coil\vm_setup\unattend.iso" -Force
Write-Host "unattend.iso replaced with Schneegans build: $((Get-Item C:\coil\vm_setup\unattend.iso).Length) bytes"
Start-VM -Name $vm
Get-Process vmconnect -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Process vmconnect.exe -ArgumentList "localhost","$vm"
Start-Sleep -Seconds 6   # wait for VMConnect window + firmware to reach the prompt

$p = Get-Process vmconnect | Sort-Object StartTime | Select-Object -Last 1
$h = $p.MainWindowHandle
[W]::ShowWindow($h, 9) | Out-Null
[W]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 800
$rect = New-Object W+RECT
[W]::GetWindowRect($h, [ref]$rect) | Out-Null
$cx = [int](($rect.L + $rect.Rt)/2); $cy = [int](($rect.T + $rect.B)/2)
[W]::SetCursorPos($cx, $cy) | Out-Null
[W]::mouse_event(2,0,0,0,[UIntPtr]::Zero); Start-Sleep -Milliseconds 80; [W]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait(" ")
Write-Host "key sent at $(Get-Date -Format T); VM started, press-any-key satisfied"
Stop-Transcript
