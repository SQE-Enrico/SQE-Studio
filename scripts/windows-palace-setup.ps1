# Palace on one Windows PC via WSL2. Opt-in steps, no silent elevation or reboot.
param([string]$Distribution='Ubuntu', [switch]$InstallWSLOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if ($Distribution -notmatch '^[a-zA-Z0-9_.-]{1,64}$') { throw 'Invalid WSL distro name.' }
Write-Host '=== Palace FEM guided setup / WSL2 ===' -ForegroundColor Cyan
Write-Host 'Palace and Spack are open source. Solver build is opt-in, can be large and requires Internet.'
Write-Host 'WSL installation may require Windows administrator approval and a reboot.'
$wsl=Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wsl) { throw 'wsl.exe is not available. Update Windows 10/11; see docs/palace-windows.md.' }
# Probe the specified distribution directly. In Windows PowerShell 5.1, capturing
# `wsl --list --quiet` can mis-decode the UTF-16 output and report false absence.
# Using only the exit code avoids any output-encoding ambiguity.
& wsl.exe -d $Distribution -- /bin/sh -c 'exit 0'
$distroProbeExit = $LASTEXITCODE
if ($distroProbeExit -ne 0) {
    Write-Host "WSL distribution '$Distribution' could not be launched (exit code $distroProbeExit)." -ForegroundColor Yellow
    Write-Host "If it is listed in 'wsl --list --verbose', do NOT reinstall it. Check initialization with: wsl -d $Distribution -- cat /etc/os-release" -ForegroundColor Yellow
    $answer=Read-Host "WSL distro '$Distribution' not detected. Run 'wsl --install -d $Distribution'? This may request admin elevation and reboot [s/N]"
    if ($answer -notin @('s','S','y','Y')) { Write-Host 'Nothing installed. Re-run after installing WSL.'; exit 2 }
    & wsl.exe --install -d $Distribution
    if ($LASTEXITCODE -ne 0) { throw 'WSL install failed; use an elevated terminal, enable virtualization and retry.' }
    Write-Host 'Complete the Ubuntu first-run user setup/reboot if requested, then re-run this wizard.' -ForegroundColor Yellow
    exit 2
}
& wsl.exe -d $Distribution -- bash -lc 'echo WSL_OK; uname -m; whoami'
if ($LASTEXITCODE -ne 0) { throw 'WSL is not initialized. Open Ubuntu from the Start menu, create a Linux user and retry.' }
if ($InstallWSLOnly) { Write-Host 'WSL initialized. Palace build was skipped.'; exit 0 }
$answer=Read-Host "Install/verify Spack + Palace in '$Distribution'? Dependencies use Ubuntu sudo; downloads and large native builds are required [s/N]"
if ($answer -notin @('s','S','y','Y')) { Write-Host 'Solver installation skipped. It can be resumed later.'; exit 0 }
# Direct WSL exec (-e) bypasses Bash argument parsing, which otherwise removes
# backslashes from unquoted Windows paths like C:\Users\... passed to wslpath.
# Guard the conversion result before calling Trim() so a failed conversion yields
# an actionable error instead of a null-valued expression exception.
$script = Join-Path $PSScriptRoot 'install_palace_wsl.sh'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Palace Linux installer script not found: $script"
}
$wslPathOutput = @(& wsl.exe -d $Distribution --exec wslpath -a -u $script)
$pathExitCode = $LASTEXITCODE
if ($pathExitCode -ne 0 -or $wslPathOutput.Count -eq 0) {
    throw "Cannot translate Windows installation path to WSL (exit $pathExitCode). Verify WSL integration and the project directory."
}
$linuxScript = ([string]$wslPathOutput[-1]).Trim()
if ([string]::IsNullOrWhiteSpace($linuxScript) -or -not $linuxScript.StartsWith('/')) {
    throw "Invalid WSL installation script path: $linuxScript"
}
& wsl.exe -d $Distribution --exec test -r $linuxScript
if ($LASTEXITCODE -ne 0) {
    throw "WSL could not read the installation script: $linuxScript. Check Windows drive automount."
}
Write-Host "Running Palace setup from $linuxScript" -ForegroundColor Cyan
& wsl.exe -d $Distribution --exec bash $linuxScript
if ($LASTEXITCODE -ne 0) { throw "Spack/Palace installation exited with $LASTEXITCODE. Inspect the Linux build log and retry." }
Write-Host 'Palace installed and help command completed. Verify a reference simulation before using results for device design.' -ForegroundColor Green
Write-Host "Launch WINDOWS-FIRST-START.cmd. The Web backend will detect the WSL distro '$Distribution'."
