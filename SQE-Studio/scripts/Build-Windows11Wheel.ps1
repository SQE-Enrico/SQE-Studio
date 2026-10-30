# Reproducible, offline first-party core wheel build. PowerShell 5.1+ / Windows 11.
# Supply a vetted local wheelhouse containing pinned build dependencies.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string] $Wheelhouse,
  [string] $OutputDirectory = 'release'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$wh = (Resolve-Path $Wheelhouse).Path
Push-Location $repo
try {
  if (-not (Test-Path (Join-Path $repo 'FOUNDATION_LOCK.json'))) { throw 'Missing foundation identity; do not build legacy archives.' }
  $ver = & py -3.11 -c 'import sys; print("%d.%d" % sys.version_info[:2])'
  if ($LASTEXITCODE -ne 0 -or $ver.Trim() -ne '3.11') { throw 'Python 3.11 is mandatory.' }
  $venv = Join-Path $repo '.sqe-wheel-build'
  & py -3.11 -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw 'Cannot create isolated build environment.' }
  $python = Join-Path $venv 'Scripts\python.exe'
  & $python -m pip install --disable-pip-version-check --no-index --find-links $wh -r (Join-Path $repo 'requirements\build-win11.txt')
  if ($LASTEXITCODE -ne 0) { throw 'Build dependencies absent from local wheelhouse.' }
  $env:SOURCE_DATE_EPOCH='1700000000'
  $out = Join-Path $repo $OutputDirectory
  New-Item -ItemType Directory -Force -Path $out | Out-Null
  Get-ChildItem -Path $out -Filter 'sqe_studio_product_foundation-0.1.1.dev9-*.whl' | Remove-Item -Force
  & $python -m build --wheel --no-isolation --outdir $out
  if ($LASTEXITCODE -ne 0) { throw 'Core build failed.' }
  $built = @(Get-ChildItem -Path $out -Filter 'sqe_studio_product_foundation-0.1.1.dev9-*.whl')
  if ($built.Count -ne 1) { throw 'Expected exactly one core wheel.' }
  $wheel = $built[0].FullName
  $hash = (Get-FileHash -Algorithm SHA256 $wheel).Hash.ToLowerInvariant()
  Set-Content -Encoding ascii -Path "$wheel.sha256" -Value "$hash  $($built[0].Name)"
  Write-Host "Core wheel: $wheel"; Write-Host "SHA-256: $hash"
  Write-Host 'The wheel is not a scientific-engine installer. Run Install-Windows11.ps1 -WheelPath <wheel>.'
} finally { Pop-Location }
