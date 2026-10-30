# Offline local, non-admin installation to an isolated Windows 11 venv.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string] $WheelPath,
  [string] $InstallDirectory = "$env:LOCALAPPDATA\SQE-Studio"
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$wheel = (Resolve-Path $WheelPath).Path
if ((Split-Path $wheel -Leaf) -cne 'sqe_studio_product_foundation-0.1.1.dev9-py3-none-any.whl') { throw 'Expected the exact reviewed SQE Studio core wheel name.' }
$expectedHash = "$wheel.sha256"
if (-not (Test-Path $expectedHash)) { throw 'Missing wheel SHA-256 sidecar; refuse unverified installation.' }
$line = (Get-Content $expectedHash -TotalCount 1).Trim()
$parts = $line -split '\s+',2
$hash = (Get-FileHash -Algorithm SHA256 $wheel).Hash.ToLowerInvariant()
if ($parts.Count -ne 2 -or $parts[0].ToLowerInvariant() -cne $hash -or $parts[1].Trim() -cne (Split-Path $wheel -Leaf)) { throw 'Wheel SHA-256 mismatch.' }
$ver = & py -3.11 -c 'import sys; print("%d.%d" % sys.version_info[:2])'
if ($LASTEXITCODE -ne 0 -or $ver.Trim() -ne '3.11') { throw 'Install Python 3.11 x64 first.' }
if (Test-Path $InstallDirectory) { throw 'Existing install: use a separate directory and explicit offline upgrade policy, never overwrite data.' }
New-Item -ItemType Directory -Force -Path $InstallDirectory | Out-Null
& py -3.11 -m venv (Join-Path $InstallDirectory 'venv')
if ($LASTEXITCODE -ne 0) { throw 'Venv creation failed.' }
$python = Join-Path $InstallDirectory 'venv\Scripts\python.exe'
& $python -m pip install --disable-pip-version-check --no-index --no-deps $wheel
if ($LASTEXITCODE -ne 0) { throw 'Offline wheel install failed.' }
# Run from the installed interpreter, exercising an independent service subprocess.
& $python (Join-Path $PSScriptRoot 'verify_wheel.py') --wheel $wheel
if ($LASTEXITCODE -ne 0) { throw 'Installed runtime smoke failed; do not start service.' }
Write-Host 'PASS: installed wheel verified; no native sidecar auto-installed.'
Write-Host "Start using: `"$python`" -m sqe_studio.server --data `"$InstallDirectory\data`" --port 8000"
