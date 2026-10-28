#!/usr/bin/env bash
set -euo pipefail
# Called by Windows backend. Work in ext4 /tmp rather than DrvFS for MPI/mesh IO.
if [[ $# != 3 ]]; then echo 'usage: palace-wsl-run.sh WORKDIR CONFIG.json RANKS' >&2; exit 2; fi
source_dir="$1"; config="$2"; ranks="$3"
[[ -d "$source_dir" && "$config" =~ ^(electrostatic|eigenmode|linearized|driven(-[12])?|convergence-(electrostatic|eigenmode)-L[0-3])\.json$ && "$ranks" =~ ^[1-9][0-9]*$ ]] || exit 2
[[ "$ranks" -le 128 ]] || { echo 'Too many MPI ranks' >&2; exit 2; }
work="$(mktemp -d "${TMPDIR:-/tmp}/sqe-palace-XXXXXXXX")"
trap 'rm -rf -- "$work"' EXIT
for file in device.msh "$config"; do [[ -f "$source_dir/$file" ]] || { echo "Missing $file" >&2; exit 2; }; cp -- "$source_dir/$file" "$work/$file"; done
if [[ -x "$HOME/.sqe/palace/bin/palace" ]]; then
  exe="$HOME/.sqe/palace/bin/palace"
else
  setup="$HOME/.sqe/spack/share/spack/setup-env.sh"
  [[ -f "$setup" ]] || { echo 'Spack missing. Run WINDOWS-PALACE-SETUP.cmd' >&2; exit 3; }
  # shellcheck disable=SC1090
  source "$setup"
  spack load palace
  exe="$(command -v palace)"
fi
[[ -n "$exe" ]] || { echo 'Palace executable unavailable' >&2; exit 3; }
cd "$work"
echo "Running Palace inside WSL2 ($ranks MPI ranks), scratch=$work" >&2
# Palace writes to the configured local subdirectory. Exit code is preserved.
if [[ -x /usr/bin/time ]]; then
  echo "SQE_RESOURCE_ACCOUNTING=GNU_TIME" >&2
  /usr/bin/time -v "$exe" -np "$ranks" "$config"
else
  echo "SQE_RESOURCE_ACCOUNTING=UNAVAILABLE" >&2
  "$exe" -np "$ranks" "$config"
fi
output="$(python3 - "$config" <<'PY'
import json,sys
cfg=json.load(open(sys.argv[1],encoding='utf-8'))
s=cfg['Problem']['Output']
if not s or s.startswith('/') or '..' in s.split('/') or '\\' in s:
    raise ValueError('Unsafe Palace output directory')
print(s)
PY
)"
[[ -d "$work/$output" ]] || { echo 'Palace did not create an output folder' >&2; exit 4; }
# Solver outputs belong to the specific immutable job workspace.
if [[ -e "$source_dir/$output" ]]; then echo 'Destination already exists; preserving previous result' >&2; exit 5; fi
cp -a -- "$work/$output" "$source_dir/$output"
