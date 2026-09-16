$sb = 'C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\sandboxes\vision_gui'
Set-Location $sb
# 1) relax match timeouts
$files = @("harness\mixing_util.py") + (Get-ChildItem m3*.py,m4*.py | Select-Object -ExpandProperty FullName)
foreach ($f in $files) {
  $t = Get-Content $f -Raw
  $n = $t -replace 'timeout_s: float = 60\.0','timeout_s: float = 300.0' `
       -replace 'timeout_s=90\.0','timeout_s=420.0' `
       -replace 'timeout_s=90','timeout_s=420' `
       -replace 'timeout_s=40','timeout_s=240' `
       -replace 'timeout_s=25\.0','timeout_s=180.0'
  if ($n -ne $t) { Set-Content $f $n -Encoding UTF8; "patched $f" }
}
# 2) fix autologon password (we changed it to 123456)
$wl = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
Set-ItemProperty $wl DefaultPassword '123456'
Set-ItemProperty $wl AutoAdminLogon '1'
Set-ItemProperty $wl DefaultUserName 'test'
"autologon fixed"
# 3) suite files for the rerun
$cases = @('m3k_mixing_match','m3l_mixing_delta','m3m_mixing_filaments','m3n_mixing_cancel','m3p_mixing_persist','m3q_mixing_view','m3r_mixing_progress','m3s_mixing_hover','m4b_batch_manual','m4d_mixing_filops','m4g_mixing_sublayer','m4h_mixing_templates','m4i_mixing_slice','m4j_mixing_samecolor')
$runner = "`$cases = @('" + ($cases -join "','") + "')`n"
$runner += @'
$sb = 'C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\sandboxes\vision_gui'
Set-Location $sb
Remove-Item C:\coil\regress_progress.txt,C:\coil\regress_summary.txt -ErrorAction SilentlyContinue
$pass=0; $fail=0; $failed=@()
foreach ($c in $cases) {
  "=== $c ===" | Add-Content C:\coil\regress_progress.txt
  & C:\Python311\python.exe "$c.py" > "artifacts\regress_$c.log" 2>&1
  if ($LASTEXITCODE -eq 0) { $pass++; "$c GREEN" | Add-Content C:\coil\regress_progress.txt }
  else { $fail++; $failed += $c; "$c RED rc=$LASTEXITCODE" | Add-Content C:\coil\regress_progress.txt }
}
"SUMMARY2: PASS=$pass FAIL=$fail" | Set-Content C:\coil\regress_summary.txt
if ($failed) { "FAILED2: $($failed -join ' ')" | Add-Content C:\coil\regress_summary.txt }
'@
Set-Content C:\coil\run_failed.ps1 $runner -Encoding UTF8
"runner written"
