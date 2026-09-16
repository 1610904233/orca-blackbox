# hv_layout_fix.ps1 — HOST, ELEVATED. Diagnose tree, fix GL probe path, run m3j.
Start-Transcript -Path "C:\coil\vm_setup\hv_layout_fix.log" -Force
$vm = "win11-test"
$cred = New-Object System.Management.Automation.PSCredential("test", (ConvertTo-SecureString "123456" -AsPlainText -Force))

Write-Host "[1] tree layout in guest..."
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    "vision-gui-blackbox exists: " + (Test-Path 'C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox')
    if (Test-Path 'C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox') {
        Get-ChildItem 'C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox' | Select-Object -ExpandProperty Name
        if (Test-Path 'C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\sandboxes') {
            "sandboxes:"; Get-ChildItem 'C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\sandboxes' | Select-Object -First 5 -ExpandProperty Name
        }
    }
    "bx leftovers:"; Get-ChildItem C:\coil\bx -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
}

Write-Host "[2] fixed GL probe (add mesa x64 dir)..."
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    (Get-Content C:\coil\gl_probe2.py -Raw) -replace 'os\.add_dll_directory\(rel\)', 'os.add_dll_directory(rel); os.add_dll_directory(r"C:\coil\mesa\x64")' |
        Set-Content C:\coil\gl_probe2.py -Encoding UTF8
    & C:\Python311\python.exe C:\coil\gl_probe2.py 2>&1 | Tee-Object -FilePath C:\coil\gl_probe_result.txt
}
Stop-Transcript
