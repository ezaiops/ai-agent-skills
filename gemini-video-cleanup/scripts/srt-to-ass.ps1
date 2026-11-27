param(
  [Parameter(Mandatory = $true)][string]$SrtPath,
  [Parameter(Mandatory = $true)][string]$OutFile,
  [Parameter(Mandatory = $true)][int]$VideoWidth,
  [Parameter(Mandatory = $true)][int]$VideoHeight,
  [string]$FontName = 'Microsoft YaHei',
  [int]$MaxChars = 20,
  [int]$HardSplit = 26,
  [double]$MinDuration = 0.85,
  [int]$BaseFontSize = 40,
  [int]$MarginBottom = 14,
  [string]$TextColor = '&H0000E0FF'
)

# Converts an SRT file to an ASS subtitle file for burning.
# Long paragraph-style cues are re-segmented at punctuation, keeping each cue
# at MaxChars or less, and the cue duration is distributed by character count.
# Style scales with video height (BaseFontSize is defined for 720p).

$ErrorActionPreference = 'Stop'

$fontSize = [int][math]::Round($BaseFontSize * $VideoHeight / 720.0)
$marginV = [int][math]::Round($MarginBottom * $VideoHeight / 720.0)
$marginLR = [int][math]::Round(40 * $VideoWidth / 1280.0)
$outline = [math]::Max(2.0, [math]::Round(2.5 * $VideoHeight / 720.0, 1))
$shadow = [math]::Max(1, [math]::Round(1.5 * $VideoHeight / 720.0, 1))

$raw = Get-Content -Raw -Encoding UTF8 -LiteralPath $SrtPath
$raw = $raw -replace "`r`n", "`n" -replace "`r", "`n"
$raw = $raw.TrimStart([char]0xFEFF)
$blocks = ($raw -split "`n`n") | Where-Object { $_.Trim() -ne '' }

$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine('[Script Info]')
[void]$sb.AppendLine('ScriptType: v4.00+')
[void]$sb.AppendLine(('PlayResX: {0}' -f $VideoWidth))
[void]$sb.AppendLine(('PlayResY: {0}' -f $VideoHeight))
[void]$sb.AppendLine('WrapStyle: 0')
[void]$sb.AppendLine('ScaledBorderAndShadow: yes')
[void]$sb.AppendLine('')
[void]$sb.AppendLine('[V4+ Styles]')
[void]$sb.AppendLine('Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding')
[void]$sb.AppendLine(('Style: Default,{0},{1},{6},&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{2},{3},2,{4},{4},{5},1' -f $FontName, $fontSize, $outline, $shadow, $marginLR, $marginV, $TextColor))
[void]$sb.AppendLine('')
[void]$sb.AppendLine('[Events]')
[void]$sb.AppendLine('Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text')

function Parse-Time([string]$t) {
  if ($t -match '(\d+):(\d+):(\d+)[,.](\d+)') {
    return ([int]$matches[1] * 3600 + [int]$matches[2] * 60 + [int]$matches[3] + [int]$matches[4] / 1000.0)
  }
  return -1.0
}

function Format-AssTime([double]$sec) {
  $h = [math]::Floor($sec / 3600)
  $m = [math]::Floor(($sec % 3600) / 60)
  $s = [math]::Floor($sec % 60)
  $cs = [math]::Round(($sec - [math]::Floor($sec)) * 100)
  if ($cs -ge 100) { $cs = 99 }
  return ('{0}:{1:00}:{2:00}.{3:00}' -f $h, $m, $s, $cs)
}

function Text-Len([string]$s) {
  return ($s -replace '[\p{P}\p{S}\s]', '').Length
}

function Split-Tokens([string]$text) {
  $ms = [regex]::Matches($text, '[^\p{P}\s]+[\p{P}]*')
  $r = @()
  foreach ($m in $ms) {
    $v = $m.Value.Trim()
    if ($v -ne '') { $r += $v }
  }
  return $r
}

function Segments-FromText([string]$text) {
  $tokens = @(Split-Tokens $text)
  if ($tokens.Count -eq 0) { return @() }
  $tk2 = @()
  foreach ($t in $tokens) {
    if ($t.Length -gt $HardSplit) {
      $rest = $t
      while ($rest.Length -gt $MaxChars) {
        $tk2 += $rest.Substring(0, $MaxChars)
        $rest = $rest.Substring($MaxChars)
      }
      if ($rest -ne '') { $tk2 += $rest }
    }
    else {
      $tk2 += $t
    }
  }
  $segs = @()
  $cur = ''
  foreach ($t in $tk2) {
    if ($cur -eq '') { $cur = $t; continue }
    $joined = $cur + $t
    if ((Text-Len $joined) -le $MaxChars) { $cur = $joined }
    else {
      $segs += $cur
      $cur = $t
    }
  }
  if ($cur -ne '') { $segs += $cur }
  return $segs
}

$count = 0
foreach ($b in $blocks) {
  $lines = $b -split "`n"
  $ti = -1
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '-->') { $ti = $i; break }
  }
  if ($ti -lt 0) { continue }
  $parts = $lines[$ti] -split '-->'
  $st = Parse-Time $parts[0]
  $en = Parse-Time $parts[1]
  if ($st -lt 0 -or $en -le $st) { continue }

  $textLines = @()
  for ($i = $ti + 1; $i -lt $lines.Count; $i++) {
    if ($lines[$i].Trim() -ne '') { $textLines += $lines[$i].Trim() }
  }
  if ($textLines.Count -eq 0) { continue }

  $fullText = ($textLines -join '')
  $segs = @(Segments-FromText $fullText)
  if ($segs.Count -eq 0) { continue }

  $weights = @()
  foreach ($s in $segs) { $weights += [math]::Max(1, (Text-Len $s)) }
  $wsum = ($weights | Measure-Object -Sum).Sum
  $total = $en - $st
  $minDur = $MinDuration
  if ($total -lt ($minDur * $segs.Count)) {
    $minDur = [math]::Max(0.35, $total / ($segs.Count * 1.2))
  }
  $durs = @()
  foreach ($wt in $weights) { $durs += [math]::Max($minDur, $total * $wt / $wsum) }
  $dsum = ($durs | Measure-Object -Sum).Sum

  $clock = $st
  for ($k = 0; $k -lt $segs.Count; $k++) {
    $d = $durs[$k] * $total / $dsum
    $a = $clock
    $bEnd = [math]::Min($en, $clock + $d)
    if ($k -eq ($segs.Count - 1)) { $bEnd = $en }
    $lineText = ($segs[$k]) -replace '[{}]', ''
    [void]$sb.AppendLine(('Dialogue: 0,{0},{1},Default,,0,0,0,,{2}' -f (Format-AssTime $a), (Format-AssTime $bEnd), $lineText))
    $clock = $bEnd
    $count++
    if ($clock -ge $en) { break }
  }
}

[System.IO.File]::WriteAllText($OutFile, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
Write-Output ('ASS written: {0} ({1} cues)' -f $OutFile, $count)
