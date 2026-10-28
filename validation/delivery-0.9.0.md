# Delivery QA — SQE Studio 0.9.0 (28 October 2026)

## Scope

This increment **does not claim a Palace FEM solve** or a Julia harmonic-balance simulation. It adds one-click diagnostic reporting to capture real Windows/WSL failures without shipping projects or raw system logs. No upload occurs. Supported launch: `WINDOWS-DIAGNOSTICS.cmd [-Extended] [-SkipTests]`; direct portable launch: `python scripts/collect_diagnostics.py`.

## Evidence executed in Linux development container

- Baseline full application regression: `python -m unittest discover -s tests -p test_*.py -q`: **118 tests run, 0 failed, 4 optional skipped** (includes 8 diagnostic privacy/packaging tests).
- Diagnostic regression: `test_diagnostics.py`: **8 tests pass** including timeout, ZIP allowlist, SHA-256 verification, credential removal, non-collection of project data and scrubbed error output.
- Real diagnostic collector on Linux: **51 curated smoke tests pass** (11 Quantum Lab, 10 physical QPU, 15 parametric, 7 Palace quality/Julia contracts, 8 diagnostic tests), report ZIP generated and checked. Missing optional Gmsh/Julia report warnings, not false positives.
- Source scripts syntax checked via Python compile. Diagnostic schema version `sqe-diagnostics/1`, output ZIP contents fully allowlisted and read-back verified.
- Generic Windows components (PowerShell, WSL, Julia, Palace, Windows user profile, Gmsh native API) **NOT exercised on actual Windows** here. This is the explicit purpose of the user-run feedback cycle.
- Reproducing full CI via captured stdout/PIPE could hang because child worker processes inherit pipe handles. **Corrected** by limiting diagnostic runs to named contract modules, fixed timeouts and file-based capture; do not reintroduce the full CI invocation in the diagnostic runner.

## Required first-user acceptance on a real Windows 11 workstation

1. Before installation, `WINDOWS-DIAGNOSTICS.cmd` must produce either full diagnostic ZIP or PowerShell fallback ZIP, without elevation.
2. After `WINDOWS-FIRST-START.cmd`, run the same command and compare `checks.json` changes.
3. Run `WINDOWS-DIAGNOSTICS.cmd -Extended` and confirm a real Gmsh 3D unit-box mesh (if Gmsh is installed); if Ubuntu WSL2 is present, it must detect a Bash shell and Spack/Palace availability.
4. Manually inspect `test-results.txt` for unintended sensitive text before sharing. The collector's scrub is a mitigation, not a guarantee.
5. Confirm that no `studio-data` or QPU projects appear in the ZIP. Independently confirm WSL2 solver installation success using the Palace wizard. This release does not execute a Palace sample solve.

## Out of scope and remaining risks

- PowerShell syntax and Windows Installer/error-code behavior not tested in an actual Windows VM or PC.
- `Spack` status is presence/installed-package inspection, **not** solver validation; full build errors are not automatically included in this first feedback ZIP.
- No user project data, raw environment variables, IP addresses, machine names, user directories, Windows Event Logs, system serials, or installer output logs are automatically collected.
- On Windows, an anti-virus, a corporate execution policy, an unavailable Python launcher, or a non-initialized WSL distro may prevent a check. Such cases should produce a WARN/fallback ZIP; rare PowerShell launch failures may still require a screenshot of the terminal.
