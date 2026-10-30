# RC8 Windows hardening — field qualification follow-up

Status: **EXPERIMENTAL / NOT RELEASE CANDIDATE**. The Windows field report `SQE-Studio-qualification-20261030(7).zip` is the basis for these fixes. Its 18 evidence-file hashes were verified before diagnosis.

## Observed field failures (from RC7)

- Integrated regression: 267 passed, 1 failed, 9 skipped. The failure was scqubits 4.3.1 `TypeError: Unsupported operator type: scipy.sparse.csc_array` during *native composite coupling*. The independently executed scqubits gate reproduced the same error. These are two gate failures from one scientific interoperability defect.
- Browser deep acceptance: 2 passed, 1 failed. `fabricationRun` was enabled when native Quantum Metal was installed, even though the fabrication handoff was marked HOLD. The native GDS workflow belongs in the Layout editor, not a fabrication-release control.
- Installed wheel: installation and package byte verification passed, and the installed HTTP smoke reported PASS, but Windows failed to delete a temporary `studio.sqlite3` (WinError 32) because a database handle could remain open after transaction context exit.
- Julia's native package is unavailable; SQDMetal / Palace, EM-EPR extraction, geometry optimization, and foundry qualifications remain blocked.

## Code changes

1. **scqubits adapter:** for 4.3.x composite `Qobj` inputs, invoke the same upstream `Qobj_to_scipy_csc_matrix` converter before the already-scoped sparse-array-to-matrix compatibility conversion. This handles the `Qobj -> csc_array` path seen in the field log. Only the storage type is normalized; values, basis, units, Hamiltonian parameters and scqubits eigenproblem remain native. The original upstream converter is restored after each native call. Regression tests assert type, shape, dtype, matrix elements, eigenvalue identity for an isolated test matrix, and restoration on error. Native acceptance on Windows is **not established** until a new laptop report passes.
2. **Store transactions:** SQLite connections opened in `with store.conn()` now explicitly close on commit or rollback. This should release Windows file handles before the installed-wheel HTTP test deletes its temporary workspace. The HTTP acceptance must be rerun on Windows; no success is inferred from a Linux test.
3. **Fabrication GUI:** the Fabrication step is permanently HOLD/read-only pending reviewed PDK, independent DRC/LVS, mask rules and signoff. The action button is disabled regardless of whether Quantum Metal is installed. CAD-only GDS generation remains available through the ordinary Layout step with the existing revision-bound controls.
4. Version upgraded to `0.1.1.dev8` to avoid confusion with the RC7 wheel. Frozen foundation contracts and historical agent evidence are unchanged.

## Software and scientific gates

Re-run `Qualify this laptop > Comprehensive` using the existing connected Python 3.11 environment. A result is not an RC until the integrated regression, browser deep acceptance, installed-assets HTTP, and native scqubits composite checks **pass on Windows**. The qualification must continue to report the missing Palace/SQDMetal/Julia package and unimplemented EM-to-quantum and geometry optimization edges as BLOCKED. Do not infer physical or foundry qualification from any software pass.
