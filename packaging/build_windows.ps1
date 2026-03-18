$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --upgrade pip
python -m pip install -r pc_app/requirements.txt pyinstaller

if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist) { Remove-Item dist -Recurse -Force }

python -m PyInstaller --clean packaging/ets2_wheel_tool.spec

Write-Host ""
Write-Host "EXE build finished."
Write-Host "Output: dist/ETS2WheelTool/"
