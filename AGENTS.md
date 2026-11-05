# SQE Studio workspace

Use English for code, comments, documentation, GitHub issues/PRs, commit
messages and user-facing replies. The user may continue writing in Italian.

The Python project is in `SQE-Studio/`. Read its `AGENTS.md` and
`CURRENT_STATE.json`, then use `tools/context.py` for the relevant area.

The owner's current product objective is a scientifically credible QuantumPro
competitor. Use QUANTUMPRO_COMPETITOR_MATRIX.md and QUANTUMPRO_DEVELOPMENT_PLAN.md
for current priorities. Historical architecture and locks are baseline evidence,
not permanent feature prohibitions; justified changes need meaningful validation.

Run local development checks from this directory with `./dev.ps1` on Windows.
It selects the existing project scientific runtime, refreshes software-only
fingerprints and runs UI controller checks plus Recommended Automatic Test.
Use `./dev.ps1 -Watch` for save-triggered reruns and `./dev.ps1 -Doctor` for tools.
Use `-Profile software` for all portable domains, real browser and wheel install;
use the relevant native profile for scientific integration changes.
`-Check` verifies existing fingerprints without updating them (required in CI).
Treat exit 1 as a failure and exit 2 as blocked/incomplete. Report explicit skips.
Do not claim completion while required checks are blocked or files changed during
the run. Do not start a persistent watcher unless the user requests one.

The active GitHub workflow lives in the repository-root `.github/workflows/`.
Preserve existing local changes and the original numerical/core hash map.
Current scientific integration changes require the separate source review in
SQE-Studio/config/core_changes.json; fingerprint refresh alone cannot authorize them.
Keep Git's byte-preserving attributes: newline conversion changes signed hashes.

Development is tracked on GitHub by issue, milestone and feature PR. Follow
`.github/DEVELOPMENT.md`: after the relevant checks pass, commit and push the
feature branch and maintain its linked PR and issue with current evidence.
Use `Closes #number` only when the issue's acceptance criteria are satisfied.
Merge only when the user explicitly requests it. GitHub Actions handles commit/PR
checks and reports; periodic chat monitoring was not requested.
