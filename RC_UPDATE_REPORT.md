# SQE Studio — Windows 11 RC Stabilization Update

**Delivery status: EXPERIMENTAL / NOT RELEASE CANDIDATE**

This is a complete source+desktop launcher+wheel update based on the last
`SQE-Studio-environment-reconnect-EXPERIMENTAL.zip` and analyzed against the
user's 2026-10-30 comprehensive laptop qualification. It is not a new foundation
baseline, scientific solver certification, or foundry approval. No frozen
contracts were changed.

## Verified corrections and hardening

1. Quantum Metal 0.9 QNet endpoint pairs: each terminal is checked against
   its corresponding native route pin, rather than falsely requiring a single
   net id across both ends. Missing or mismatched connections are rejected.
2. SciPy `sparray` to `csc_matrix` conversion only for scqubits composite
   operators, with exactly preserved values and bound subsystem identity.
   Native scqubits spectra still need validation on Windows 11.
3. Native Palace experimental kinetic-deck bytes agree with their SHA-256 on
   Windows regardless of newline defaults.
4. GUI tests explicitly read UTF-8 and wait for saved revision consistency
   between the display and authenticated server response.
5. Native-job scheduler releases exclusive slot before publishing a terminal
   state, preventing immediate retry races.
6. Previously environment-dependent no-native test now verifies real native
   result manifests when scqubits is installed rather than requiring failure.
7. Qualification installs the newly built wheel with `--force-reinstall` in a
   temporary virtual environment, validates package location and byte identity,
   then performs real HTTP auth/revision/UI smoke.
8. Failed job and Julia-native tests collect bounded, sanitized logs from
   the qualification's own test workspace only (not user projects).

## Actual evidence on this build host

- Full integrated nonbrowser regression: **261 passed, 11 skipped, 0 failed**.
- Node.js JavaScript syntax: PASS.
- Evolved source inventory and frozen contract digest: PASS.
- Two wheel builds with SOURCE_DATE_EPOCH fixed: identical SHA-256.
- Isolated installed wheel provenance verification: PASS.
- Installed-wheel local HTTP, authentication/CSRF, stale revision rejection,
  CPW starter model and UI static resources: PASS.
- Real Chromium deep browser acceptance on this host: SKIPPED (managed
  URLBlocklist). Browser success on the user's previous report does not prove
  the newly modified deep tests pass until rerun on Windows.
- Qualifier quick profile: **4 PASS, 0 FAIL, 12 BLOCKED** (by profile or host).
- A local attempt at Comprehensive did not complete within the execution time
  budget; it is **not** counted as a passed test.
- No native Quantum Metal, scqubits or Julia scientific solver verification
  was performed here (missing engines).

## Remaining blockers

- Re-run all native Quantum Metal, scqubits and Julia tests on the user's laptop;
  use preserved native stderr and failure evidence for remaining failures.
- SQDMetal/Palace mesh/deck/eigenmode and convergence not yet available.
- EPR→Hamiltonian mapping, reviewed material kinetic inductance and iterative
  multi-engine design optimization remain unqualified or incomplete.
- No independent reference-benchmark convergence, PDK/DRC/LVS signoff or
  fabrication approval. **Fabrication HOLD**.

## User instructions (no command line)

1. Keep the current scientific environment, Python 3.11, Playwright, Chromium
   and native libraries; do not reinstall them.
2. Back up your current SQE-Studio folder. Extract the complete ZIP to a new
   location and open `SQE-Studio/Launch SQE Studio.pyw`.
3. If not selected automatically, use `Reconnect existing scientific environment`
   and point to the existing Python 3.11 environment.
4. Open `Qualify this laptop → Comprehensive` and attach the resulting ZIP.
   The report now includes captured worker/Julia error details from isolated tests.

The desktop application is still an evolving integrated EDA environment, not
an experiment registry or an RC. Scientific functions remain fail-closed.
