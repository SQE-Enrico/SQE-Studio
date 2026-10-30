# RC12.1 — Windows qualification portability and native EM readiness

Status: **EXPERIMENTAL / NOT RELEASE CANDIDATE**.

## Evidence from the 2026-10-30 Windows RC12 comprehensive report

The submitted qualification archive passed its 28 declared evidence SHA-256 checks.
The laptop reported 13 PASS, 1 FAIL, 5 BLOCKED gates. The integrated suite
reported 312 passed, 2 failed, 7 skipped. The native SQDMetal API probe passed:
`SQDMetal 0.0.1.dev1`, `gmsh 4.15.2`, and `Quantum Metal 0.9.0` were imported.
Julia/JosephsonCircuits, scqubits, Palace CLI through WSL and real browser acceptance
also passed their separately scoped gates. No native EM mesh/deck/solve was executed.

## Two cross-platform regression corrections

1. A test of the *missing SQDMetal module* now explicitly substitutes a missing
   `require_module` dependency. Previously it only succeeded when SQDMetal was
   absent; on a provisioned laptop the test instead proceeded to physical deck
   validation and could fail on a material mismatch. The physical deck validator
   and its fail-closed material checks have **not** been altered.
2. A hostile ZIP member-path fixture now preserves the backslash byte in local
   and central-directory ZIP headers, even when Python's Windows `zipfile`
   writer normalizes separators. It asserts the archive really contains the
   malformed name. The product's ZIP validator already rejected actual
   backslash member paths and was **not** relaxed or changed.

Neither fix affects production adapters, solver models, installation logic,
GDS artifacts, auth, frozen contracts or the packaged wheel. They correct test
reliability across installed and uninstalled Windows scientific environments.

## Next scientific acceptance gate

Use the normal EDA GUI to create or select a reviewed CPW design, confirm the
physical substrate/metal/superstrate parameters, ground, boundary conditions,
CPW ports and mesh refinement plan, then run the actual `deck_only` step with
SQDMetal/Gmsh. Preserve the real `.msh`, Palace `.json` and source-revision/
SHA-256 evidence. Only after a physicist approves the setup should the solver
run be enabled, with a second mesh resolution for an explicit convergence
comparison. No unreviewed material constants or fabricated solver output are
permitted. The EM-to-Hamiltonian and geometry optimization edges remain blocked.
