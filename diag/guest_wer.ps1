$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  '=== APPCRASH since today 00:00, by app ==='
  try {
    Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; StartTime=(Get-Date).Date} -ErrorAction Stop |
      ForEach-Object {
        $app = ($_ .Properties | Select-Object -First 1)
      }
  } catch {}
  Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; StartTime=(Get-Date).Date} -ErrorAction SilentlyContinue |
    ForEach-Object {
      $x = [xml]$_.ToXml()
      $props = @{}
      $x.Event.EventData.Data | ForEach-Object { $props[$_.Name] = $_.'#text' }
      '{0}  {1}  mod={2}  exc={3}' -f $_.TimeCreated.ToString('MM-dd HH:mm'), $props['AppName'], $props['FaultingModule'], $props['ExceptionCode']
    } | Group-Object { ($_ -split '  ')[1] } | ForEach-Object { '{0} x{1}' -f $_.Name, $_.Count; $_.Group | Select-Object -First 4 }
  '=== WER 1001 reporters ==='
  Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1001; StartTime=(Get-Date).Date} -ErrorAction SilentlyContinue |
    ForEach-Object {
      $x = [xml]$_.ToXml()
      $props = @{}
      $x.Event.EventData.Data | ForEach-Object { $props[$_.Name] = $_.'#text' }
      '{0}  {1}' -f $_.TimeCreated.ToString('MM-dd HH:mm'), $props['AppPath']
    } | Select-Object -First 12
}
