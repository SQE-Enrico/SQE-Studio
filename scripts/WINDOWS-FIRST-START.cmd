@echo off
setlocal
set "WHEEL=%~dp0..\release\sqe_studio_product_foundation-0.1.0-py3-none-any.whl"
if not exist "%WHEEL%" (
  echo Missing verified core wheel: %WHEEL%
  echo Build offline first with scripts\Build-Windows11Wheel.ps1 and a trusted local wheelhouse.
  exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Windows11.ps1" -WheelPath "%WHEEL%"
if errorlevel 1 exit /b 1
exit /b 0
