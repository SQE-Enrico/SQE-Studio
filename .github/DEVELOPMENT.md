# Development tracked on GitHub

Use English for code, comments, documentation, GitHub issues/PRs and commit
messages. The owner may give instructions in Italian.

Each increment starts from an issue with an observable outcome, acceptance
criteria and required tests. The roadmap groups these issues into five milestones.

1. Work on a codex/<issue>-<topic> feature branch.
2. Run focused tests and Recommended on the scientific workstation. Run
   software before integration and the native profiles required by the issue.
3. Commit descriptive, verified increments and push the feature branch.
4. Maintain a linked PR using Refs #number. Use Closes #number only when its
   acceptance criteria have been verified.
5. Inspect CI for the current revision, fix failures, and update the issue/PR
   with reports, checksums and explicit exclusions.

Pushes and pull requests trigger GitHub Actions. Each job records its commit,
environment, test families, regression domains and downloadable evidence.
Linked issues close when a PR containing Closes is merged into the default
branch; GitHub updates the associated milestone.

Agents working in this repository maintain issues and PRs with current evidence
after each verified increment. Commit/PR publication is part of the authorized
development cycle. Merge requires an explicit owner instruction. Periodic chat
monitoring is not configured.

GitHub-hosted CI installs software/browser test tools. The native scientific
backends are exercised on the workstation using the relevant local profiles.
The single_transmon profile uses real Palace and scqubits; extraction remains
the separately labeled EM-fixture compatibility test.

The original core map stays immutable. Scientific integration changes require
the current source review and exact active hashes in config/core_changes.json,
with primary references and meaningful native validation. Fingerprint refresh
alone does not authorize a numerical change or a physical release.

Development extras include NumPy/SciPy for sparse compatibility tests and
Shapely for direct declared-geometry identity checks on clean CI runners.
