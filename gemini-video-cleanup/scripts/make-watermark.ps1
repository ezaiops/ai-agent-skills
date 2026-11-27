param(
  [Parameter(Mandatory = $true)][int]$Width,
  [Parameter(Mandatory = $true)][int]$Height,
  [Parameter(Mandatory = $true)][string]$Text,
  [ValidateSet('beige', 'dark')][string]$Style = 'beige',
  [Parameter(Mandatory = $true)][string]$OutFile
)

# Generates a rounded-corner watermark badge PNG at 4x resolution.
# The caller downscales it during overlay (lanczos) for crisp edges.
# Styles:
#   beige : warm beige fill + dark brown text (fits paper-texture videos)
#   dark  : near-black fill + white text
# The fill is fully opaque so it completely covers any underlying watermark.

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$scale = 4
$w = $Width * $scale
$h = $Height * $scale

$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$g.Clear([System.Drawing.Color]::Transparent)

$rect = New-Object System.Drawing.RectangleF(1, 1, ($w - 2), ($h - 2))
$radius = [double][math]::Max(8.0, $h * 0.22)
$d = 2 * $radius
$gp = New-Object System.Drawing.Drawing2D.GraphicsPath
$gp.AddArc($rect.X, $rect.Y, $d, $d, 180, 90)
$gp.AddArc(($rect.Right - $d), $rect.Y, $d, $d, 270, 90)
$gp.AddArc(($rect.Right - $d), ($rect.Bottom - $d), $d, $d, 0, 90)
$gp.AddArc($rect.X, ($rect.Bottom - $d), $d, $d, 90, 90)
$gp.CloseFigure()

switch ($Style) {
  'beige' {
    $fill = [System.Drawing.Color]::FromArgb(255, 231, 221, 199)
    $border = [System.Drawing.Color]::FromArgb(110, 120, 100, 70)
    $fg = [System.Drawing.Color]::FromArgb(255, 58, 49, 37)
  }
  'dark' {
    $fill = [System.Drawing.Color]::FromArgb(255, 14, 16, 22)
    $border = [System.Drawing.Color]::FromArgb(46, 255, 255, 255)
    $fg = [System.Drawing.Color]::White
  }
}

$bgBrush = New-Object System.Drawing.SolidBrush($fill)
$g.FillPath($bgBrush, $gp)
$pen = New-Object System.Drawing.Pen($border, [float][math]::Max(1.5, $h * 0.018))
$g.DrawPath($pen, $gp)

$fontPx = [int][math]::Max(8, [math]::Round($h * 0.44))
$font = $null
foreach ($name in @('Microsoft YaHei', 'SimHei', 'Microsoft JhengHei', 'Arial')) {
  try {
    $font = New-Object System.Drawing.Font($name, $fontPx, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    break
  }
  catch { }
}
if ($null -eq $font) { throw 'No usable font found.' }

$fmt = New-Object System.Drawing.StringFormat
$fmt.Alignment = [System.Drawing.StringAlignment]::Center
$fmt.LineAlignment = [System.Drawing.StringAlignment]::Center

# shrink the font if the text would overflow the badge
$maxW = $w * 0.86
$measured = $g.MeasureString($Text, $font)
if ($measured.Width -gt $maxW) {
  $newPx = [int][math]::Floor($fontPx * $maxW / $measured.Width)
  $font.Dispose()
  $font = New-Object System.Drawing.Font('Microsoft YaHei', [math]::Max(8, $newPx), [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
}

$brush = New-Object System.Drawing.SolidBrush($fg)
$g.DrawString($Text, $font, $brush, (New-Object System.Drawing.RectangleF(0, 0, $w, $h)), $fmt)

$g.Dispose()
$bmp.Save($OutFile, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output ('Watermark PNG written: {0} ({1}x{2})' -f $OutFile, $Width, $Height)
