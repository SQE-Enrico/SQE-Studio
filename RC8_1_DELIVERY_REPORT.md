# SQE Studio RC8.1 — Browser qualification evidence-path hotfix

Status: **EXPERIMENTAL — NOT A RELEASE CANDIDATE**.

## Field report analyzed

- Input: `SQE-Studio-qualification-20261030(8).zip` (20 entries, CRC valid, all 19 declared SHA-256 checks valid).
- Target: Windows 11, Python 3.11.9, Playwright 1.64.1 and native Quantum Metal/scqubits installed.
- Comprehensive gates: **9 PASS / 1 FAIL / 6 BLOCKED**.
- Integrated regression: **273 PASS / 9 SKIPPED**. Native Quantum Metal: **5 PASS**; native scqubits: **4 PASS**.
- Installed wheel/build/installed authenticated HTTP acceptance: **PASS**. Real browser smoke: **PASS**.
- Deep browser: **2 PASS / 1 FAIL**. The failing test completed core revision, auth, schematic, layout, fail-closed EM worker, history and Fabrication HOLD checks before raising `ValueError` at `capture.relative_to(ROOT)` when a screenshot was in an external temporary evidence directory.
- This is a qualification **test** defect, not demonstrated product-engine or solver failure. The viewport assertions after the failing logging line have not yet passed on the laptop.

## Change and provenance

- One browser test correction: screenshot logging uses `capture.name`, not `capture.relative_to(ROOT)`. This supports external capture directories and avoids leaking user directories in logs.
- One regression test added: executes viewport audit with a screenshot directory outside the source tree and checks path-safe log output.
- Added developer note `docs/RC_WINDOWS_QUALIFICATION_8_1.md` explaining the field cause, acceptance requirements and scientific limitations.
- Regenerated evolved-source inventory using its own verifier. `FOUNDATION_LOCK.json` and all frozen contracts remain byte-identical.
- All production `src/` files, GUI assets, launchers, dependencies and scientific adapters are **byte-identical to RC8**. Original prebuilt wheel `0.1.1.dev8` is included **unchanged**; no engine, Python or browser reinstall is needed.

## Verification in current host

- New path regression: **1 PASS**.
- Full pytest: **272 PASS, 14 SKIPPED, 0 FAIL** (Python 3.13 host; unavailable native solvers and restricted Chromium are not claimed).
- Evolved-source manifest: **VERIFIED**.
- The core wheel is binary-identical to RC8; it was not rebuilt because production sources are unchanged.
- Real Chromium deep acceptance on Windows still requires retest using the corrected package.

## Persistent RC blockers

- JosephsonCircuits.jl package absent in Julia environment (2 native RF tests skipped).
- SQDMetal/Palace native EM workflow and converged eigenmode/kinetic inductance studies remain incomplete.
- EM/EPR to Hamiltonian, multi-engine geometry optimization and cross-engine RF mapping are not scientifically qualified.
- Experimental measurements, DRC/LVS, PDK and foundry approval are missing. Fabrication remains HOLD.
- Node.js missing on laptop for JS syntax gate (this does not prevent actual Chromium acceptance).

Next step: Use the corrected full source directory and existing connected scientific environment, run `Qualify this laptop > Comprehensive`, share the new ZIP. The browser deep gate must pass *including* the viewport checks before calling it qualified. Do not promote to RC solely based on these software test results.
