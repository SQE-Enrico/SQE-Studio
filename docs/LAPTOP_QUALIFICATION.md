# Laptop qualification and evidence handoff — integrated EDA release gates

**Status:** release engineering / diagnostic procedure. It is **not** another solver, scientific workflow, experiment registry or per-example user interface. It exercises the same project model, installed adapters, authenticated HTTP server and browser as the production integrated EDA application. Tests never replace native engine calculations with a purported solver result.

## No-terminal procedure (Windows laptop)

1. Extract the **complete** SQE Studio source package into a normal folder. Ensure Python with Tkinter is available. If Python 3.11 x64 is not detected, use **Prepare scientific environment** to see the installation guidance. Double-click **`Launch SQE Studio.pyw`**. Do not run the app as administrator and do not expose its local HTTP port to the LAN.
2. In the desktop window choose **Qualify this laptop**. Pick **Comprehensive** for the most useful handoff. Pick **Quick** only for a shorter software-only check; unexecuted gates will be `BLOCKED`.
3. Click **Run tests and save report**, choose an ordinary local folder (outside the SQE Studio source), and let the in-app progress view complete. The program asks you where to save a single `SQE-Studio-qualification-YYYYMMDD.zip` file. A solver may take time or time out; a dependency or browser block is reported rather than hidden.
4. Inspect `SUMMARY.md` and `QUALIFICATION.json` inside the ZIP. **Share only that generated qualification ZIP** with the developer. It contains minimized logs and OS/toolchain descriptors, not your projects. Review it before sharing because textual logs undergo best-effort redaction, not a guarantee of anonymity.
5. Also report, separately if relevant, which design case you tried manually, whether the actual mesh and port identities were reviewed, and whether you have native solver result archives. **Do not share project IP, raw results or material process recipes without permission**; this automatic qualification never collects them.

**Dependency setup:** The tester never downloads executables or installs packages. A separate, explicitly consented GUI action **Prepare scientific environment** can provision a private Python 3.11 toolchain with selected Python packages and (optionally) Chromium. It does not install Palace, Julia or unreviewed SQDMetal source. See [Windows workstation setup](WINDOWS_WORKSTATION_SETUP.md). Optional tools (pytest, Playwright, Chromium, Node.js, Python wheel/build backend, Quantum Metal, scqubits, Julia/JC, SQDMetal, Gmsh and Palace) must be installed independently using reviewed instructions. A missing tool is `BLOCKED`, not `PASS`. Package installation checks use only an isolated temporary virtual environment and an offline wheel built from the current source.

## Test matrix (what actually runs)

| Gate / layer | Automatic action | What PASS proves | What it does **not** prove |
|---|---|---|---|
| Source integrity | Hash current source inventory and immutable foundation contracts | This extracted tree matches its declared extended-source inventory | Signed provenance or original scientific qualification |
| Static + regression | Python source AST, Node JavaScript syntax if present, complete pytest excluding separate browser test | Software/contracts/security/HTTP tests pass on this runtime | Independent native solver correctness; skipped test coverage |
| Real browser | Playwright + actual Chromium/compatible browser; quick smoke then full authenticated GUI tests with keyboard, revision, security, failed native archive and viewport checks | Real installed GUI and deep browser tests in the target browser | Windows/GPU portability beyond the host; native EM solution |
| Wheel deployment | Offline build from **current** source; offline install in temp venv; installed HTTP/auth/CSRF/revision/CPW starter and UI assets | A built package works independently of the source PYTHONPATH | A signed Windows installer or any scientific solver |
| Quantum Metal | Existing native QDesign/GDS regression, only if installed | Native generator path and inspected QGeometry/GDS assertions execute | Foundry DRC/LVS or geometry ↔ EM alignment across all devices |
| scqubits | Native transmon, fluxonium, flux sweep and composite regressions when installed | Real eigenenergy output and explicit basis checks | Hamiltonian values extracted from EM, measurements |
| JosephsonCircuits | Native Julia adapter tests if Julia available | The test assertions actually executed; skipped native tests are BLOCKED | Fully validated nonlinear RF ports, harmonics or pump modeling |
| SQDMetal/Gmsh/Palace | Toolchain detection and a blocked scientific-gate entry | Nothing about scientific solver execution | Automated unsupervised Palace acceptance is **not** claimed |
| Closed-loop scientific gates | Unimplemented edges and independent validation explicitly audited | Prevents premature RC promotion | EPR conversion, sheet impedance, geometry optimization, PDK/DRC/LVS |

