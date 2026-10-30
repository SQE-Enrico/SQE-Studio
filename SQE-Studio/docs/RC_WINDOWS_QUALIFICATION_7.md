# RC candidate engineering: Windows qualification round 7

**Version status:** EXPERIMENTAL / NOT RELEASE CANDIDATE. This is a product source update, not a numerical validation, solver certification, foundry approval or general QuantumPro-equivalent release.

## Package identity

The installable Python core uses **0.1.1.dev7**, explicitly a development version. The original foundation lock and historical product foundation manifest remain unchanged. The build and Windows offline scripts now target this exact development wheel, rather than silently reusing the old 0.1.0 distribution. The generated `release/` wheel is excluded from the **source** inventory and is checked independently by its SHA-256 sidecar and the ZIP delivery manifest. Source launch and the existing managed Python 3.11 environment remain supported.

## Reproducible input evidence

This patch was made against `SQE-Studio-Windows-field-fixes-EXPERIMENTAL.zip` and the user's sixth Windows 11 qualification bundle (`SQE-Studio-qualification-20261030(6).zip`). The field bundle recorded 263 passed, 2 failed and 9 skipped regression tests, with a separate 5 PASS / 4 FAIL / 7 BLOCKED qualification outcome. Quantum Metal native geometry/GDS checks passed; installed scqubits 4.3.1 failed the composite sparse-array conversion; Chromium launched, but deep GUI acceptance failed; installed wheel provenance passed while its following HTTP gate failed without diagnostic stdout.

## Source changes and physical invariants

1. **Generic EM editor:** Its study selector and *New study* control exist even when no EM study exists; settings, port and run controls do not. Only wire those handlers when an actual study is selected. The generic browser acceptance now uses `#newEMStudy` and references the actual saved study ID rather than a retired fixed identifier. A missing reviewed material/port/solver mapping remains BLOCKED; no simulation or experimental claims are introduced.
2. **Composite scqubits/SciPy compatibility:** scqubits 4.3.x rejects `scipy.sparse.csc_array` in its *own* `HilbertSpace` bare-Hamiltonian conversion boundary. During a **composite native worker solve only**, replace this conversion function with a representation-only wrapper that changes SciPy sparse arrays into `csc_matrix` before passing them to the upstream converter. Numeric matrix elements, shape, dtype, subsystem, eigenbasis flag and eigenvectors are preserved. Restore the original function even on exceptions. The existing separate bound-operator bridge is retained. This is a narrowly scoped compatibility shim, **not** an independent eigenvalue or physics validation. Never use it to replace native results with fixture data; the actual laptop test must pass for scientific acceptance.
3. **Windows startup timing:** Native worker Python imports can exceed four seconds. A regression test now uses a bounded monotonic 55-second deadline with cancellation and an explicit failure on timeout. Production solver time limits remain unchanged.
4. **Installed package acceptance:** The offline wheel build, isolated install and byte/provenance validation are distinct from the installed-wheel authenticated HTTP smoke. Record stdout/stderr, return code and timeout of both operations, and never treat a verified wheel as proof of a successful server/UI workflow.

These changes are within the existing integrated EDA architecture. They do not alter the frozen project schema, native Quantum Metal/GDS adapter, EM solver, material physics, or any artifact approval gate.

## Laptop requalification — GUI only

1. Do **not** reinstall Python, Playwright/Chromium, Quantum Metal, Gmsh, scqubits, or Julia just for this source update.
2. Back up the previous `SQE-Studio` folder; extract the updated complete ZIP into a fresh folder.
3. Launch `Launch SQE Studio.pyw`. If the existing Python 3.11 environment is no longer connected, choose **Reconnect existing scientific environment**; do not recreate it.
4. Choose **Qualify this laptop → Comprehensive**. Share the newly created ZIP, after reviewing its redacted logs.
5. Specifically review `browser_deep_acceptance`, `native_scqubits`, `integrated_regression`, `installed_wheel` and `installed_assets`. Failures are actionable, and missing solver dependencies remain `BLOCKED` rather than `PASS`.

## Remaining RC blockers

- Re-run **real** scqubits 4.3.1 composite Hamiltonian and fluxonium/Transmon native regression on Windows; compare numerical transitions to a reference and basis convergence. Unit and provenance checks must remain explicit.
- Verify the deep Chromium workflow for zero, one and multiple EM studies with zero page errors, preserving fail-closed execution requirements. Keep the actual downloaded worker failure evidence.
- Determine the installed-wheel HTTP failure from the new log, rather than treating its absence as a packaging failure.
- Julia's `JosephsonCircuits.jl` and SQDMetal/Gmsh/Palace native deck/solve remain unavailable or not qualified. Native EM-to-quantum/EPR, kinetic sheet comparisons and objective-driven design optimization remain blocked.
- Full CAD → EM → verified extraction → circuit/quantum → target evaluation → geometry feedback, convergence, external benchmark and PDK/DRC/LVS/foundry approval are not established. Fabrication remains HOLD.

**References:** scqubits 4.3.x published operator conversion implementation: https://scqubits.readthedocs.io/en/latest/_modules/scqubits/utils/spectrum_utils.html ; source releases: https://github.com/scqubits/scqubits/releases . This local bridge must be removed when validated upstream SciPy sparse-array compatibility is available.
