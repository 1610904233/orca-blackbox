# hv_run_all.ps1 — the single entry point. Run from an ELEVATED PowerShell:
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   & C:\coil\vm_setup\hv_run_all.ps1
# Does: create VM (apply-image, ~15 min) -> orchestrate (wait first boot,
# provision, GL probe, smoke, snapshot, ~30 min). Logs to hv_run_all.log.

$ErrorActionPreference = "Continue"
Start-Transcript -Path "C:\coil\vm_setup\hv_run_all.log" -Force

Write-Host "===== [1/2] creating VM ====="
& "C:\coil\vm_setup\hv_create_vm.ps1"

Write-Host "===== [2/2] orchestrating (wait boot + provision + snapshot) ====="
& "C:\coil\vm_setup\hv_orchestrate.ps1"

Write-Host "===== HV RUN ALL COMPLETE ====="
Stop-Transcript
