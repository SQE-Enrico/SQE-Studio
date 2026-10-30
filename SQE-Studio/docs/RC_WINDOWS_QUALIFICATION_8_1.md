# RC8.1 browser evidence-path compatibility hotfix

Status: **EXPERIMENTAL / NOT RELEASE CANDIDATE**. This is a Windows qualification-test-only correction, NOT a change to any scientific engine, solver, geometry, revision, security gate, or GUI production module.

## Field evidence

The ZIP `SQE-Studio-qualification-20261030(8).zip` was checked for CRC errors and all 19 declared file SHA-256 hashes. The Windows 11 / Python 3.11.9 comprehensive qualification reported **9 PASS, 1 FAIL, 6 BLOCKED**. The integrated regression reported **273 passed, 9 skipped**; native Quantum Metal passed 5 tests; native scqubits passed 4 tests; installed wheel and HTTP/CSRF acceptance passed. Chromium smoke passed. Browser deep acceptance reported 2 passed and 1 failed.

In `test_real_browser_local_http_auth_revisions_and_fail_closed_job`, the browser completed project revisions, layout editing, authenticated EM worker blocked outcome, immutable history, and Fabrication HOLD checks before failing at `audit_viewport` while printing the screenshot path. The screenshot was saved under an external temporary qualification directory. The test incorrectly used `capture.relative_to(ROOT)`, which raises `ValueError` whenever the capture directory is not under the project source root. This is a **test evidence-path bug** and does not demonstrate a runtime CAD, solver or GUI defect. Remaining responsive layout assertions after the failed print were not reached and must not be marked as passed.

## Correction

- The browser test now logs only the evidence screenshot filename (`capture.name`), regardless of capture root. This also prevents user-home paths from leaking into shared logs.
- Added a test that writes a screenshot under a separate temporary directory and executes `audit_viewport` to exercise the previously failing line.
- Updated the evolved-source SHA-256 inventory; frozen contracts and `FOUNDATION_LOCK.json` remain unchanged.
- The installable production wheel remains **0.1.1.dev8, byte-for-byte unchanged**. There is no need to reinstall scientific dependencies or replace the wheel. This full source distribution contains the corrected qualification test.

## Remaining blockers

- Julia executable exists, but JosephsonCircuits.jl is absent (native RF test skipped).
- Node.js is unavailable for optional JS syntax gate; real Chromium tests run independently.
- SQDMetal/Palace native EM solve and convergence are not qualified.
- Reviewed EM -> EPR -> Hamiltonian integration and general geometry optimization are not yet implemented and qualified.
- Independent experimental validation, PDK, DRC/LVS and foundry signoff are absent. Fabrication remains HOLD.

## Next Windows acceptance

Use `Qualify this laptop > Comprehensive` with the existing connected Python 3.11 scientific environment. The deep-browser viewport assertions must complete for the browser gate to PASS. Do not infer scientific qualification from passing software acceptance.
