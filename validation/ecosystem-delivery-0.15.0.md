# SQE Studio 0.15.0 — release acceptance record

Date: 2026-10-28. Core interpreter: Python 3.13.5 on Linux.

## Executed locally

| Check | Result |
| --- | --- |
| Initial all-module pytest regression | **172 passed, 4 skipped**, plus 18 pytest subtests; completed in 45.27 s |
| Focused legacy Palace/QPU audit + ecosystem regression | **35 passed**, 5.33 s |
| Current new ecosystem contract tests | **11 passed** (`python -m unittest -q tests.test_ecosystem_v015`) |
| End-to-end generic 1Q sample | **3 steps completed** (modes, RF sweep, Josephson SI export), `ecosystem verify` passed |
| Module import/compilation, JSON/TOML examples | Passed locally |
| Later full-suite re-run after additional changes | **Incomplete due to timeout**; no pass claim |

The local executable stack does **not** contain `SQDMetal`, `qiskit_metal`,
`scqubits`, `julia`, `gmsh`, or native `palace`. External calls are therefore
covered by **mocked public API boundary tests, not by third-party solver
execution**. The 11 new tests include anti-traversal/symlink checks, tamper
checks, optional-package refusal, plugin registration, and fake linear Julia /
SQDMetal handoff. No real external result accuracy or FEM convergence is proven.

## Separate scientific qualification required

1. Python 3.11 Quantum Metal + SQDMetal environment: verify a real QDesign
   factory, Gmsh boundary/mesh attributes, prepared and run Palace models;
   compare extracted C with independent capacitors and analytic references.
2. Julia environment: execute a fixed linear 1-port reference over a defined
   frequency grid, verify complex S against a known passive LC model; then
   qualify separate pumped nonlinear/harmonic-balance workflows.
3. scqubits: compare charge-basis spectra and custom-Circuit YAML against
   independent operators, truncation sweeps and energy-unit crosschecks.
4. Palace QPU: repeat two **independent** mesh refinements and geometry/
   terminal audits on the real Windows/WSL workstation. The existing 0.14.1
   discrepancy is **not resolved** by this software architecture release.
5. ADS QuantumPro-level readiness: validate electrical/physical interchange,
   losses, package effects, DRC/LVS, calibrated measurements, project UX,
   security and sustained multi-OS CI before any equivalence claim.

## Compatibility

No original files were deleted. Legacy Web Studio projects, `.sqe.zip`
fixtures, `sqw run`, `sqw stage`, Palace diagnostic profiles and their test
cases remain in the source archive. New ecosystem workflow is an independent
opt-in CLI path, not silently inserted into historical scientific flows.
