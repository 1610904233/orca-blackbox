$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
$r = Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  $out = @()
  $ev = Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; StartTime=(Get-Date).Date} -MaxEvents 40 -ErrorAction SilentlyContinue
  foreach ($e in $ev) {
    $x = [xml]$e.ToXml()
    $props = @{}
    $x.Event.EventData.Data | ForEach-Object { $props[$_.Name] = $_.'#text' }
    $out += ('{0} {1} exc={2}' -f $e.TimeCreated.ToString('HH:mm'), $props['AppName'], $props['ExceptionCode'])
  }
  $out -join "`n"
}
Write-Output $r
