# 0.11.0 delivery verification

Release source: SQE Studio 0.10.0 release ZIP plus the previously delivered Web-login hotfix and new changes.

## Verified in the development container

- Focused Quantum Lab: 11 tests passing.
- Physical QPU: 10 tests passing.
- Parametric QPU: 15 tests passing.
- Palace quality and contract tests: 7 passing.
- Existing diagnostic tests: 8 passing.
- Diagnostic Web authorization: 4 passing.
- Post-login dashboard: 4 passing.
- New scientific diagnostic, queue and English UI regression tests: 4 passing.
- JavaScript syntax validated for Studio, Quantum Lab and System & Diagnostics.
- An actual fixed-reference package/GDS/Palace JSON export succeeded; a generated scientific diagnostic ZIP correctly reported the geometry PASS and missing optional Gmsh/Palace SKIP on Linux development host.

The historical full-test runner printed `Ran 130 tests ... OK (skipped=4)` but did not exit cleanly in this execution environment before the external timeout. This is a known test-runner/worker-process cleanup issue; it is NOT declared a clean full-suite completion.

## Not yet verified

- Web visual interaction on actual Windows 11 (new buttons and queue telemetry).
- Native Gmsh 3D for the full single-transmon geometry on the target PC; diagnostic may time out.
- Palace WSL2 solver execution, matrix extraction, eigenmode, two-driven-port simulations on the target PC.
- Numerical convergence, accuracy, fabrication suitability and runtime/memory limits under actual workload.

## User acceptance

1. Back up local data before applying the release; retain workstation `.venv` and `studio-data`.
2. Open the dashboard after sign-in; `/api/template` must no longer return 500.
3. Open Quantum Design Lab > Palace / FEM 3D, click `Refresh preview and checks` and verify the English notice.
4. Review the existing queued mesh job, its stage and worker log; use `Cancel job` if it remains stalled.
5. Open System & Diagnostics, verify `Compute queue health`, run Extended, then optionally opt into `Scientific workflow validation` with sufficient time and memory.
6. Download the ZIP, review its contents, and share it for debugging. Never send the entire `studio-data` folder.
