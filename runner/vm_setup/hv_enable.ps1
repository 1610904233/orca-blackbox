# hv_enable.ps1 — MUST RUN ELEVATED. Stages the Hyper-V feature (NoRestart).
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All -NoRestart
Write-Host "Hyper-V staged. A restart is required to activate."
