Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class WMax {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
}
'@
$p = Get-Process vmconnect -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*localhost*" } | Select-Object -First 1
if ($p) {
  [WMax]::ShowWindow($p.MainWindowHandle, 3) | Out-Null
  Write-Output ("maximized: " + $p.MainWindowTitle)
} else {
  Write-Output "vmconnect not found"
}
