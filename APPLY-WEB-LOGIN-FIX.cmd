@echo off
setlocal
cd /d "%~dp0"
echo SQE Studio 0.10.0 - Web Login Hotfix
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0WEB-LOGIN-FIX\apply.ps1"
if errorlevel 1 (
  echo.
  echo The hotfix did not complete. Read the message above.
  pause
  exit /b 1
)
echo.
echo You can now restart SQE Studio.
pause
endlocal
