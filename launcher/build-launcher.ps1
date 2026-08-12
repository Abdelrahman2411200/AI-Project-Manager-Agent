[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourcePath = Join-Path $PSScriptRoot "AIProjectManagerLauncher.cs"
$manifestPath = Join-Path $PSScriptRoot "app.manifest"
$iconPath = Join-Path $PSScriptRoot "AIProjectManager.ico"
$outputPath = Join-Path $repositoryRoot "AI Project Manager.exe"
$compilerCandidates = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)
$compilerPath = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compilerPath) {
    throw "The Windows .NET Framework C# compiler was not found. Enable .NET Framework 4.x."
}

Add-Type -AssemblyName System.Drawing
$bitmap = [System.Drawing.Bitmap]::new(256, 256)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$rectangle = [System.Drawing.Rectangle]::new(0, 0, 255, 255)
$gradient = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
    $rectangle,
    [System.Drawing.Color]::FromArgb(79, 107, 255),
    [System.Drawing.Color]::FromArgb(139, 92, 246),
    45
)
$graphics.FillRectangle($gradient, $rectangle)
$pen = [System.Drawing.Pen]::new([System.Drawing.Color]::White, 14)
$pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
$pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
$white = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
$points = @(
    [System.Drawing.Point]::new(68, 76),
    [System.Drawing.Point]::new(68, 180),
    [System.Drawing.Point]::new(144, 128),
    [System.Drawing.Point]::new(196, 180)
)
$graphics.DrawLine($pen, $points[0], $points[2])
$graphics.DrawLine($pen, $points[1], $points[2])
$graphics.DrawLine($pen, $points[2], $points[3])
foreach ($point in $points) {
    $graphics.FillEllipse($white, $point.X - 19, $point.Y - 19, 38, 38)
}
$graphics.DrawLine($pen, 192, 44, 192, 84)
$graphics.DrawLine($pen, 172, 64, 212, 64)
$iconHandle = $bitmap.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($iconHandle)
$stream = [System.IO.File]::Create($iconPath)
try {
    $icon.Save($stream)
}
finally {
    $stream.Dispose()
    $icon.Dispose()
    $white.Dispose()
    $pen.Dispose()
    $gradient.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()
}

& $compilerPath /nologo /target:winexe /optimize+ /platform:anycpu `
    "/out:$outputPath" "/win32icon:$iconPath" "/win32manifest:$manifestPath" `
    /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll `
    /reference:System.Windows.Forms.dll $sourcePath
if ($LASTEXITCODE -ne 0) {
    throw "The Windows launcher did not compile successfully."
}

$built = Get-Item -LiteralPath $outputPath
Write-Host "Built $($built.FullName) ($($built.Length) bytes)" -ForegroundColor Green
