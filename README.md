# SQE Studio 0.17.0 — Unified Web Research Workspace

**One user workflow: Project → Setup → Run → Results → Support ZIP.** The redesigned default browser interface combines project selection, optional scientific engine setup, test/experiment execution, results inspection and single-ZIP debugging. All user-facing workflows and new documentation are in English.

On Windows, extract the archive and double-click **`WINDOWS-FIRST-START.cmd`**. At first launch, best-effort background provisioning checks optional scqubits, Gmsh, Quantum Metal, SQDMetal and JosephsonCircuits.jl. Scientific and native solvers that need missing runtimes or external dependencies remain flagged as requiring attention. Automatic installation is not a certificate of scientific validation.

Read [Getting Started](GETTING-STARTED.md), [Unified Web Workflow](docs/unified-web-workflow.md), and [Release 0.17.0](RELEASE-0.17.0.md). Detailed design controls remain accessible from **Advanced editor** and existing data remains compatible.

---

## Historical capabilities and scientific limitations

**An open-source, browser-based environment for superconducting quantum-circuit design, reproducible simulations, and scientific review.**

SQE Studio combines a persistent project workspace with parameterized QPU designs, reduced-order circuit models, GDSII/Quantum Metal interchange, Gmsh meshing, Palace FEM integration, and a JosephsonCircuits.jl export bridge. The project is available under the Apache-2.0 license. Scientific limitations are recorded explicitly: this is **research software, not a validated fabrication-ready EDA product**.


## v0.14 — QPU Mesh Convergence & Field Evidence (Web UI)

From **System & Diagnostics → Palace scientific diagnostics**, choose **QPU C convergence** to run two real electrostatic Palace refinements (L0 and L1) of the *same fixed one-transmon geometry* and compare verified Maxwell and differential capacitance matrices in fF. **QPU Modes** is an optional, more expensive two-level eigenfrequency comparison; it does **not** track modes by field overlap and reports a `WARN` for the identity check. Both profiles collect stage logs, original CSV hashes, limited field/energy metadata and a downloadable, privacy-minimized `scientific-results.json`. L0 requests one ParaView field frame for inventory, not an in-browser 3D render. **Two-level numerical stability is not physical device qualification.** See [v0.14 validation guide](docs/WORKFLOW-VALIDATION-0.14.0.md).

## v0.13 — Analytical FEM benchmark & numerical results (Web UI)

In **System & Diagnostics**, select **Palace scientific diagnostics → Numerical** to solve a parallel-plate capacitor at two independently generated mesh levels and a small PEC cavity. The Web UI displays verified Palace capacitance matrices (in fF), analytical errors, a mesh-level patch-test comparison and a lowest-frequency cavity check. The downloadable report contains `scientific-results.json`, SHA-256 checksums and bounded logs. Existing Quick / Standard / Full profiles are retained. **Numerical reference validation is not QPU mesh-convergence or full scientific qualification.** See [v0.13 validation guide](docs/WORKFLOW-VALIDATION-0.13.0.md).

## Start on Windows 11

1. Extract this complete archive into a **new writable folder**, not an elevated/system folder. Keep backups of `studio-data` from any earlier installation.
2. Double-click **`WINDOWS-FIRST-START.cmd`**. The first launch creates `.venv` and installs Python dependencies. Subsequent launches reuse it. Gmsh installation is optional and does not prevent the Web application from starting.
3. Your browser opens **http://127.0.0.1:8000/**. Follow the one-time administrator setup link on the first launch.
4. From the left navigation choose **Quantum Design Lab** for QPU design, **Research Experiments** for multi-engine tests, and **System & Diagnostics** for software regressions and Palace audits.
5. Run diagnostics from the Web UI and download the resulting ZIP. Open and review the ZIP before sharing. Nothing is automatically uploaded.

**Web endpoints:** `/` (projects), `/quantumlab.html` (QPU design), `/experiments.html` (multi-engine experiments, local administrator only), `/control.html` (regression and Palace diagnostics, local administrator only).

If the Web application cannot start at all, use **`WINDOWS-DIAGNOSTICS.cmd`** as an offline fallback. No command-line work is required for routine design and diagnostic tasks once the application is running. Installing native solvers still requires explicit OS-level approval; no hidden elevation or compilation is initiated by the browser.

Read [Web-first experiments](docs/web-first-experiments.md), [Getting started](GETTING-STARTED.md), [Windows installation](docs/windows.md), [Web diagnostics](docs/diagnostics-windows.md), and [scientific development roadmap](docs/roadmap-quantumpro-open-eda.md).

