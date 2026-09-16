$sb = 'C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\sandboxes\vision_gui'
Set-Location $sb
Remove-Item C:\coil\regress_progress.txt,C:\coil\regress_summary.txt -ErrorAction SilentlyContinue
$cases = @('m3k_mixing_match','m3l_mixing_delta','m3m_mixing_filaments','m3n_mixing_cancel','m3p_mixing_persist','m3q_mixing_view','m3r_mixing_progress','m3s_mixing_hover','m4b_batch_manual','m4d_mixing_filops','m4g_mixing_sublayer','m4h_mixing_templates','m4i_mixing_slice','m4j_mixing_samecolor')
$pass = 0; $fail = 0; $failed = @()
foreach ($c in $cases) {
  "=== $c ===" | Add-Content C:\coil\regress_progress.txt
  & C:\Python311\python.exe "$c.py" > "artifacts\regress_$c.log" 2>&1
  if ($LASTEXITCODE -eq 0) { $pass++; "$c GREEN" | Add-Content C:\coil\regress_progress.txt }
  else { $fail++; $failed += $c; "$c RED rc=$LASTEXITCODE" | Add-Content C:\coil\regress_progress.txt }
}
"SUMMARY2: PASS=$pass FAIL=$fail" | Set-Content C:\coil\regress_summary.txt
if ($failed) { "FAILED2: $($failed -join ' ')" | Add-Content C:\coil\regress_summary.txt }
