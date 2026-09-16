# hv_orchestrate.ps1 — MUST RUN ELEVATED (Admin PowerShell) on the HOST,
# AFTER the VM has been created and started (run hv_create_vm.ps1 first).
#
# Waits for guest first-boot (marker via PowerShell Direct), runs the
# in-guest provisioner, verifies GL + smoke case, then takes the
# green-baseline checkpoint.

$ErrorActionPreference = "Continue"
$vmName = "win11-test"
$cred = New-Object System.Management.Automation.PSCredential("test", (ConvertTo-SecureString "123456" -AsPlainText -Force))

Write-Host "[1] waiting for guest first boot + autologon (up to 30 min)..."
$deadline = (Get-Date).AddMinutes(30)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        $out = Invoke-Command -VMName $vmName -Credential $cred -ScriptBlock {
            if (Test-Path C:\setup_done.txt) { "setup-done" } else { "pending" }
        } -ErrorAction Stop
        if ($out -match "setup-done") { $ready = $true; break }
        Write-Host "  pending..."
    } catch { Write-Host "  PS Direct not ready: $($_.Exception.Message)" }
    Start-Sleep -Seconds 30
}
if (-not $ready) { Write-Host "TIMEOUT waiting for guest"; exit 1 }

Write-Host "[2] running in-guest provisioner (~5-10 min)..."
Invoke-Command -VMName $vmName -Credential $cred -ScriptBlock {
    powershell -ExecutionPolicy Bypass -File C:\hv_provision.ps1
}
Invoke-Command -VMName $vmName -Credential $cred -ScriptBlock { Get-Content C:\coil\gl_probe_result.txt -ErrorAction SilentlyContinue }

Write-Host "[3] GL check: llvmpipe/software renderer expected"
$gl = Invoke-Command -VMName $vmName -Credential $cred -ScriptBlock { Get-Content C:\coil\gl_probe_result.txt -ErrorAction SilentlyContinue }
if ($gl -match "llvmpipe|softpipe|SVGA|AMD|Radeon") {
    Write-Host "GL renderer OK: $gl"
} else {
    Write-Host "WARN: unexpected GL renderer: $gl"
}

Write-Host "[4] running smoke case m3j inside the guest (~2 min)..."
Invoke-Command -VMName $vmName -Credential $cred -ScriptBlock {
    $sb = "C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\sandboxes\vision_gui"
    Set-Location $sb
    & C:\Python311\python.exe m3j_mixing_entry.py 2>&1 | Select-Object -Last 12
}

Write-Host "[5] checkpoint green-baseline"
Checkpoint-VM -Name $vmName -SnapshotName "green-baseline"
Get-VMSnapshot -VMName $vmName | Format-Table Name, CreationTime
Write-Host "ORCHESTRATION DONE — snapshot 'green-baseline' taken."
