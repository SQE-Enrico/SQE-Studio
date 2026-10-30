# SQE Studio RC12.1 — Windows Qualification Portability Fix

**Status:** EXPERIMENTAL / NOT RELEASE CANDIDATE.

## Verified incoming laptop report

The submitted `SQE-Studio-qualification-20261030(20261030-143142).zip`
was validated: every one of 28 declared evidence payloads matched SHA-256,
with no unexpected or missing members. The Windows comprehensive report shows:

- **13 PASS / 1 FAIL / 5 BLOCKED gates**.
- Integrated regression: **312 passed, 2 failed, 7 skipped**.
- Native API handshake **PASS** for installed SQDMetal 0.0.1.dev1,
  Gmsh 4.15.2, Quantum Metal 0.9.0. This is not a mesh or solve.
- Palace WSL CLI handshake PASS (binary version unreported); native Quantum
  Metal, scqubits and JosephsonCircuits.jl tests PASS. Four deep browser
  acceptance tests PASS; isolated wheel installation and HTTP PASS.

## Root causes and changes

The two regressions were introduced by **environment-dependent test assumptions**:

1. `test_no_native_module_no_output` assumed SQDMetal was not installed;
   once installed it proceeded to check a native Palace deck and found a
   **genuine fail-closed material-stack mismatch** instead of the expected
   missing-module exception. The corrected test explicitly substitutes a
   missing native import in the test only. Material checks remain unchanged.
2. `test_unsafe_archive_rejected` used Python `zipfile` to generate a member
   name with a backslash. Windows `zipfile` normalizes this to `/` before the
   archive is written. Therefore the test did **not actually present** the
   malicious filename to the production validator. The test fixture now
   preserves the literal backslash in raw ZIP directory metadata and verifies
   the supplied member name before asserting rejection. The existing
   production ZIP validator already rejects real backslashes; there was no
   demonstrated production bypass and no change to the validation logic.

## Verification on this build host

- Full Python pytest regression: **311 passed, 14 skipped, 0 failed; exit code 0**.
- Source inventory verification: **PASS**, SHA-256
  `7393385249e182552ad737b4740f3ba17da196e6f1d446d2d3003afb553a0ce1`.
- Frozen contract digest remains
  `6ffd28ebea3dcfa815a61c22598733520055d8e2b902c1e7ec5ffd5255f74171`.
- No production code changed. The original `0.1.1.dev13` wheel is preserved
  **byte-for-byte**, SHA-256
  `7aa9106684a9c0d5cfa48b0f9f79191c911aefcf8d57336ff9e96d89a1a6f164`.
- The two corrected tests passed, but the Windows qualification still needs
  to be re-run on the target laptop to verify portability in that environment.

## Next native integrated EDA qualification

Do **not** reinstall SQDMetal, Palace, Julia, Gmsh, Quantum Metal or Chromium.
Once Windows regression is green, use the generic SQE EM editor to create a
revision-bound reviewed CPW study, inspect materials/ports/boundaries and run
native deck-only Gmsh/Palace generation. Retain mesh/deck/hash evidence and
validate both mesh and mode matching before approving a native Palace solve.
A physics expert must review the results and convergence; a CLI handshake is
not independent scientific validation. EPR, geometry optimization and
fabrication release remain blocked pending their own evidence and approvals.
