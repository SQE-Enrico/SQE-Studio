# SQE Studio v0.10.0 - minimal first-login hotfix (Windows)
# This installer does not install packages or modify studio-data or .venv.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$payload = Join-Path $PSScriptRoot 'payload'
$changes = @(
    @{ Relative="src\sqw\studio\server.py"; Original="C0CC0702DE54589704F641CBB32531F7D348AF385BA7FC17D3875651DA491DE2"; Corrected="31653E6E4E7A1817B886C24B3F169565F00335B3589A83EA0A791502841B7672" }
    @{ Relative="scripts\windows-first-run.ps1"; Original="203E9506604684F6B53D7113D113E44AD08AA2BDBD8336280777527240CDF218"; Corrected="AD1171D11529C97E737519F0C3DC2C4C0F9236FBD58390AE18904DD2B9655600" }
)
$testRel='tests\studio\test_dashboard_boot.py'
$testSource=Join-Path $payload $testRel
$testDestination=Join-Path $root $testRel
$testHash='92AE75207990FA0A19156D2CE607B665EEB3DC8EC59C515296775B09F7856CD9'
$backup=Join-Path $root ('hotfix-backups\web-login-'+(Get-Date -Format 'yyyyMMdd-HHmmssfff'))
$changed=New-Object System.Collections.ArrayList
$testAdded=$false

try {
    if (-not (Test-Path -LiteralPath (Join-Path $root 'WINDOWS-FIRST-START.cmd'))) {
        throw 'Extract this hotfix inside the SQE Studio installation folder before running it.'
    }
    foreach ($entry in $changes) {
        $target=Join-Path $root $entry.Relative
        $replacement=Join-Path $payload $entry.Relative
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Missing expected file: $($entry.Relative)" }
        if (-not (Test-Path -LiteralPath $replacement -PathType Leaf)) { throw "Missing patch file: $($entry.Relative)" }
        $current=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
        $patchHash=(Get-FileHash -LiteralPath $replacement -Algorithm SHA256).Hash
        if ($patchHash -ne $entry.Corrected) { throw "Patch integrity check failed: $($entry.Relative)" }
        if ($current -ne $entry.Original -and $current -ne $entry.Corrected) {
            throw "Unknown version or local edits: $($entry.Relative). No files have been changed."
        }
    }
    if (-not (Test-Path -LiteralPath $testSource -PathType Leaf)) { throw 'The regression test is missing from the hotfix.' }
    if ((Get-FileHash -LiteralPath $testSource -Algorithm SHA256).Hash -ne $testHash) { throw 'Regression test integrity check failed.' }
    if (Test-Path -LiteralPath $testDestination -PathType Leaf) {
        if ((Get-FileHash -LiteralPath $testDestination -Algorithm SHA256).Hash -ne $testHash) {
            throw 'An existing dashboard regression test has local changes. No files have been changed.'
        }
    }

    foreach ($entry in $changes) {
        $target=Join-Path $root $entry.Relative
        $replacement=Join-Path $payload $entry.Relative
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -eq $entry.Corrected) {
            Write-Host "Already fixed: $($entry.Relative)"
            continue
        }
        $saved=Join-Path $backup $entry.Relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $saved) | Out-Null
        Copy-Item -LiteralPath $target -Destination $saved -Force
        Copy-Item -LiteralPath $replacement -Destination $target -Force
        [void]$changed.Add(@{Target=$target;Backup=$saved})
        Write-Host "Patched: $($entry.Relative)" -ForegroundColor Green
    }
    if (-not (Test-Path -LiteralPath $testDestination -PathType Leaf)) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $testDestination) | Out-Null
        Copy-Item -LiteralPath $testSource -Destination $testDestination -Force
        $testAdded=$true
    }

    $python=Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        Write-Warning 'Hotfix installed. Existing .venv was not found, so regression tests were not run.'
    } else {
        $oldPythonPath=$env:PYTHONPATH
        try {
            $env:PYTHONPATH=Join-Path $root 'src'
            Write-Host 'Running dashboard API regression tests...'
            & $python -m unittest discover -s (Join-Path $root 'tests\studio') -p test_dashboard_boot.py -v
            if ($LASTEXITCODE -ne 0) { throw "Regression tests returned exit code $LASTEXITCODE" }
        } finally { $env:PYTHONPATH=$oldPythonPath }
    }
    Write-Host ''
    Write-Host 'HOTFIX OK. Stop the old SQE server with Ctrl+C, then double-click WINDOWS-FIRST-START.cmd.' -ForegroundColor Green
    if ($changed.Count -gt 0) { Write-Host "Backups: $backup" }
    exit 0
} catch {
    Write-Host "HOTFIX FAILED: $($_.Exception.Message)" -ForegroundColor Red
    foreach ($entry in $changed) {
        Copy-Item -LiteralPath $entry.Backup -Destination $entry.Target -Force
    }
    if ($testAdded) { Remove-Item -LiteralPath $testDestination -ErrorAction SilentlyContinue }
    if ($changed.Count -gt 0) { Write-Host 'Original files restored from backups.' -ForegroundColor Yellow }
    exit 1
}
