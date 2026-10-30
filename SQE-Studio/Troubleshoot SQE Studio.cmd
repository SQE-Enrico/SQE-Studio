@echo off
setlocal
cd /d "%~dp0"
echo SQE Studio launcher diagnostics - no changes to installed environments.
echo A detailed log is also written under %%LOCALAPPDATA%%\SQE-Studio\launcher-errors.log.
where py >nul 2>&1
if errorlevel 1 (
  python "scripts\diagnose_launcher.py"
) else (
  py -3 "scripts\diagnose_launcher.py"
)
if errorlevel 1 (
  echo.
  echo SQE Studio did not start. Preserve this error text and the launcher log.
)
echo.
pause
