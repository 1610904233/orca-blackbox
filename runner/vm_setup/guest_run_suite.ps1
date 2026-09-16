$cases = 'm3j_mixing_entry m3k_mixing_match m3l_mixing_delta m3m_mixing_filaments m3n_mixing_cancel m3o_mixing_nomodel m3p_mixing_persist m3q_mixing_view m3r_mixing_progress m3s_mixing_hover m3t_mixing_add_ratio m3u_mixing_ratio_flow m3v_mixing_cycle_input m3w_mixing_cycle_flow m3x_mixing_match m3y_mixing_gradient m3z_mixing_compat m4a_mixing_gates m4b_batch_manual m4c_mixing_panel m4d_mixing_filops m4e_mixing_paint m4f_mixing_cap64 m4g_mixing_sublayer m4h_mixing_templates m4i_mixing_slice m4j_mixing_samecolor' -split ' '
$sb = 'C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\sandboxes\vision_gui'
Set-Location $sb
New-Item -ItemType Directory -Force -Path artifacts | Out-Null
Remove-Item C:\coil\regress_summary.txt -ErrorAction SilentlyContinue
$pass=0; $_fail=0; $_failed=@()
foreach ($c in $cases) {
  "=== $c ===" | Add-Content C:\coil\regress_progress.txt
  & C:\Python311\python.exe "$c.py" > "artifacts\regress_$c.log" 2>&1
  if ($LASTEXITCODE -eq 0) { $pass++; "$c GREEN" | Add-Content C:\coil\regress_progress.txt }
  else { $_fail++; $_failed += $c; "$c RED rc=$LASTEXITCODE" | Add-Content C:\coil\regress_progress.txt }
}
"SUMMARY: PASS=$pass FAIL=$_fail" | Set-Content C:\coil\regress_summary.txt
if ($_failed) { "FAILED: $($_failed -join ' ')" | Add-Content C:\coil\regress_summary.txt }
