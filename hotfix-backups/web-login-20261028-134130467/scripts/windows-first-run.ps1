# This script is source code, not a packaged binary. All installation is user-scoped.
# Python comes from python.org only when a compatible interpreter is unavailable.
param(
    [switch]$Full,
    [switch]$NoBrowser,
    [switch]$SkipGmsh,
    [switch]$SetupPalace,
    [int]$Port = 8000,
    [int]$CPUs = 2,
    [int]$MemoryGB = 4
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port must be 1024-65535.' }
if ($CPUs -lt 1 -or $MemoryGB -lt 1) { throw 'CPU and memory reservations must be positive.' }

function Test-Python([string]$Executable) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    try {
        $check = (& $Executable -c 'import sys;print(int((3,11)<=sys.version_info[:2]<(3,14)))' 2>$null | Select-Object -Last 1)
        return ($LASTEXITCODE -eq 0 -and "$check" -eq '1')
    } catch { return $false }
}

function Find-Python {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        'C:\Program Files\Python312\python.exe',
        'C:\Program Files\Python313\python.exe'
    )
    foreach ($candidate in $candidates) { if (Test-Python $candidate) { return $candidate } }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($version in @('-3.12','-3.13','-3.11')) {
            try {
                $executable = (& $py.Source $version -c 'import sys;print(sys.executable)' 2>$null | Select-Object -Last 1)
                if ($executable -and (Test-Python $executable.Trim())) { return $executable.Trim() }
            } catch {}
        }
    }
    foreach ($name in @('python.exe','python3.exe')) {
        $command=Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and (Test-Python $command.Source)) { return $command.Source }
    }
    return $null
}

Write-Host '[1/4] Checking Python 3.11-3.13...' -ForegroundColor Cyan
$python = Find-Python
if (-not $python) {
    Write-Host 'No compatible Python installation found. Fetching the official Python 3.12.10 installer.'
    Write-Host 'Internet access is required on first start. No elevated privileges will be requested.'
    $url='https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
    $installer=Join-Path $env:TEMP 'sqe-python-3.12.10-amd64.exe'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    $signature=Get-AuthenticodeSignature -FilePath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        Remove-Item -LiteralPath $installer -ErrorAction SilentlyContinue
        throw 'The Python installer signature could not be verified as Python Software Foundation. Installation aborted.'
    }
    $target=Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312'
    $p=Start-Process -FilePath $installer -ArgumentList @('/quiet','InstallAllUsers=0','PrependPath=0','Include_pip=1','Include_test=0',"TargetDir=$target") -PassThru -Wait
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "Python installation exited with $($p.ExitCode)" }
    $python=Join-Path $target 'python.exe'
    if (-not (Test-Python $python)) { throw "Python was not found after installation: $python" }
}
Write-Host "Python: $python" -ForegroundColor Green

$venvPython=Join-Path $root '.venv\Scripts\python.exe'
$environmentStatus=Join-Path $root '.venv\sqw-environment.json'
$needsInstall=$true
if ((Test-Path $venvPython) -and (Test-Path $environmentStatus)) {
    try { $state=Get-Content $environmentStatus -Raw | ConvertFrom-Json; if ($state.status -eq 'ready') { $needsInstall=$false } } catch {}
}
# A v0.6 preexisting environment can be marked ready but not include the new
# Shapely physical-CAD dependency. Requalify it through bootstrap in that case.
if (-not $needsInstall) {
    try {
        & $venvPython -c 'import shapely; assert tuple(map(int,shapely.__version__.split(".")[:2])) >= (2,0)'
        if ($LASTEXITCODE -ne 0) { $needsInstall=$true }
    } catch { $needsInstall=$true }
}
Write-Host '[2/4] Isolated Python environment...' -ForegroundColor Cyan
if ($needsInstall) {
    if ($Full) { $profile='full' } else { $profile='core' }
    Write-Host "Installing profile: $profile (Python packages come from the configured pip index)."
    & $python (Join-Path $root 'scripts\bootstrap.py') --profile $profile --skip-demo --skip-tests
    if ($LASTEXITCODE -ne 0) { throw "Python bootstrap failed with exit code $LASTEXITCODE" }
} else {
    Write-Host 'Existing qualified environment found; skipping installation.' -ForegroundColor Green
    if ($Full -and (Get-Content $environmentStatus -Raw | ConvertFrom-Json).profile -ne 'full') {
        throw 'Existing core environment cannot silently become full. Follow docs/windows.md to use a separate full .venv.'
    }
}
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Virtual environment Python executable is missing.' }

# Gmsh is an optional Python wheel required for the FEM mesher.
# A failed native dependency does not prevent using local circuit analyses.
if (-not $SkipGmsh) {
    Write-Host 'Checking Gmsh Python FEM mesher...' -ForegroundColor Cyan
    try { & $venvPython -c 'import gmsh; print("Gmsh version:", gmsh.__version__)' 2>$null } catch { }
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Installing Gmsh 4.15.2 from pip; Palace itself is a separate Linux program.'
        $gmshInstallExit = 1
        try {
            & $venvPython -m pip install 'gmsh==4.15.2'
            $gmshInstallExit = $LASTEXITCODE
        } catch { Write-Warning "Gmsh pip install raised: $($_.Exception.Message)" }
        if ($gmshInstallExit -ne 0) {
            Write-Warning 'Gmsh installation failed: reduced-order Web simulation still works, but no FEM mesh is available.'
        } else {
            $gmshCheckExit = 1
            try {
                & $venvPython (Join-Path $root 'scripts\record_optional_gmsh.py')
                $gmshCheckExit = $LASTEXITCODE
            } catch { Write-Warning "Gmsh native API check raised: $($_.Exception.Message)" }
            if ($gmshCheckExit -ne 0) { Write-Warning 'Gmsh installed but validation/registration failed; check native dependencies.' }
        }
    }
}
if ($SetupPalace) {
    Write-Host 'Starting opt-in Palace/WSL installer (Ubuntu sudo and possible reboot required).' -ForegroundColor Cyan
    & (Join-Path $root 'scripts\windows-palace-setup.ps1')
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'Palace setup incomplete; you can resume with WINDOWS-PALACE-SETUP.cmd later.'
    }
}
Write-Host '[3/4] Running start-up scientific smoke tests (non-blocking)...' -ForegroundColor Cyan
# A failed optional regression is a warning, not a reason to lock the user out
# of the Web diagnostics page. Persistent reports are shown in the control UI.
try {
    & $venvPython (Join-Path $root 'scripts\startup_checks.py')
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Start-up checks failed; use System & Diagnostics after login.' }
} catch { Write-Warning 'Start-up checks could not run; use System & Diagnostics after login.' }

Write-Host '[4/4] Starting the local Web interface and queue worker...' -ForegroundColor Cyan
Write-Host 'First login requires administrator setup; the workspace opens in the browser.'
Write-Host 'After login: System & Diagnostics is available in the left navigation.'
Write-Host 'All data stays inside studio-data. Press Ctrl+C to stop the service.'
$argsList=@('-m','sqw.studio.launch','--data',(Join-Path $root 'studio-data'),'--host','127.0.0.1','--port',"$Port",'--cpus',"$CPUs",'--memory-gb',"$MemoryGB",'--concurrent-jobs','1')
if (-not $NoBrowser) { $argsList+='--open-browser' }
& $venvPython @argsList
if ($LASTEXITCODE -ne 0) { throw "SQE Studio exited with code $LASTEXITCODE" }
