# SQE Studio 0.13.0 — Delivery and QA record

## Confirmed in development environment

- Fixed independent capacitor/cavity mesh generation, analytic references and input hashes.
- Unit tests for two-level patch-test comparison, numerical failure values, solver provenance, tamper rejection, cavity frequency and matrix summary.
- Scientific ZIP with `scientific-results.json`, correct allowlist and checksum manifest; in the development environment without Palace, reference preparation `PASS`, actual solver stages `SKIP`.
- v0.12 benchmark/quality/diagnostic/parametric/physical tests passed in isolated executions.
- JavaScript syntax, Python compilation and Bash syntax checks passed.

## Not confirmed

- A genuine Palace capacitor/cavity run against Windows 11 / Ubuntu WSL2.
- Palace 0.16.0 schema compatibility and eigenmode availability on target workstation.
- End-to-end visual browser acceptance on Windows 11.
- Clean termination of full historical regression suite: the worker-process test runner stalled when run as one batch. This must not be described as a pass.

## Scientific caution

The two-level capacitor comparison is an *exact linear-potential patch test* and is not a QPU mesh convergence claim. A passed PEC cavity eigenvalue threshold is not proof of mode identity or EPR accuracy. Source hashes are recorded; no synthetic output will be substituted for Palace.

## Next workstation test

Run **Numerical** via `control.html`, download the diagnostic ZIP, and share only after reviewing its contents. If a solve fails, consult the retained bounded logs and `scientific-results.json`. Do not run Full in parallel.
