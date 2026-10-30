# SQE Studio RC12.2 — Windows ZIP name validation fix

**Status: Experimental / Blocked — NOT RELEASE CANDIDATE.**

## Verified laptop RC12.1 evidence (2026-10-30)

The submitted comprehensive qualification ZIP had 28 of 28 evidence hashes
verified, 13 PASS gates, 1 FAIL gate, and 5 BLOCKED gates. The integration
regression reported 313 passed, 1 failed, 7 skipped. The sole failure was
`test_unsafe_archive_rejected` for a raw ZIP member name containing a
backslash. Browser, installation/wheel, Julia/JosephsonCircuits, Quantum Metal,
scqubits, SQDMetal API handshake and Palace CLI checks passed. These are
bounded tests, not a successful EM solve.

## Root cause and security fix

Python's `zipfile` can normalize member name separators on Windows. RC12.1
already rewrote the fixture's ZIP name bytes correctly, but incorrectly
asserted its name against `ZipFile.namelist()` (the normalized representation).
More importantly, the product source validator used only
`ZipInfo.filename` and therefore could fail to reject an unsafe *original*
member name on Windows. Both issues are fixed: the test verifies
`ZipInfo.orig_filename`, and `sqdmetal_source._check_zip` requires the
original and normalized names to be identical, in addition to its existing
fail-closed path checks. Regression tests cover a hostile backslash, a
NUL-terminated member name, and simulated Windows `zipfile` normalization
on POSIX.

No network request, pip install, user project modification or native solver
execution is performed by these tests. No scientific solver models, GUI EDA
flows, frozen contracts, material, authorization or fabrication rules changed.

## Local tests and qualification boundaries

- Focused setup, ZIP provenance and reconnect regressions: **35 passed, exit 0**.
- Source integrity inventory check: **PASS**.
- A full host pytest run before the final added Windows normalization test
  printed **312 passed, 14 skipped**, but its shell process did not exit
  cleanly before the runner timeout. This is NOT recorded as a completed
  full-suite acceptance, and the final added test was not in that run.
- Windows 11 RC12.2 regression: **NOT RUN**. Must be executed on the laptop.
- Native QDesign-to-Gmsh mesh-to-Palace deck and solve: **NOT RUN**.
- EM/EPR/Hamiltonian edge, objective-driven geometric optimization and
  independent foundry validation: **BLOCKED**.

## Distribution

The source-only workstation setup validator and its tests/docs are modified.
The distributed `0.1.1.dev13` wheel remains **byte-identical** to RC12.1,
because the top-level workstation installer is not shipped inside the wheel.
All installation/solver configuration remains in place on the laptop. Do not
reinstall SQDMetal, Palace, Julia, Quantum Metal, Gmsh or Chromium.

## Next target-laptop action

Unpack RC12.2 into a separate directory, reconnect the existing Python 3.11
scientific environment if needed, then run `Qualify this laptop` with the
Comprehensive profile. Preserve the report ZIP and verify the source integrity
gate. Once Windows regression is green, conduct an explicitly reviewed
CAD-to-native-mesh-and-deck test through the generic GUI. Fabrication remains HOLD.
