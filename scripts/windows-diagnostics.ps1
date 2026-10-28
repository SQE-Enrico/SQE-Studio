<#
SQE Studio diagnostics (read-only, no admin, no network, no installers).
If Python is missing, still emit a minimal PowerShell-only ZIP.
The ZIP contains allowlisted metadata only and MUST be reviewed before sharing.
#>
param([switch]$Extended, [switch]$SkipTests)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $root
$outDir = Join-Path $root 'diagnostics'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

Write-Host 'SQE Studio - Local diagnostics' -ForegroundColor Cyan
Write-Host 'No installation, elevation or upload.'
Write-Host 'Usernames, hostnames, serials, projects and credentials are not collected.'

function Test-PythonExe([string]$File, [string[]]$VersionArgs) {
    try {
        $out = & $File @VersionArgs -c 'import sys;print("SQE_PYTHON_OK" if sys.version_info.major==3 else "NO")' 2>$null
        return ($LASTEXITCODE -eq 0 -and ($out | Select-Object -Last 1) -eq 'SQE_PYTHON_OK')
    } catch { return $false }
}

$python = $null
$pythonArgs = @()
$venv = Join-Path $root '.venv\Scripts\python.exe'
if ((Test-Path -LiteralPath $venv -PathType Leaf) -and (Test-PythonExe -File $venv -VersionArgs @())) {
    $python = $venv
} else {
    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        foreach ($version in @('-3.12','-3.13','-3.11','-3')) {
            if (Test-PythonExe -File $pyLauncher.Source -VersionArgs @($version)) {
                $python = $pyLauncher.Source
                $pythonArgs = @($version)
                break
            }
        }
    }
    if (-not $python) {
        $candidate = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($candidate -and (Test-PythonExe -File $candidate.Source -VersionArgs @())) { $python = $candidate.Source }
    }
}

if ($python) {
    Write-Host 'Python found: running application diagnostics.'
    $pythonCallArgs = @() + $pythonArgs + @((Join-Path $root 'scripts\collect_diagnostics.py'), '--out-dir', $outDir)
    if ($Extended) { $pythonCallArgs += '--extended' }
    if ($SkipTests) { $pythonCallArgs += '--skip-tests' }
    & $python @pythonCallArgs
    if ($LASTEXITCODE -ne 0) { throw 'Python diagnostics did not generate a ZIP.' }
    Write-Host 'Review SUMMARY.txt, environment.json, checks.json and test-results.txt before sharing.' -ForegroundColor Green
    exit 0
}

function Write-UTF8NoBom([string]$Path, [string]$Content) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

# Fallback minimal if Python cannot even start. Windows/PowerShell-only, privacy-safe.
Write-Warning 'Python unavailable: generating minimal PowerShell diagnostic ZIP.'
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ('sqe-diag-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    $os = $null
    $cpu = $null
    $ram = $null
    try { $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop } catch { }
    try { $cpu = Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop | Select-Object -First 1 } catch { }
    try { $ram = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop } catch { }
    $disk = $null
    try { $disk = Get-PSDrive -Name (Get-Location).Drive.Name -ErrorAction Stop } catch { }
    $envData = [ordered]@{
        schema = 'sqe-diagnostics/1'; app_release = '0.10.0'; mode = 'powershell-fallback'
        platform = 'Windows'; os_build = $(if ($os) { [string]$os.BuildNumber } else { $null })
        architecture = 'x64'; cpu_model = $(if ($cpu) { [string]$cpu.Name } else { $null })
        logical_cpu_count = $(if ($cpu) { [int]$cpu.NumberOfLogicalProcessors } else { $null })
        physical_memory_gib = $(if ($ram) { [math]::Round($ram.TotalPhysicalMemory / 1GB,1) } else { $null })
        free_disk_gib = $(if ($disk) { [math]::Round($disk.Free / 1GB,1) } else { $null })
        python_version = $null
        note = 'No user names, computer names, serials, environment variables, file contents or network addresses collected.'
    }
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    $wslStatus = if ($wsl) { 'PASS' } else { 'WARN' }
    $wslCode = if ($wsl) { 'WSL_COMMAND_PRESENT' } else { 'WSL_NOT_FOUND' }
    $checks = @(
        [ordered]@{ id='runtime.python'; status='WARN'; code='PYTHON_NOT_FOUND'; detail='Python not usable'; next_action='Run WINDOWS-FIRST-START.cmd.' },
        [ordered]@{ id='wsl.command'; status=$wslStatus; code=$wslCode; detail='Only checked whether wsl.exe exists'; next_action='Use WINDOWS-PALACE-SETUP.cmd if needed.' },
        [ordered]@{ id='app.regressions'; status='SKIP'; code='NO_PYTHON'; detail='Python tests could not run'; next_action='Install Python to run the standard diagnostic.' }
    )
    $summary = "SQE Studio 0.10 - PowerShell fallback diagnostics`r`nPython not found; no application tests were run.`r`n" +
               "The ZIP is still useful to debug the initial installation.`r`n"
    $privacy = 'Review all ZIP entries before sharing. No uploads, projects, credentials, full directory paths, usernames or machine identifiers were collected. This fallback did not run Python, Gmsh, Palace or Julia.'
    Write-UTF8NoBom (Join-Path $temp 'environment.json') ($envData | ConvertTo-Json -Depth 6)
    Write-UTF8NoBom (Join-Path $temp 'checks.json') ($checks | ConvertTo-Json -Depth 6)
    $summary | Set-Content -LiteralPath (Join-Path $temp 'SUMMARY.txt') -Encoding UTF8
    'Python tests skipped: no compatible executable found.' | Set-Content -LiteralPath (Join-Path $temp 'test-results.txt') -Encoding UTF8
    $privacy | Set-Content -LiteralPath (Join-Path $temp 'README-PRIVACY.txt') -Encoding UTF8
    $manifest = [ordered]@{schema='sqe-diagnostics/1';status='WARN';release='0.10.0';mode='powershell-fallback';created_utc=[DateTime]::UtcNow.ToString('o')}
    Write-UTF8NoBom (Join-Path $temp 'manifest.json') ($manifest | ConvertTo-Json -Depth 6)
    $names = @('README-PRIVACY.txt','environment.json','checks.json','test-results.txt','SUMMARY.txt','manifest.json')
    $sums = @()
    foreach ($name in $names) {
        $sha = (Get-FileHash -LiteralPath (Join-Path $temp $name) -Algorithm SHA256).Hash.ToLowerInvariant()
        $sums += "$sha  $name"
    }
    $sums | Set-Content -LiteralPath (Join-Path $temp 'SHA256SUMS.txt') -Encoding UTF8
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmssZ')
    $zip = Join-Path $outDir ('SQE-DIAGNOSTICS-v0.10.0-FALLBACK-' + $stamp + '.zip')
    $archivePaths = @($names + @('SHA256SUMS.txt') | ForEach-Object { Join-Path $temp $_ })
    Compress-Archive -LiteralPath $archivePaths -DestinationPath $zip -ErrorAction Stop
    Write-Host "Fallback diagnostic ZIP created: $zip" -ForegroundColor Green
    Write-Host 'Open and review the files before sharing.'
} finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
