@echo off
setlocal
cd /d "%~dp0"
echo ====================================================
echo   SQE Studio / Open Quantum Design Lab - Windows
 echo ====================================================
echo First start: Python environment and dependencies will be installed per-user.
echo Later starts: reuse the same environment and projects.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows-first-run.ps1" %*
if errorlevel 1 (
  echo.
  echo ERROR: startup failed. Check the messages above and docs\windows.md.
  pause
  exit /b 1
)
endlocal
