# hv_diag_panther2.ps1 — ELEVATED. Setup UI is up now; send Shift+F10 + notepad now.
$ErrorActionPreference = "Continue"
Start-Transcript -Path "C:\coil\vm_setup\hv_diag_panther2.log" -Force
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;using System.Runtime.InteropServices;
public class W{
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
 public struct RECT{public int L,T,Rt,B;}
}
'@
$p = Get-Process vmconnect | Sort-Object StartTime | Select-Object -Last 1
$h = $p.MainWindowHandle
[W]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 800
[System.Windows.Forms.SendKeys]::SendWait("+{F10}")
Start-Sleep -Seconds 5
[System.Windows.Forms.SendKeys]::SendWait("notepad X:\Windows\Panther\setuperr.log{ENTER}")
Write-Host "sent $(Get-Date -Format T)"
Start-Sleep -Seconds 4
Stop-Transcript
