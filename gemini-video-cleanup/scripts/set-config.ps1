param(
  [Parameter(Mandatory = $true)][string]$WatermarkText
)

# Saves the per-user watermark text into config.json (next to SKILL.md).
# Script source stays pure ASCII; Chinese values are passed as arguments.
$ErrorActionPreference = 'Stop'
$configFile = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) '..\config.json'))

$obj = [ordered]@{ watermark_text = $WatermarkText }
$json = $obj | ConvertTo-Json
[System.IO.File]::WriteAllText($configFile, $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Output ('config.json saved: watermark_text = ' + $WatermarkText)