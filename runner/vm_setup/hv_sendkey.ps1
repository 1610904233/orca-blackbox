# hv_sendkey.ps1 — elevated: activate VMConnect and send a key to the VM
# (satisfies "Press any key to boot from CD/DVD")
$ErrorActionPreference = "Continue"
Start-Transcript -Path "C:\coil\vm_setup\hv_sendkey.log" -Force
Add-Type @'
using System;using System.Runtime.InteropServices;
public class W{
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int n);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint dx,uint dy,uint d,UIntPtr e);
}
'@
$p = Get-Process vmconnect | Sort-Object StartTime | Select-Object -Last 1
$h = $p.MainWindowHandle
[W]::ShowWindow($h, 9) | Out-Null
[W]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 800
# click center of window to give the VM keyboard focus
$r = New-Object -TypeName psobject
Add-Type @'
using System;using System.Runtime.InteropServices;
public class R2{ [StructLayout(LayoutKind.Sequential)] public struct RECT{public int L,T,Rt,B;}
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);}
'@
$rect = New-Object R2+RECT
[R2]::GetWindowRect($h, [ref]$rect) | Out-Null
$cx = [int](($rect.L + $rect.Rt)/2); $cy = [int](($rect.T + $rect.B)/2)
[W]::SetCursorPos($cx, $cy) | Out-Null
[W]::mouse_event(2,0,0,0,[UIntPtr]::Zero); Start-Sleep -Milliseconds 80; [W]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait(" ")
# also send via SendInput-style keybd_event for scan-code fidelity
Add-Type -AssemblyName System.Windows.Forms
Start-Sleep -Milliseconds 300
Write-Host "key sent at $(Get-Date -Format T)"
Stop-Transcript
