# make_iso.ps1 — build the Win11 setup ISO via IMAPI2 (in-box COM), with
# autounattend.xml at root + EFI El Torito boot (efisys_noprompt = no
# 'Press any key' prompt) + UDF for the split swm files.
# IMAPI2 is Microsoft's own imaging engine (same stack used to burn/author
# Windows media), so the output is first-party standard.

$ErrorActionPreference = "Stop"

$src = "C:\coil\vm_setup\iso_src"
$out = "C:\coil\vm_setup\win11-imapi.iso"
$boot = "C:\coil\vm_setup\efisys_noprompt.bin"

$fsi = New-Object -ComObject IMAPI2FS.MsftFileSystemImage
$fsi.VolumeName = "CCCOMA_X64FRE_EN-US_DV9"
# FsiFileSystemISO9660=1 | Joliet=2 | UDF=4
$fsi.FileSystemsToCreate = 7
$fsi.UDFRevision = 0x0250   # UDF 2.50 (large files)
$fsi.FreeMediaBlocks = 4200000   # ~8.6 GB (dual-layer sized)

$fsi.Root.AddTree($src, $false)

# EFI El Torito boot entry (PlatformId 0xEF, no emulation)
$adBoot = New-Object -ComObject ADODB.Stream
$adBoot.Type = 1              # binary
$adBoot.Open()
$adBoot.LoadFromFile($boot)
$bo = New-Object -ComObject IMAPI2FS.BootOptions
$bo.AssignBootImage($adBoot)
$bo.PlatformId = 0xEF         # EFI
$bo.EmulationType = 0         # no emulation
$bo.Manufacturer = "Microsoft"
$fsi.BootOptions = $bo

$result = $fsi.CreateResultImage()
Write-Host ("total blocks: " + $result.TotalBlocks)

# write IStream -> file
$istream = $result.ImageStream
$adStream = New-Object -ComObject ADODB.Stream
$adStream.Type = 1          # binary
$adStream.Open()
$istream.CopyTo($adStream)
$adStream.SaveToFile($out, 2)   # adSaveCreateOverWrite
$adStream.Close()
Write-Host ("ISO written: " + $out)
Write-Host ("size: " + (Get-Item $out).Length)
