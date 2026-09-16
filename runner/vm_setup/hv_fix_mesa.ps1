# hv_fix_mesa.ps1 — HOST, ELEVATED. Copy full mesa x64 dll set into Release dir, re-diag app.
Start-Transcript -Path "C:\coil\vm_setup\hv_fix_mesa.log" -Force
$vm = "win11-test"
$cred = New-Object System.Management.Automation.PSCredential("test", (ConvertTo-SecureString "123456" -AsPlainText -Force))
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    $rel = "C:\coil\Projects\SnapmakerOrca_dev\build\src\Release"
    Copy-Item "C:\coil\mesa\x64\*.dll" $rel -Force
    "mesa dlls in Release: " + (Get-ChildItem $rel -Filter "*.dll" | Where-Object Name -match "gallium|glapi|llvm|zlib|expat|opengl" | Measure-Object | Select-Object -ExpandProperty Count)
    $p = Start-Process "$rel\snapmaker-orca.exe" -PassThru -ArgumentList "--datadir","C:\coil\diag_datadir"
    Start-Sleep -Seconds 25
    "exited=" + $p.HasExited + " code=" + $(if ($p.HasExited) { $p.ExitCode } else { "-" })
    Get-Process | Where-Object { $_.Name -like "*orca*" } | ForEach-Object { "$($_.Id) $($_.Name) title='$($_.MainWindowTitle)' resp=$($_.Responding)" }
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
}
Stop-Transcript
