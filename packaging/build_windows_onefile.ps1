$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --upgrade pip
python -m pip install -r pc_app/requirements.txt pyinstaller

if (Test-Path build_onefile) { Remove-Item build_onefile -Recurse -Force }
if (Test-Path dist_onefile) { Remove-Item dist_onefile -Recurse -Force }

python -m PyInstaller --clean --workpath build_onefile --distpath dist_onefile packaging/ets2_wheel_tool_onefile.spec

Write-Host ""
Write-Host "One-file EXE build finished."
Write-Host "Output: dist_onefile/ETS2WheelTool.exe"