The native EM gate stays `BLOCKED` even when Palace exists: running an arbitrary geometry with implicit ground, boundaries, ports or metal-film assumptions would violate fail-closed physics. To close it, use the ordinary GUI to create/review a **real** CPW design case, execute at least two mesh refinements in the genuine native solver, inspect QGeometry and Gmsh identifiers, and export revision-bound solver results for a separately approved benchmark review. That later stage must be automated using the ordinary project/job interface **after** reviewed inputs exist, not an ad hoc resonator runner.

## Report format and decision rules

Generated ZIP: `QUALIFICATION.json` (machine-readable schema `sqe.laptop-eda-qualification.v1`), `SUMMARY.md`, `logs/*.txt`, optional `captures/*.png` from synthetic browser tests, and `INTEGRITY.json` (SHA-256 of every other member). Each gate contains `id`, `category`, `status` (`PASS`, `FAIL`, `BLOCKED`), description, duration, log hash and optional counts/reason. `INTEGRITY.json` detects accidental report alteration; it is **not** a digital signature or proof of independent execution.

- **PASS**: the test actually ran and its stated assertions succeeded; record skipped subtests separately.
- **FAIL**: a test, integrity check or build executed but failed, including timeout when execution was attempted.
- **BLOCKED**: no valid acceptance was performed (missing dependency, browser policy, quick profile omission, or unsupported scientific bridge). Do not convert it to PASS because a fixture worked.
- **RC = BLOCKED** while native end-to-end simulation, validated cross-engine physical identity, basis/mesh convergence, browser/platform packaging and independent reference comparisons remain incomplete. Source and GUI passing alone cannot promote the product.

## Proposed release progression

**R0: Source/software readiness.** Reproduce a clean source inventory, passing automated regression and authenticated production HTTP flows, offline package installation and a Windows browser run. Resolve failures at their owned modules; no frozen contract rewrite.

**R1: Native single-engine reproducibility.** On the laptop complete Quantum Metal QGeometry/GDS, independent scqubits transmon/fluxonium with cutoff convergence, SQDMetal/Gmsh/Palace reviewed CPW eigenmode with mesh convergence, and (when supported) Julia RF runs. Every native result must identify version, geometry, units, revisions, materials, settings and hashes.

**R2: Integrated design-loop qualification.** Demonstrate geometry edits propagate into native EM, extracted parameters, circuit model and physically comparable observable; add reviewed, versioned EPR→Hamiltonian, kinetic-sheet and complex-port mappings. Use the **same GUI** and canonical design revision to iterate under explicit objectives and constraints. Validate with published and independent references, declaring model mismatches.

**RC decision.** Pass security, packaging, platform and scientific gates on the intended laptop/OS, retain signed release evidence and conduct an independent physics review. A package can be a **software RC** only if its stated scope is explicit; it cannot be marketed as a scientifically qualified integrated EDA RC while the closed-loop edges above remain blocked. Foundry export always stays HOLD without PDK/DRC/LVS approvals.

## Developer API (optional, not required for a designer)

Tests are initiated through the GUI; automation in controlled CI may call `sqe_studio.qualification.qualify(source_root, output_zip, profile='comprehensive')`. The implementation deliberately is **not an HTTP endpoint** (a remote/browser-accessible arbitrary test runner would expand the security boundary). Test children have bounded time, no network installation and private temporary HOME; report generation writes only to the user-selected ZIP destination.
