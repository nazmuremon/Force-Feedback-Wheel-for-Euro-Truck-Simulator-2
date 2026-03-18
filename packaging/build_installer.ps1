$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path "dist/ETS2WheelTool/ETS2WheelTool.exe")) {
    throw "EXE build not found. Run packaging/build_windows.ps1 first."
}

$candidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)

$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 not found. Install it from https://jrsoftware.org/isinfo.php"
}

& $iscc "packaging/ets2_wheel_tool.iss"

Write-Host ""
Write-Host "Installer build finished."
Write-Host "Output: dist_installer/ETS2WheelToolSetup.exe"
