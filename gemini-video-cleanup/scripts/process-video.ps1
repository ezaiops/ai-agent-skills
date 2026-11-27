param(
  [Parameter(Mandatory = $true)][string]$Path,
  [switch]$Recurse,
  [string]$Srt = '',
  [ValidateSet('auto', 'on', 'off')][string]$Subtitles = 'auto',
  [string]$WatermarkText = '',
  [ValidateSet('beige', 'dark')][string]$WatermarkStyle = 'beige',
  [int]$SubtitleFontSize = 40,
  [string]$SubtitleColor = '&H0000E0FF',
  [int]$SubtitleMarginBottom = 14,
  [string]$OutputDir = '',
  [double]$TrimSeconds = -1,
  [double]$EndScanSeconds = 15,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Output sub-folder name "cheng pian" (finished videos), kept ASCII in source on purpose.
$OUT_FOLDER_NAME = [string][char]0x6210 + [char]0x7247

# ---- per-user watermark text (first-use gate) ----
# The skill does not hard-code any user's brand text. If no -WatermarkText is
# given, it is read from config.json (next to SKILL.md). If still empty, we
# stop with instructions so the caller configures their own watermark first.
$configFile = Join-Path (Split-Path -Parent $scriptDir) 'config.json'
if ($WatermarkText -eq '') {
  if (Test-Path -LiteralPath $configFile) {
    try {
      $cfg = Get-Content -Raw -Encoding UTF8 -LiteralPath $configFile | ConvertFrom-Json
      if ($null -ne $cfg -and $null -ne $cfg.watermark_text) {
        $cfgText = ([string]$cfg.watermark_text).Trim()
        if ($cfgText -ne '') { $WatermarkText = $cfgText }
      }
    }
    catch { }
  }
}
if ($WatermarkText -eq '') {
  Write-Host ''
  Write-Host '[INFO] Watermark text is not configured yet (first use of this skill).' -ForegroundColor Yellow
  Write-Host '  Configure it once and re-run:'
  Write-Host ('    powershell -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $scriptDir 'set-config.ps1') + '" -WatermarkText "<YOUR BRAND TEXT>"')
  Write-Host '  Or pass -WatermarkText directly on the command line.'
  Write-Host ''
  exit 2
}

function Resolve-Tool([string]$preferred, [string]$fallback) {
  if (Test-Path -LiteralPath $preferred) { return $preferred }
  return $fallback
}
$FFMPEG = Resolve-Tool 'C:\ffmpeg\bin\ffmpeg.exe' 'ffmpeg'
$FFPROBE = Resolve-Tool 'C:\ffmpeg\bin\ffprobe.exe' 'ffprobe'

function Get-Probe([string]$file) {
  $raw = & $FFPROBE -v error -print_format json -show_format -show_streams $file 2>$null
  if (-not $raw) { throw "ffprobe failed for: $file" }
  return (($raw | Out-String) | ConvertFrom-Json)
}

function Get-Fps($probe) {
  $stream = $probe.streams | Where-Object { $_.codec_type -eq 'video' } | Select-Object -First 1
  $expr = $stream.avg_frame_rate
  if (-not $expr -or $expr -eq '0/0') { $expr = $stream.r_frame_rate }
  if ($expr -match '^(\d+)/(\d+)$' -and [double]$matches[2] -gt 0) {
    return ([double]$matches[1] / [double]$matches[2])
  }
  return 25.0
}

function Find-SrtFor([string]$videoFile) {
  $dir = Split-Path -Parent $videoFile
  $base = [IO.Path]::GetFileNameWithoutExtension($videoFile)
  $srts = @(Get-ChildItem -LiteralPath $dir -Filter '*.srt' -File -ErrorAction SilentlyContinue)
  foreach ($f in $srts) {
    if ($f.BaseName -eq $base) { return $f.FullName }
  }
  foreach ($f in $srts) {
    if ($f.BaseName.StartsWith($base + ' (transcribed', [System.StringComparison]::OrdinalIgnoreCase)) {
      return $f.FullName
    }
  }
  return ''
}

function Get-SrtEnd([string]$srtPath) {
  $raw = Get-Content -Raw -Encoding UTF8 -LiteralPath $srtPath
  $ms = [regex]::Matches($raw, '(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*')
  if ($ms.Count -eq 0) { return -1.0 }
  $m = $ms[$ms.Count - 1]
  return ([int]$m.Groups[1].Value * 3600 + [int]$m.Groups[2].Value * 60 + [int]$m.Groups[3].Value + [int]$m.Groups[4].Value / 1000.0)
}

# Detect the start of the trailing end-card (Gemini Notebook logo card).
# Two templates exist: white card (YAVG >= 215) and dark card
# (YAVG <= 58 with no true black, i.e. YMIN >= 10). We scan the last
# EndScanSeconds and find the run of "card-like" frames that extends to
# the end of the video; a brightness step at the run start guards against
# mistaking a dark content scene for a card. Returns the full duration when
# no end card is found.
function Find-EndCardStart([string]$file, [double]$duration, [double]$fps) {
  $window = [math]::Min($EndScanSeconds, $duration)
  if ($window -lt 2 -or $duration -le 0) { return $duration }
  $start = $duration - $window
  $ffArgs = @(
    '-v', 'error', '-nostdin',
    '-ss', $start.ToString('0.###', [System.Globalization.CultureInfo]::InvariantCulture),
    '-i', $file,
    '-vf', 'signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-,metadata=print:key=lavfi.signalstats.YMIN:file=-',
    '-an', '-f', 'null', '-'
  )
  $out = (& $FFMPEG @ffArgs 2>$null | Out-String)

  $frames = @{}
  $cur = -1.0
  foreach ($line in ($out -split "`r?`n")) {
    if ($line -match 'pts_time:([0-9]+(?:\.[0-9]+)?)') {
      $cur = [math]::Round([double]$matches[1], 3)
      if (-not $frames.ContainsKey($cur)) { $frames[$cur] = @{ Avg = $null; Min = $null } }
    }
    elseif ($line -match 'YAVG=([0-9]+(?:\.[0-9]+)?)' -and $cur -ge 0) {
      if (-not $frames.ContainsKey($cur)) { $frames[$cur] = @{ Avg = $null; Min = $null } }
      $frames[$cur].Avg = [double]$matches[1]
    }
    elseif ($line -match 'YMIN=([0-9]+(?:\.[0-9]+)?)' -and $cur -ge 0) {
      if (-not $frames.ContainsKey($cur)) { $frames[$cur] = @{ Avg = $null; Min = $null } }
      $frames[$cur].Min = [double]$matches[1]
    }
  }

  $keys = @($frames.Keys | Sort-Object)
  $times = @()
  $yavg = @()
  $ymin = @()
  foreach ($k in $keys) {
    if ($null -ne $frames[$k].Avg -and $null -ne $frames[$k].Min) {
      $times += [double]$k
      $yavg += $frames[$k].Avg
      $ymin += $frames[$k].Min
    }
  }
  $n = $times.Count
  if ($n -lt 5) { return $duration }

  $cardLike = New-Object bool[] $n
  for ($i = 0; $i -lt $n; $i++) {
    $cardLike[$i] = (($yavg[$i] -ge 215.0) -or (($yavg[$i] -le 58.0) -and ($ymin[$i] -ge 10.0)))
  }

  $runStart = $n
  for ($i = ($n - 1); $i -ge 0; $i--) {
    if ($cardLike[$i]) { $runStart = $i } else { break }
  }
  if ($runStart -ge $n -or $runStart -le 0) { return $duration }

  $runDur = $times[$n - 1] - $times[$runStart]
  if ($runDur -lt 0.8) { return $duration }

  $step = [math]::Abs($yavg[$runStart - 1] - $yavg[$runStart])
  if ($step -lt 12.0) { return $duration }

  $frameDur = 1.0 / $fps
  $cut = $start + $times[$runStart] - $frameDur
  if ($cut -lt 0) { $cut = 0 }
  return $cut
}

function Get-WatermarkLayout([int]$w, [int]$h) {
  $portrait = $h -gt $w
  if ($portrait) {
    $s = $w / 720.0
    $bw = [int][math]::Round(178 * $s)
    $bh = [int][math]::Round(34 * $s)
    $bx = $w - $bw - [int][math]::Round(20 * $s)
    $by = $h - $bh - [int][math]::Round(18 * $s)
  }
  else {
    $s = $w / 1280.0
    $bw = [int][math]::Round(142 * $s)
    $bh = [int][math]::Round(34 * $s)
    $bx = $w - $bw - [int][math]::Round(4 * $s)
    $by = $h - $bh
  }
  return @{ Width = $bw; Height = $bh; X = $bx; Y = $by }
}

function Process-VideoFile([string]$videoFile) {
  $probe = Get-Probe $videoFile
  $stream = $probe.streams | Where-Object { $_.codec_type -eq 'video' } | Select-Object -First 1
  if (-not $stream) { throw "No video stream: $videoFile" }
  $w = [int]$stream.width
  $h = [int]$stream.height
  $duration = [double]$probe.format.duration
  $fps = Get-Fps $probe
  $portrait = $h -gt $w

  $srtPath = ''
  if ($Srt -ne '') {
    if (-not (Test-Path -LiteralPath $Srt)) { throw "SRT not found: $Srt" }
    $srtPath = $Srt
  }
  else {
    $srtPath = Find-SrtFor $videoFile
  }

  $srtEnd = -1.0
  if ($srtPath -ne '') { $srtEnd = Get-SrtEnd $srtPath }
  $srtRatio = 0.0
  if ($srtEnd -gt 0 -and $duration -gt 0) { $srtRatio = $srtEnd / $duration }

  $burn = $false
  if ($Subtitles -eq 'on') {
    $burn = ($srtPath -ne '')
  }
  elseif ($Subtitles -eq 'auto') {
    $burn = ($srtPath -ne '') -and (-not $portrait) -and ($srtRatio -ge 0.85) -and ($srtRatio -le 1.18)
  }

  $cut = $duration
  if ($TrimSeconds -gt 0) {
    $cut = [math]::Min($TrimSeconds, $duration)
  }
  else {
    $autoCut = Find-EndCardStart $videoFile $duration $fps
    if ($duration -gt 30 -and $autoCut -lt ($duration * 0.6)) {
      Write-Warning ('Auto cut {0:N2}s looks too early for a {1:N1}s video; keeping full length. Use -TrimSeconds to force.' -f $autoCut, $duration)
      $cut = $duration
    }
    else {
      $cut = $autoCut
    }
  }

  $outRoot = ''
  if ($OutputDir -ne '') { $outRoot = $OutputDir }
  else { $outRoot = Join-Path (Split-Path -Parent $videoFile) $OUT_FOLDER_NAME }
  $outFile = Join-Path $outRoot ([IO.Path]::GetFileName($videoFile))

  $tmp = Join-Path ([IO.Path]::GetTempPath()) ('vc_' + [guid]::NewGuid().ToString('N').Substring(0, 10))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null

  try {
    $wmPng = ''
    $layout = $null
    if ($WatermarkText -ne '') {
      $layout = Get-WatermarkLayout $w $h
      $wmPng = Join-Path $tmp 'wm.png'
      & (Join-Path $scriptDir 'make-watermark.ps1') -Width $layout.Width -Height $layout.Height -Text $WatermarkText -Style $WatermarkStyle -OutFile $wmPng | Out-Null
    }

    $assFile = ''
    if ($burn) {
      $assFile = Join-Path $tmp 'sub.ass'
      & (Join-Path $scriptDir 'srt-to-ass.ps1') -SrtPath $srtPath -OutFile $assFile -VideoWidth $w -VideoHeight $h -BaseFontSize $SubtitleFontSize -TextColor $SubtitleColor -MarginBottom $SubtitleMarginBottom | Out-Null
    }

    $filters = @()
    $baseLabel = '0:v'
    if ($burn) {
      $filters += '[0:v]subtitles=sub.ass[v0]'
      $baseLabel = 'v0'
    }
    if ($wmPng -ne '') {
      $filters += ('[1:v]scale={0}:{1}:flags=lanczos[wmk]' -f $layout.Width, $layout.Height)
      $filters += ('[{0}][wmk]overlay={1}:{2}[v]' -f $baseLabel, $layout.X, $layout.Y)
      $outLabel = 'v'
    }
    else {
      $outLabel = $baseLabel
    }

    $filterFile = ''
    if ($filters.Count -gt 0) {
      $filterFile = Join-Path $tmp 'filter.txt'
      [IO.File]::WriteAllText($filterFile, ($filters -join ";`n"), (New-Object System.Text.UTF8Encoding($false)))
    }

    $boxInfo = ''
    if ($layout) { $boxInfo = '{0}x{1}@{2},{3}' -f $layout.Width, $layout.Height, $layout.X, $layout.Y }

    $plan = [pscustomobject]@{
      File           = $videoFile
      Resolution     = ('{0}x{1}' -f $w, $h)
      DurationSec    = [math]::Round($duration, 2)
      Srt            = $srtPath
      SrtRatio       = [math]::Round($srtRatio, 3)
      BurnSubtitles  = $burn
      CutAtSec       = [math]::Round($cut, 3)
      Watermark      = $WatermarkText
      WatermarkStyle = $WatermarkStyle
      WatermarkBox   = $boxInfo
      Output         = $outFile
      Mode           = $(if ($DryRun) { 'DRY-RUN' } else { 'RENDER' })
    }

    if ($DryRun) { return $plan }

    New-Item -ItemType Directory -Force -Path $outRoot | Out-Null
    Write-Host ('Rendering: {0} -> {1}' -f (Split-Path -Leaf $videoFile), $outFile)

    $ffArgs = @('-y', '-v', 'warning', '-stats', '-i', $videoFile)
    if ($wmPng -ne '') { $ffArgs += @('-i', 'wm.png') }
    if ($filterFile -ne '') {
      $ffArgs += @('-filter_complex_script', $filterFile)
      $ffArgs += @('-map', "[$outLabel]")
    }
    else {
      $ffArgs += @('-map', '0:v')
    }
    $ffArgs += @('-map', '0:a?')
    $ffArgs += @('-t', $cut.ToString('0.###', [System.Globalization.CultureInfo]::InvariantCulture))
    $ffArgs += @('-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p')
    $ffArgs += @('-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', $outFile)

    Push-Location $tmp
    try {
      $prevEap = $ErrorActionPreference
      $ErrorActionPreference = 'Continue'
      try {
        & $FFMPEG @ffArgs 2>$null | Out-Null
        $exitCode = $LASTEXITCODE
      }
      finally {
        $ErrorActionPreference = $prevEap
      }
    }
    finally {
      Pop-Location
    }
    if ($exitCode -ne 0) { throw ("ffmpeg exited with code {0} for: {1}" -f $exitCode, $videoFile) }
    if (-not (Test-Path -LiteralPath $outFile)) { throw "Render failed: $outFile" }
    $plan | Add-Member -NotePropertyName OutputSizeMB -NotePropertyValue ([math]::Round((Get-Item -LiteralPath $outFile).Length / 1MB, 2))
    return $plan
  }
  finally {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }
  }
}

# ---------------- main ----------------
$results = @()
if (Test-Path -LiteralPath $Path -PathType Container) {
  $excludePattern = '[\\/]' + [regex]::Escape($OUT_FOLDER_NAME) + '[\\/]'
  $videoFiles = @(Get-ChildItem -LiteralPath $Path -Filter '*.mp4' -File -Recurse:$Recurse |
    Where-Object { $_.FullName -notmatch $excludePattern } |
    Sort-Object FullName)
  if ($videoFiles.Count -eq 0) { throw "No .mp4 files found in: $Path" }
  $i = 0
  foreach ($f in $videoFiles) {
    $i++
    Write-Host ('[{0}/{1}] {2}' -f $i, $videoFiles.Count, $f.Name) -ForegroundColor Cyan
    $results += Process-VideoFile $f.FullName
  }
}
else {
  $results += Process-VideoFile $Path
}
$results | Format-List
