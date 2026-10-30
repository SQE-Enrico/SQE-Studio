# RC12.2 — ZIP member validation across Windows and POSIX

**Release qualification: EXPERIMENTAL / NOT RC.**

## Windows qualification evidence

The 2026-10-30 Windows RC12.1 comprehensive report verified all 28 evidence
SHA-256 values. It recorded 13 PASS, 1 FAIL, 5 BLOCKED gates. The integrated
regression ran 313 passing tests, 1 failing test and 7 skipped tests. The only
failure was `test_unsafe_archive_rejected` for a member whose original ZIP name
contains a backslash.

The test inspected `ZipFile.namelist()`, which returns names normalized by
Python's `zipfile` reader on Windows. This meant the test falsely asserted
that the malicious raw member name survived *as a normalized name*.
More importantly, the previous validator inspected only `ZipInfo.filename`,
not its `orig_filename`. That could allow the reader to normalize an unsafe
raw member name before the path validation. It was not sufficient to correct
only the test. Do not downgrade this to a test-only portability bug.

## Fix and invariant

`test_sqdmetal_official_source.py` now checks `ZipInfo.orig_filename`, not
`namelist()`, to confirm the hostile member name is present. It includes an
additional NUL-containing ZIP member test.

`sqdmetal_source._check_zip()` now rejects any mismatch between
`ZipInfo.orig_filename` and `ZipInfo.filename`, as well as backslashes,
NULs, special entries and non-normalized member paths, **before extraction**.
It does not rewrite the archive to repair it and never falls back to an
unchecked source. Commit pinning, SHA-256 checks, download and size limits,
source installation consent and scientific fail-closed checks are unchanged.

This change concerns the standalone desktop scientific-environment installer;
it does not affect native Quantum Metal, SQDMetal, Gmsh, Palace, Julia or
scqubits calculations, frozen contracts, browser authentication or the EDA GUI.
The original `0.1.1.dev13` wheel is preserved because this installer is not
included in the wheel's `src/` package.

## Remaining RC qualification

The source inventory must match this evolved tree. Run the full regression
on the target Windows 11 laptop; the Linux host's tests cannot establish
Windows acceptance. The native QDesign -> Gmsh mesh -> Palace solve and
convergence are **not yet qualified** despite import/CLI PASS gates.
Reviewed materials, ports, boundary conditions and mesh are required.
EM-to-Hamiltonian, closed-loop geometry optimization and fabrication approval
remain BLOCKED. Do not infer native scientific qualification from these fixes.
