@echo off
setlocal
cd /d "%~dp0"
echo Installing Quantum Metal in a separate, optional Python environment.
if not exist ".venv\Scripts\python.exe" (
 echo First run WINDOWS-FIRST-START.cmd once.
 pause
 exit /b 2
)
".venv\Scripts\python.exe" -m venv ".venv-metal"
if errorlevel 1 goto failure
".venv-metal\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failure
".venv-metal\Scripts\python.exe" -m pip install "quantum-metal[mesh]>=0.8,<1"
if errorlevel 1 goto failure
".venv-metal\Scripts\python.exe" -c "from qiskit_metal.designs import DesignPlanar; print('Quantum Metal headless API OK')"
if errorlevel 1 goto failure
echo Quantum Metal is installed in .venv-metal. See docs\quantum-metal-integration.md.
pause
exit /b 0
:failure
echo Installation failed. The main SQE Studio environment was not modified.
pause
exit /b 1
