@echo off
setlocal
cd /d "%~dp0.."

python -m pip install --upgrade pip
python -m pip install -r pc_app\requirements.txt pyinstaller

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller --clean packaging\ets2_wheel_tool.spec

echo.
echo EXE build finished.
echo Output: dist\ETS2WheelTool\
endlocal
