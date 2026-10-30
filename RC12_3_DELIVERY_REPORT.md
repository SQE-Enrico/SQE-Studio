# SQE Studio RC12.3 — Windows Qualification Stabilization

**Status:** Experimental / NOT RELEASE CANDIDATE.

## Input evidence

- Source baseline: `SQE-Studio-RC12.2-Windows-ZIP-validation-EXPERIMENTAL.zip` (reused unchanged except for the declared changes).
- User Windows 11 qualification: `SQE-Studio-qualification-20261030(20261030-145509).zip`.
- Uploaded evidence: 28/28 SHA-256 verified, ZIP integrity verified.
- Windows result: 13 PASS gates, 1 FAIL gate, 5 BLOCKED gates; integrated pytest 314 passed, 2 failed, 7 skipped.

## Changes

1. Windows ZIP normalization test no longer relies on the private and unavailable `zipfile._sanitize_filename`. It uses public `ZipFile.infolist` / `ZipInfo.filename` / `ZipInfo.orig_filename` to emulate normalized Windows paths, and requires the existing validator to reject the unsafe original name.
2. HTTP/CSRF adversarial test performs a tightly bounded retry only for `ConnectionAbortedError` during the expected-to-be-rejected `Sec-Fetch-Site: same-site` request. Every aborted attempt must leave the project list unchanged. A genuine HTTP 403 must be seen; a 200, mutation or repeated connection abort still fails the test.
3. Added `docs/RC12_3_WINDOWS_QUALIFICATION.md` and regenerated `EDA_SOURCE_MANIFEST.json` without modifying historical/frozen contracts.

There are **no changes to scientific engines, EDA production application code, scientific numerical models, package dependency versions, or release wheel**.

## Local validation

- ZIP safety + HTTP hardening focused suite: **24 passed**, exit 0.
- Source inventory and frozen contract verification: **PASS**, inventory hash `be2392b0a0d5ab5edf7c73bf8519d77484606ecb0afda87a4a10b0b0c93fca40`.
- Source-integrity regression: **1 passed**, exit 0.
- Python source/test compilation: **PASS**.
- Full integrated pytest on this host: reached 100% test progress but stalled during shutdown and did not produce an exit code / final summary. **NOT counted as a full-suite pass.** Its raw log is included for inspection.
- Native Quantum Metal, SQDMetal/Gmsh mesh generation, Palace solving, scqubits and JosephsonCircuits runs on the user's Windows laptop: **NOT RE-RUN** by this update. Earlier native gates retain their evidence from the uploaded user report.

## Next step

Extract RC12.3 in a new folder, reconnect the existing Python 3.11 scientific environment (do not reinstall solvers), and run `Qualify this laptop -> Comprehensive`. Send the generated ZIP. If software gates pass, proceed to a reviewed native CAD -> Gmsh -> Palace solve with material/port/mesh approvals and repeatability checks; this update alone does not qualify the EM design loop.
