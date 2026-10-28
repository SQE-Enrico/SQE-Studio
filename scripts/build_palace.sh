#!/usr/bin/env bash
set -euo pipefail
# User-invoked native build, no sudo and no system directories modified.
# Install the build prerequisites listed in docs/setup.md before running.
sqw_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sqw_tag="${SQW_PALACE_TAG:-v0.18.1}"
sqw_src="$sqw_root/.sqw/palace-$sqw_tag"
sqw_build="$sqw_src/build"
sqw_jobs="${SQW_BUILD_JOBS:-4}"
mkdir -p "$sqw_root/.sqw"
if [[ ! -d "$sqw_src/.git" ]]; then
  git clone --depth 1 --branch "$sqw_tag" https://github.com/awslabs/palace.git "$sqw_src"
fi
cmake -S "$sqw_src" -B "$sqw_build" -DCMAKE_BUILD_TYPE=Release \
  -DPALACE_WITH_SUPERLU=ON -DPALACE_WITH_SLEPC=ON
cmake --build "$sqw_build" --parallel "$sqw_jobs"
git -C "$sqw_src" rev-parse HEAD > "$sqw_root/.sqw/palace-source-commit.txt"
"$sqw_build/bin/palace" --help
echo "Use --palace $sqw_build/bin/palace in sqw commands."
