# hv_fix_tree_smoke.ps1 — HOST, ELEVATED. Flatten wb into vision-gui-blackbox, run m3j.
Start-Transcript -Path "C:\coil\vm_setup\hv_fix_tree_smoke.log" -Force
$vm = "win11-test"
$cred = New-Object System.Management.Automation.PSCredential("test", (ConvertTo-SecureString "123456" -AsPlainText -Force))
$wt = "C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox"

Write-Host "[1] flattening tree..."
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($wt)
    $wb = "$wt\wb"
    if (Test-Path $wb) {
        # empty sandboxes placeholder at destination -> remove, then move real one up
        if ((Test-Path "$wt\sandboxes") -and -not (Get-ChildItem "$wt\sandboxes" -Recurse -File)) { Remove-Item "$wt\sandboxes" -Recurse -Force }
        Get-ChildItem $wb | ForEach-Object { Move-Item $_.FullName $wt -Force }
        Remove-Item $wb -Recurse -Force
    }
    "vision_gui sandbox: " + (Test-Path "$wt\sandboxes\vision_gui\m3j_mixing_entry.py")
    "resources: " + (Test-Path "$wt\resources")
    "tests: " + (Test-Path "$wt\tests")
} -ArgumentList $wt

Write-Host "[2] m3j smoke (~2-5 min)..."
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($wt)
    Set-Location "$wt\sandboxes\vision_gui"
    & C:\Python311\python.exe m3j_mixing_entry.py 2>&1 | Select-Object -Last 20
} -ArgumentList $wt
Stop-Transcript
