# relay.ps1 — ELEVATED, PERSISTENT. Watches for C:\coil\vm_setup\relay_cmd.txt,
# executes it as PowerShell, writes output to relay_out.txt, then deletes the cmd.
# Stop by creating relay_stop.txt.
Set-Location C:\coil\vm_setup
"relay up $(Get-Date -Format T)" | Set-Content relay_alive.txt
while ($true) {
    if (Test-Path C:\coil\vm_setup\relay_stop.txt) { "relay stopped" | Add-Content relay_alive.txt; break }
    if (Test-Path C:\coil\vm_setup\relay_cmd.txt) {
        $cmd = Get-Content C:\coil\vm_setup\relay_cmd.txt -Raw
        Remove-Item C:\coil\vm_setup\relay_cmd.txt -Force
        "=== RUN $(Get-Date -Format T) ===" | Set-Content relay_out.txt
        try {
            $out = Invoke-Expression $cmd 2>&1 | Out-String
            $out | Add-Content relay_out.txt
        } catch {
            "ERROR: $($_.Exception.Message)" | Add-Content relay_out.txt
        }
        "=== DONE $(Get-Date -Format T) ===" | Add-Content relay_out.txt
        Get-Date -Format T | Set-Content relay_alive.txt
    }
    Start-Sleep -Milliseconds 700
}
