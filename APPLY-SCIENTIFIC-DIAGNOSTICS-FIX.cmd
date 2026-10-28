@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "%~dp0SCIENTIFIC-FIX\apply.ps1" (
    echo ERROR: SCIENTIFIC-FIX\apply.ps1 is missing.
    echo Extract this ZIP directly into the SQE-Studio installation folder.
    pause
    exit /b 1
)
rem Do not pass a quoted ProjectRoot ending in a backslash to PowerShell.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SCIENTIFIC-FIX\apply.ps1"
if errorlevel 1 (
    echo.
    echo Hotfix could not be applied. See the error above.
    pause
    exit /b 1
)
echo.
echo Hotfix completed. Restart SQE Studio with WINDOWS-FIRST-START.cmd.
pause
