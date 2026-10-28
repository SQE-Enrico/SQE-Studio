@echo off
setlocal
cd /d "%~dp0"
echo SQE Studio - guided Palace WSL2/Ubuntu installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows-palace-setup.ps1" %*
if errorlevel 1 (
 echo Palace setup is incomplete. Read docs\palace-windows.md.
 pause
 exit /b 1
)
echo.
echo Palace installer completed.
pause
endlocal
