# SQE Studio 0.17.0 — Validation Record

**Date:** 2026-10-28  
**Scope:** unified browser navigation, administrator-only engine provisioning, setup ZIP export, unchanged Palace/Studio research contracts.

## Completed local checks

| Check | Result | Evidence |
| --- | --- | --- |
| Existing multi-engine Web API regression | PASS, 6 tests | `tests/studio/test_web_experiments_v016.py` |
| New unified Web / dependency management / security regression | PASS, 5 tests | `tests/studio/test_unified_workspace_v017.py` |
| Studio project/worker regression | PASS, 15 tests | `tests/studio/test_studio.py` |
| Diagnostic API regression | PASS, 6 tests | `tests/studio/test_diagnostic_control.py` |
| Ecosystem and Palace scientific unit/audit regression | PASS, 36 tests | `tests/test_ecosystem_v015.py`, `test_palace_quality.py`, `test_fem_audit_v0141.py`, `test_qpu_convergence_v014.py` |
| Browser layout render for Project, Setup and Run | PASS in mocked-data browser render | Headless Chromium/Playwright, no JavaScript exceptions (not a live integrated browser test) |
| JavaScript syntax check | PASS | `node --check src/sqw/studio/static/workspace.js` |
| Python syntax | PASS | Python compileall on the Studio package |

**Focused total:** 68 unit/integration tests passed across the above groups. These are software-contract checks, not external FEM solver validation.

**Incomplete check:** a separate attempt at the unrestricted `unittest discover -s tests` suite exceeded the available 180-second execution window and has no full-suite PASS claim. The focused suites above were rerun separately and passed. The previous version's reported 187-test run is not presented as evidence of a complete v0.17.0 regression.

## Not tested in this environment

- Live PyPI/Git/Julia downloads and provisioning on a Windows workstation.
- SQDMetal QDesign-to-Palace end-to-end mesh/solve, and COMSOL licensing or native availability.
- Real Julia JosephsonCircuits harmonic-balance or linear-sweep accuracy.
- Palace/WSL native multi-QPU convergence and independent fabricated-device measurements.
- A full authenticated browser smoke test over a real local socket: the browser execution environment blocked navigation to loopback. The replacement visual test used mocked API data; it does not prove runtime deployment.

## Qualification rules

- **Ready** for an engine means post-install import or small API smoke test passed.
- **Completed/partial** for provisioning records the availability and failures of each optional package.
- **COMPUTED / INTEGRITY_VERIFIED_ONLY** identifies artifact production or SHA-256 verification, not scientific validation.
- Failed installation and worker runs retain evidence and can export one support ZIP.

## Privacy/security controls

Only local workstation administrators with an authenticated CSRF-protected session can install optional engines or run external scientific workflows. Installer targets and options are fixed, imports accept only declarative input files, commands do not pass through a shell, and the browser cannot request arbitrary package installations. Support ZIPs must be manually downloaded and reviewed before sharing. External packages may themselves execute trusted installer/build scripts and require network access.
