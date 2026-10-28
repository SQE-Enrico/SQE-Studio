@echo off
setlocal
cd /d "%~dp0"
echo =======================================================
echo  SQE Studio - Emergency Windows Diagnostics
 echo =======================================================
echo No installation, elevation, or automatic upload.
echo Generates a reviewable ZIP in the diagnostics folder.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows-diagnostics.ps1" %*
if errorlevel 1 (
  echo.
  echo ERROR: diagnostics did not finish. Report the displayed error.
  pause
  exit /b 1
)
echo.
echo BEFORE SHARING: open the ZIP and review each file.
pause
endlocal
