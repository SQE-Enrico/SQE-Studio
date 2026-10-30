# SQE Studio — Windows RC stabilization round 7

**Delivery:** complete experimental source distribution with desktop launcher and offline-verifiable Python wheel `0.1.1.dev7`.
**Status:** EXPERIMENTAL / BLOCKED_NOT_RELEASE_CANDIDATE.
**Baseline:** `SQE-Studio-Windows-field-fixes-EXPERIMENTAL.zip`.
**Trigger:** real Windows 11 qualification `(6)`; its integrated suite reported 263 PASS, 2 FAIL, 9 SKIPPED, with 5 PASS / 4 FAIL / 7 BLOCKED qualification gates.

## What changed

- Generic EM editor no longer wires handlers of absent study settings when there are zero saved EM studies. Browser tests now use the current `newEMStudy` control and the selected study ID; a dedicated GUI test covers zero/one/two studies and deletion.
- Native composite scqubits 4.3.x only: a *scoped* bridge converts SciPy sparse arrays to equivalent sparse matrices at the upstream internal operator-conversion boundary. Upstream function is restored after the solve, including failure. Other solver output, Hamiltonian elements, physical units, input validation and solver convergence remain unchanged. Native correctness on the Windows field environment is **not yet established**.
- Native-worker lifecycle regression waits a bounded 55 seconds for startup, then requests cancellation and fails explicitly; production solver timeout is unchanged.
- Offline wheel/provenance and installed HTTP/UI smoke are now independently reported with separate failure stdout/stderr and exit codes. A verified wheel does not override an HTTP FAIL.
- Adversarial HTTP regression now tolerates an expected TCP close after sending a rejection response, while still asserting the exact response status.
- Build identity is now the explicit development version `0.1.1.dev7` (Windows wheel installer references updated); frozen contracts and historical foundation lock remain unchanged. Generated `release/` packages are outside the **source** inventory and covered by the delivery-level archive hashes.

## Verification performed here

- Evolved source inventory verified, with unmodified frozen contracts.
- Offline local regression: **266 PASS / 0 FAIL / 11 SKIPPED**; native Quantum Metal, scqubits and Julia are missing in this host environment. These are not native validation results.
- JavaScript syntax validated via Node.js.
- Browser Playwright acceptance: **3 SKIPPED** because this managed host blocks Chromium navigation to local HTTP (URLBlocklist). No browser PASS is claimed.
- Two reproducible wheels have identical SHA-256. A freshly isolated Python virtual environment installed the new wheel, verified its version and actual imported server bytes, and successfully executed authenticated localhost HTTP, CSRF, project revision and GUI asset smoke.
- A host Quick qualification completed earlier in development; a final repeated Quick qualification did **not terminate within the execution deadline** and is **not claimed** as a completed qualifying run. Independent full regression/build/HTTP checks above did finish. This warrants follow-up if reproduced.

## Laptop instructions (no terminal)

1. Keep the existing scientific Python 3.11 environment and installed Quantum Metal, scqubits, Gmsh and Chromium; there is no reason to reinstall them for this source patch.
2. Back up the existing `SQE-Studio` folder and extract this complete archive in a clean folder. Open `SQE-Studio/Launch SQE Studio.pyw`.
3. If needed, use **Reconnect existing scientific environment** to select the previous environment without downloading it again.
4. Choose **Qualify this laptop → Comprehensive**, save the generated report ZIP and share it after reviewing any local path details.
5. Inspect independent gates `integrated_regression`, `browser_deep_acceptance`, `native_scqubits`, `installed_wheel` and `installed_assets`. A native solver listed as installed is not enough to mark it validated.

## RC remains blocked by

- Actual composite scqubits 4.3.1/installed SciPy spectrum and convergence tests on the Windows laptop, and deep real-browser acceptance on that host.
- SQDMetal/Gmsh/Palace native eigenmode/deck solve, mesh convergence, reviewed kinetic sheet boundary, mode matching and EM-to-EPR/Hamiltonian edges.
- JosephsonCircuits.jl native Julia environment and RF/HB qualification.
- Genuine multi-engine CAD → EM → physically typed circuit → objective-driven geometry feedback and benchmark/measurement comparisons.
- Independent security testing, PDK, DRC/LVS, foundry review and fabrication approval. **Fabrication HOLD**.

Engineering rules and benchmarks remain under `SQE-Studio/docs/DEVELOPER_PRINCIPLES.md`, `EDA_EXTENSION_ARCHITECTURE.md`, `SCIENTIFIC_DESIGN_CASES.md`, and `RC_WINDOWS_QUALIFICATION_7.md`. This is one generic integrated EDA application, not a separate experiment viewer or a CLI workflow.
