# hv_diag_app.ps1 — HOST, ELEVATED. Diagnose app launch in guest.
Start-Transcript -Path "C:\coil\vm_setup\hv_diag_app.log" -Force
$vm = "win11-test"
$cred = New-Object System.Management.Automation.PSCredential("test", (ConvertTo-SecureString "123456" -AsPlainText -Force))
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    "orca processes now: " + ((Get-Process | Where-Object { $_.Name -like "*orca*" -or $_.Name -like "*crashpad*" } | Select-Object Id,Name | Format-Table -AutoSize | Out-String))
    # launch app directly, wait 20s, report process + windows
    $p = Start-Process "C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe" -PassThru -ArgumentList "--datadir","C:\coil\diag_datadir"
    Start-Sleep -Seconds 20
    "after 20s: exited=" + $p.HasExited
    if ($p.HasExited) { "exit code: " + $p.ExitCode }
    $procs = Get-Process | Where-Object { $_.Name -like "*orca*" }
    foreach ($pr in $procs) { "$($pr.Id) $($pr.Name) MainWindowTitle='$($pr.MainWindowTitle)' resp=$($pr.Responding)" }
    # crash dumps?
    Get-ChildItem "$env:LOCALAPPDATA\crash*" -ErrorAction SilentlyContinue | Select-Object -First 3 FullName
    Get-ChildItem "C:\coil\Projects\SnapmakerOrca_dev\build\src\Release" -Filter "*.log" -ErrorAction SilentlyContinue | Select-Object Name,Length
}
Stop-Transcript
