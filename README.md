# SQE Studio 0.11.0 — Web-first Quantum EDA Research Workstation

**An open-source, browser-based environment for superconducting quantum-circuit design, reproducible simulations, and scientific review.**

SQE Studio combines a persistent project workspace with parameterized QPU designs, reduced-order circuit models, GDSII/Quantum Metal interchange, Gmsh meshing, Palace FEM integration, and a JosephsonCircuits.jl export bridge. The project is available under the Apache-2.0 license. Scientific limitations are recorded explicitly: this is **research software, not a validated fabrication-ready EDA product**.

## Start on Windows 11

1. Extract this complete archive into a **new writable folder**, not an elevated/system folder. Keep backups of `studio-data` from any earlier installation.
2. Double-click **`WINDOWS-FIRST-START.cmd`**. The first launch creates `.venv` and installs Python dependencies. Subsequent launches reuse it. Gmsh installation is optional and does not prevent the Web application from starting.
3. Your browser opens **http://127.0.0.1:8000/**. Follow the one-time administrator setup link on the first launch.
4. From the left navigation choose **Quantum Design Lab** for QPU design and **System & Diagnostics** for operating-system and scientific-software checks.
5. Run diagnostics from the Web UI and download the resulting ZIP. Open and review the ZIP before sharing. Nothing is automatically uploaded.

**Web endpoints:** `/` (projects), `/quantumlab.html` (QPU design), `/control.html` (diagnostics, local administrator only).

If the Web application cannot start at all, use **`WINDOWS-DIAGNOSTICS.cmd`** as an offline fallback. No command-line work is required for routine design and diagnostic tasks once the application is running. Installing native solvers still requires explicit OS-level approval; no hidden elevation or compilation is initiated by the browser.

Read [Getting started](GETTING-STARTED.md), [Windows installation](docs/windows.md), [Web diagnostics](docs/diagnostics-windows.md), and [scientific development roadmap](docs/roadmap-quantumpro-open-eda.md).

## Current capabilities

| Area | Available now | Important limitations |
| --- | --- | --- |
| Web workspace | Accounts, projects, immutable revisions, worker jobs, artifacts, project export/import | Local SQLite; multi-host distributed scheduler not implemented |
| Parametric QPU | Configurable materials, stack-up, Dolan/Manhattan JJ process-intent, qubit shapes, physical couplers and CPW routes | Multilayer 3D mesher and foundry DRC/LVS remain incomplete |
| Circuit studies | Modes, weak-Kerr estimates, RF S-parameters, flux sweeps, Bloch sequences, reduced Duffing, yield and loss assumptions | Reduced models, not general nonlinear circuit or gate simulation |
| Gmsh / Palace | Gmsh mesh tools; Palace electrostatic, eigenmode, linearized JJ, and driven configurations; convergence job contracts | Authentic FEM benchmark/accuracy validation on Windows/WSL2 is pending |
| JosephsonCircuits.jl | SI netlist export and separate Julia environment setup | Actual harmonic-balance execution is not yet integrated into Web jobs |
| Quantum Metal | QGeometry manifest, optional separate environment | Interchange does not imply a qualified mesh or fabricated device |
| System & Diagnostics | Web-driven standard/extended checks, per-check results, persistent local ZIP reports, privacy review | Extended Gmsh test is a mesh smoke test, **not** a physical Palace FEM validation |

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

The local administrator can run **Scientific workflow validation** from **System & Diagnostics**. This is an opt-in, bounded series of geometry/GDS, Gmsh 3D mesh and authentic Palace capacitance/eigenmode/RF checks on an isolated fixed reference. All stages are reported with PASS/FAIL/SKIP, elapsed time, log excerpts and a downloadable ZIP. No projects, passwords or data folders are copied. See [docs/WORKFLOW-VALIDATION-0.11.0.md](docs/WORKFLOW-VALIDATION-0.11.0.md).

The **Compute queue health** panel helps distinguish a queued job from a running FEM computation. The Palace workbench now exposes worker logs and cancellation. A PASS does not certify EM accuracy or fab readiness.
