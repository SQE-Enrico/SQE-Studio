# Local Windows development: reuse the project's prepared scientific environment.
[CmdletBinding()]
param(
    [string] $Profile = 'recommended',
    [switch] $Watch,
    [switch] $Check,
    [switch] $Doctor,
    [string] $Python = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'SQE-Studio')).Path

if (-not $Python -and $env:LOCALAPPDATA) {
    # Bootstrap only the bound/current project, never another project's runtime.
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $bytes = $hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectRoot.ToLowerInvariant())) }
    finally { $hasher.Dispose() }
    $digest = ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
    $runtimeId = $digest.Substring(0, 16)
    $localRoot = Join-Path $env:LOCALAPPDATA 'SQE-Studio'
    $binding = Join-Path $localRoot "bindings\$runtimeId.json"
    if (Test-Path -LiteralPath $binding) {
        $bound = Get-Content -LiteralPath $binding -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($bound.schema -eq 'sqe.local-runtime-binding.v1' -and
            $bound.source_path_sha256 -eq $digest -and $bound.environment_id -cmatch '^[a-f0-9]{16}$') {
            $runtimeId = $bound.environment_id
        }
    }
    $runtimeRoot = Join-Path $localRoot "environments\$runtimeId"
    $readyPath = Join-Path $runtimeRoot 'ready.json'
    $candidate = Join-Path $runtimeRoot 'venv\Scripts\python.exe'
    if ((Test-Path -LiteralPath $readyPath) -and (Test-Path -LiteralPath $candidate)) {
        $ready = Get-Content -LiteralPath $readyPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($ready.schema -eq 'sqe.local-python-runtime.v1' -and $ready.python_version -eq '3.11' -and
            $ready.source_path_sha256 -cmatch '^[a-f0-9]{64}$' -and
            $ready.source_path_sha256.Substring(0, 16) -eq $runtimeId) { $Python = $candidate }
    }
}
if (-not $Python) {
    $candidate = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $candidate) { $Python = $candidate }
}
$prefixArguments = @()
if (-not $Python) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) { $Python = $launcher.Source; $prefixArguments = @('-3.11') }
    else {
        $launcher = Get-Command python -ErrorAction SilentlyContinue
        if ($launcher) { $Python = $launcher.Source }
    }
}
if (-not $Python) { throw 'No Python found. Prepare the SQE environment or pass -Python <python.exe>.' }

$toolArguments = @('-u', (Join-Path $projectRoot 'tools\dev.py'), '--profile', $Profile)
if ($Watch) { $toolArguments += '--watch' }
if ($Check) { $toolArguments += '--check' }
if ($Doctor) { $toolArguments += '--doctor' }
$previousUtf8 = $env:PYTHONUTF8
$previousBytecode = $env:PYTHONDONTWRITEBYTECODE
try {
    $env:PYTHONUTF8 = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & $Python @prefixArguments @toolArguments
    $resultCode = $LASTEXITCODE
} finally {
    $env:PYTHONUTF8 = $previousUtf8
    $env:PYTHONDONTWRITEBYTECODE = $previousBytecode
}
exit $resultCode
