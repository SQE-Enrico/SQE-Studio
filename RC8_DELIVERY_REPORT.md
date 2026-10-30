# SQE Studio — RC8 Windows qualification corrective build

**Status: EXPERIMENTAL — NOT RC.** Version `0.1.1.dev8`.

This release responds to the user-supplied and SHA-256-verified `SQE-Studio-qualification-20261030(7).zip`. The RC7 laptop result was 6 PASS, 4 FAIL and 6 BLOCKED gates. Integrated regression: 267 passed, 1 failed, 9 skipped; browser deep: 2 passed, 1 failed; Quantum Metal: 5 native tests passed.

## Targeted fixes

- Composite scqubits 4.3.1: handle the native `Qobj -> csc_array` conversion path in the narrowly scoped sparse-compatibility boundary, in addition to direct sparse arrays. Native numerical data and eigensolver remain unchanged. A Windows native rerun is mandatory to confirm this fix.
- Installed wheel HTTP test: release SQLite database handles as soon as transaction context managers finish, including on errors. This targets `WinError 32` at test-workspace deletion.
- Fabrication UI: separate native CAD GDS export (still available from the Layout editor) from fabrication signoff (read-only HOLD and disabled). Independent PDK, DRC/LVS and foundry approval remain mandatory.
- Added unit tests for Qobj sparse conversion, numerical preservation, SQLite handle closure and fabrication HOLD behavior. Frozen contracts and baseline provenance are unchanged.

## Checks completed in this build environment

- `pytest -q` with production source on PYTHONPATH: **271 passed, 14 skipped, 0 failed**. This includes software and fixture tests, NOT a native scqubits composite acceptance on Windows.
- Node JavaScript syntax: PASS.
- Evolved source inventory and frozen contract digest: PASS.
- Two wheels built under fixed SOURCE_DATE_EPOCH: byte-identical. Wheel SHA-256: `9462418e0bda47b81ca60c4a6157075b4c629ff86514d8205075fac0e6b40c2f`.
- Installed-wheel HTTP smoke in an isolated interpreter: PASS (authentication, CSRF, local HTTP, CPW template, revision conflict and logout).
- No native scqubits, Quantum Metal, Palace, SQDMetal, Julia, Chromium deep test, Gmsh meshing, EM solve, EPR extraction, optimizer or foundry validation was executed in this build environment.

## Next Windows RC8 acceptance

Keep the existing Python 3.11 environment and native packages. Unpack RC8 separately, reconnect the existing scientific environment if needed, and choose **Qualify this laptop > Comprehensive**. Required improvements: integrated regression, native composite scqubits, deep browser HOLD, installed-assets cleanup. Preserve BLOCKED for SQDMetal/Palace, JosephsonCircuits.jl if not installed, versioned EM->Hamiltonian, native geometry optimization and foundry qualification. Do not bypass any physical or security gate to make a test green.

Use `SQE-Studio/docs/RC_WINDOWS_QUALIFICATION_8.md` for the defect-by-defect engineering note.
