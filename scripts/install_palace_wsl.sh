#!/usr/bin/env bash
set -euo pipefail
# Execute from an opt-in PowerShell wizard, inside the Ubuntu WSL distribution.
# Spack package build from source may be resource intensive. No false success flag.
export DEBIAN_FRONTEND=noninteractive
if ! command -v apt-get >/dev/null 2>&1; then echo 'This installer supports Ubuntu/Debian WSL. Use Spack manually on other distros.' >&2; exit 2; fi
if [[ -z "$(command -v sudo || true)" ]]; then echo 'sudo is required for Ubuntu dependencies.' >&2; exit 2; fi
printf 'Installing Linux build dependencies for Palace using sudo (Ubuntu)...\n'
sudo apt-get update
sudo apt-get install -y --no-install-recommends git curl ca-certificates python3 python3-venv python3-pip build-essential gfortran cmake ninja-build pkg-config patchelf bzip2 xz-utils unzip file tar make perl gawk libopenblas-dev liblapack-dev libopenmpi-dev openmpi-bin libssl-dev zlib1g-dev libglu1-mesa libgl1
base="$HOME/.sqe"; spack="$base/spack"; mkdir -p "$base"
if [[ ! -f "$spack/share/spack/setup-env.sh" ]]; then
  if [[ -e "$spack" ]]; then echo "Not overwriting non-Spack directory: $spack" >&2; exit 2; fi
  echo 'Cloning the Spack releases/v1.2 branch (project-owned directory)...'
  git clone --depth 1 --branch releases/v1.2 https://github.com/spack/spack.git "$spack"
fi
# shellcheck disable=SC1091
source "$spack/share/spack/setup-env.sh"
spack compiler find || true
spack external find cmake || true
spack versions palace
printf '\nStarting the official Spack Palace build. This may use substantial disk, memory and CPU.\n'
spack install palace
spack load palace
command -v palace
palace -h
printf '\nPALACE_INSTALLED_IN_WSL=1\n'
