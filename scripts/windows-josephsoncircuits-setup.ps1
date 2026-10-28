# Optional, explicit, user-invoked Julia environment. The core Web app does not require Julia.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$cmd = Get-Command julia -ErrorAction SilentlyContinue
if (-not $cmd) {
  Write-Host 'Julia is missing. The official Julia instructions recommend Juliaup via Microsoft Store/App Installer.'
  Write-Host 'Installation from Microsoft Store requires user consent and Internet access.'
  $answer = Read-Host 'Install Julia via winget from the official Microsoft Store? [y/N]'
  if ($answer -ne 'y' -and $answer -ne 'Y') { throw 'Julia installation cancelled by user.' }
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'winget not found. See https://julialang.org/install/' }
  & winget install --name Julia --id 9NJNWW8PVKMN -e -s msstore
  if ($LASTEXITCODE -ne 0) { throw 'winget could not install Julia.' }
  Write-Host 'Installation finished. Open a new terminal if julia is not visible on PATH.'
  $cmd = Get-Command julia -ErrorAction SilentlyContinue
  if (-not $cmd) { throw 'Julia is not yet visible on PATH. Relaunch this script from a new terminal.' }
}
Write-Host 'Preparing separate Julia environment and JosephsonCircuits.jl...'
$envdir = Join-Path $root '.julia-josephson'
New-Item -ItemType Directory -Force -Path $envdir | Out-Null
$env:SQE_JULIA_ENV = $envdir
& $cmd.Source --startup-file=no --project=$envdir -e 'using Pkg; Pkg.add("JosephsonCircuits"); Pkg.precompile(); using JosephsonCircuits; println("JosephsonCircuits ready")'
if ($LASTEXITCODE -ne 0) { throw 'Julia or JosephsonCircuits package setup failed. No simulation is claimed.' }
Write-Host 'JosephsonCircuits.jl environment ready (the solver was not scientifically qualified).'
