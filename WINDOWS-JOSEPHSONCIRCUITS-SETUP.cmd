@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows-josephsoncircuits-setup.ps1"
if errorlevel 1 echo [SQE] Julia setup failed; inspect the errors above.
pause
