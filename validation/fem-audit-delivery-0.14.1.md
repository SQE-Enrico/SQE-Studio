# SQE Studio 0.14.1 — Release verification record

Scope: static/source audits, synthetic MSH fixtures, real JSON scientific-report generation without Palace, regression tests and archive integrity checks. No new FEM claim is made without target-hardware solver output.

## Known prior real-hardware result

The earlier v0.14 two-level QPU study completed both solves but did not converge: L0 and L1 projected capacitances differed by roughly 32–47%. This report is the input motivating the v0.14.1 audit, *not* a passed convergence study.

## Added safeguards

- Read-only MSH physical-group and boundary-contract audit; no project access.
- AMR profile limited to a single iteration with a finite DOF cap; explicitly opt-in.
- Hashed Palace CSV energy checks; mismatches are disclosed, never scaled away.
- Original verified diagnostic CSVs included when small, with per-file and aggregate size caps.
- Separate PASS/FAIL/SKIP/WARN outcomes and explicit physical-qualification limitations.

## Not yet demonstrated

- v0.14.1 real QPU MSH audit on Windows Gmsh 4.15.2.
- AMR solve using the user's Palace 0.16 installation.
- Full 3D geometric manifold and electrode connectivity validation.
- Physical QPU capacitance convergence or measured device agreement.

## Verification performed during release creation

- 108 individually executed focused unit tests passed across FEM audit, convergence, scientific diagnostics, benchmark profiles, quantitative results, Python/Quantum Lab, physical and parametric QPU, Palace interop, qualification and related modules.
- Four Studio diagnostic-control tests additionally passed (112 focused tests in total, without counting repeats).
- Python compilation and JavaScript syntax check passed.
- A complete audit-profile report ZIP was generated in the development environment with geometry `PASS` and Gmsh/Palace-dependent stages marked `SKIP`; no fabricated solver results were reported.
- A broader test run stopped during the historical provenance/worker test and cannot be reported as fully passed.
- The development environment could not install Gmsh (network unavailable) or run Palace. Real v0.14.1 native validation is pending on the user's Windows/WSL2 workstation.
