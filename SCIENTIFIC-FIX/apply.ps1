# SQE Studio 0.11.0 Scientific Diagnostics Hotfix v2
# Root discovery uses script location. No quoted trailing-backslash argument is passed by cmd.exe.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Fail([string]$Message) { throw $Message }

$rootCandidate = Join-Path -Path $PSScriptRoot -ChildPath '..'
$root = (Resolve-Path -LiteralPath $rootCandidate -ErrorAction Stop).ProviderPath
$payload = Join-Path -Path $PSScriptRoot -ChildPath 'files'
$relativeFiles = @(
    'src/sqw/diagnostics.py',
    'scripts/palace-wsl-run.sh',
    'tests/test_scientific_diagnostics_v011.py'
)
$entries = @()

$projectMarker = Join-Path $root 'WINDOWS-FIRST-START.cmd'
$pyproject = Join-Path $root 'pyproject.toml'
if (-not (Test-Path -LiteralPath $projectMarker -PathType Leaf)) {
    Fail 'The patch is not inside the SQE-Studio root folder (WINDOWS-FIRST-START.cmd missing).'
}
if (-not (Test-Path -LiteralPath $pyproject -PathType Leaf)) {
    Fail 'The patch is not inside an SQE Studio source folder (pyproject.toml missing).'
}
if (-not (Select-String -LiteralPath $pyproject -Pattern 'version\s*=\s*"0\.11\.0"' -Quiet)) {
    Fail 'This hotfix supports only SQE Studio v0.11.0. Nothing was modified.'
}

foreach ($relative in $relativeFiles) {
    $native = $relative.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
    $source = Join-Path $payload $native
    $target = Join-Path $root $native
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { Fail "Missing hotfix payload: $relative" }
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { Fail "Missing SQE Studio file: $relative" }
    $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $targetHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    $entries += [PSCustomObject]@{ Relative=$relative; Source=$source; Target=$target; Same=($sourceHash -eq $targetHash) }
}
Write-Host "SQE Studio project: $root"

$py = Join-Path (Join-Path (Join-Path $root '.venv') 'Scripts') 'python.exe'
function Test-Hotfix {
    if (Test-Path -LiteralPath $py -PathType Leaf) {
        Push-Location $root
        try {
            Write-Host 'Running scientific diagnostics regression tests...'
            & $py -m unittest discover -s tests -p test_scientific_diagnostics_v011.py -q
            if ($LASTEXITCODE -ne 0) { Fail "Scientific diagnostics tests returned exit code $LASTEXITCODE" }
            Write-Host 'PASS: scientific diagnostics regression tests.'
        } finally { Pop-Location }
    } else {
        Write-Host 'SKIP: Python virtual environment is not present. Run WINDOWS-FIRST-START.cmd later.'
    }
}

$changed = @($entries | Where-Object { -not $_.Same })
if ($changed.Count -eq 0) {
    Write-Host 'All three hotfix files already match the corrected versions.'
    Test-Hotfix
    exit 0
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$backup = Join-Path (Join-Path $root 'patch-backups') "scientific-diagnostics-v2-$stamp"
$backupReady = $false
$applyStarted = $false
try {
    # Back up *all* target files before changing any of them.
    foreach ($entry in $entries) {
        $native = $entry.Relative.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
        $saved = Join-Path $backup $native
        $parent = Split-Path -Path $saved -Parent
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $entry.Target -Destination $saved -Force -ErrorAction Stop
    }
    $backupReady = $true
    Write-Host "Original files backed up to: $backup"
    $applyStarted = $true
    foreach ($entry in $changed) {
        Copy-Item -LiteralPath $entry.Source -Destination $entry.Target -Force -ErrorAction Stop
        $targetHash = (Get-FileHash -LiteralPath $entry.Target -Algorithm SHA256).Hash
        $sourceHash = (Get-FileHash -LiteralPath $entry.Source -Algorithm SHA256).Hash
        if ($targetHash -ne $sourceHash) { Fail "Hash verification failed: $($entry.Relative)" }
        Write-Host "Updated: $($entry.Relative)"
    }
    Test-Hotfix
    Write-Host 'SUCCESS: Scientific diagnostics hotfix v2 installed and verified.'
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($backupReady -and $applyStarted) {
        Write-Host 'Restoring original files from backup...'
        $restoreErrors = @()
        foreach ($entry in $entries) {
            $native = $entry.Relative.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
            $saved = Join-Path $backup $native
            try {
                Copy-Item -LiteralPath $saved -Destination $entry.Target -Force -ErrorAction Stop
            } catch { $restoreErrors += $entry.Relative }
        }
        if ($restoreErrors.Count -gt 0) {
            Write-Host ("WARNING: Restoration incomplete for: " + ($restoreErrors -join ', ')) -ForegroundColor Red
            Write-Host "Manual backups are available at: $backup"
        } else {
            Write-Host 'Original files restored successfully.'
        }
    } else {
        Write-Host 'No source files were modified.'
    }
    exit 1
}
