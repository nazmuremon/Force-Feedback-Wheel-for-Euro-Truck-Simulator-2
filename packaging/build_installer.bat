@echo off
setlocal
cd /d "%~dp0.."

if not exist dist\ETS2WheelTool\ETS2WheelTool.exe (
    echo EXE build not found. Run packaging\build_windows.bat first.
    exit /b 1
)

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not exist "%ISCC%" (
    echo Inno Setup 6 not found.
    echo Install it from https://jrsoftware.org/isinfo.php and run this script again.
    exit /b 1
)

"%ISCC%" packaging\ets2_wheel_tool.iss

echo.
echo Installer build finished.
echo Output: dist_installer\ETS2WheelToolSetup.exe
endlocal
