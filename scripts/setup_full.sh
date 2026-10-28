#!/usr/bin/env bash
set -euo pipefail
# After installing the OS prerequisites in docs/setup.md, one command provisions
# the Python reference environment and native Palace under this checkout.
sqw_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$sqw_root"
python3 scripts/bootstrap.py --profile full --skip-demo
bash scripts/build_palace.sh
"$sqw_root/.venv/bin/python" -m sqw doctor
echo "Full environment built. Qualify mesh, solves and KLayout with docs/fem.md."