## Current capabilities

| Area | Available now | Important limitations |
| --- | --- | --- |
| Web workspace | Accounts, projects, immutable revisions, worker jobs, artifacts, project export/import | Local SQLite; multi-host distributed scheduler not implemented |
| Parametric QPU | Configurable materials, stack-up, Dolan/Manhattan JJ process-intent, qubit shapes, physical couplers and CPW routes | Multilayer 3D mesher and foundry DRC/LVS remain incomplete |
| Circuit studies | Modes, weak-Kerr estimates, RF S-parameters, flux sweeps, Bloch sequences, reduced Duffing, yield and loss assumptions | Reduced models, not general nonlinear circuit or gate simulation |
| Gmsh / Palace | Gmsh mesh tools; Palace electrostatic, eigenmode, linearized JJ, and driven configurations; convergence job contracts | A real electrostatic QPU solve was reported successful on Windows/WSL2 in v0.12; independent numerical references still require workstation validation |
| JosephsonCircuits.jl | SI export and experimental opt-in Julia linear S sweep from the Research Experiments browser page | Full pumped harmonic balance and Web worker execution not qualified |
| Quantum Metal | QGeometry bridge plus trusted QDesign factory/inventory in browser-run experiments | Interchange does not imply a qualified mesh or fabricated device |
| SQDMetal | Optional API adapter prepares Palace Gmsh meshes/configs from QDesign via browser-run experiments | Actual target-workstation solver execution, extraction mapping and geometry qualification pending |
| Research Experiments | Browser project catalog, safe workflow ZIP import, step plans, optional adapters, isolated jobs, progress, logs, one-click support ZIPs | External solver validation and separate environment setup required |
| System & Diagnostics | Web Standard/Extended health tests and opt-in scientific Quick/Standard/Numerical/Full profiles; per-stage logs, bounded jobs and ZIP reports | The new Numerical profile runs independent analytical references; passing it does not prove QPU geometry convergence or fabrication readiness |

## Why Palace and JosephsonCircuits.jl?

**Palace** is the intended primary FEM electromagnetics solver for realistic geometry, fields and S-parameters. **JosephsonCircuits.jl** (Kevin O'Brien and collaborators) is the intended nonlinear Josephson circuit solver. Their scientific outputs must be linked by explicit model contracts and benchmarked before automatic quantum-parameter extraction is claimed.

## Project structure

- `src/sqw/`: scientific engine and Web API.
- `src/sqw/studio/static/`: English-language browser workspaces (no JavaScript build step).
- `scripts/`: opt-in installers, diagnostics fallback, bootstrap and export utilities.
- `requirements/`: pinned core Python dependencies.
- `tests/`: unit, scientific-contract and authorization tests.
- `examples/`: fixed reproducible examples; not user projects.
- `docs/`: operational instructions, physics assumptions, and roadmap.
- `studio-data/`: **generated locally at runtime** and never included in release ZIPs.

For the optional production architecture, see [deployment](docs/deployment.md). The built-in Python WSGI launcher is for local loopback use, not for direct public exposure.

## Scientific and privacy principles

- The geometric model, nominal circuit, and extracted FEM results are distinct provenance tiers.
- An installed solver is not a validated solver. A completed job is not an accuracy certificate.
- No project content, account database, secrets, personal paths or historical diagnostic bundles are distributed with this release.
- Diagnostic reports use a fixed allowlist of files and best-effort redaction; **review before sharing**.
- Native solver installations may require Internet, disk space, user consent and elevated OS operations. Those steps are not run from the Web diagnostic endpoint.

## Credits and licensing

SQE Studio was initiated for superconducting quantum electronics research at INRiM. Earlier releases and scientific modules are preserved; original authorship and license notices remain with the source. See `CITATION.cff`, `NOTICE`, `LICENSE`, and `CHANGELOG.md`.

## Scientific workflow diagnostics (v0.11)

The local administrator can run **Scientific workflow validation** from **System & Diagnostics**. This is an opt-in, bounded series of geometry/GDS, Gmsh 3D mesh and authentic Palace capacitance/eigenmode/RF checks on an isolated fixed reference. All stages are reported with PASS/FAIL/SKIP, elapsed time, log excerpts and a downloadable ZIP. No projects, passwords or data folders are copied. See [docs/WORKFLOW-VALIDATION-0.13.0.md](docs/WORKFLOW-VALIDATION-0.13.0.md).

The **Compute queue health** panel helps distinguish a queued job from a running FEM computation. The Palace workbench now exposes worker logs and cancellation. A PASS does not certify EM accuracy or fab readiness.
