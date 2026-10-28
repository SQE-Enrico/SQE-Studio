# SQE Studio 0.11.0 — Windows/WSL workflow validation

## Use from the browser

1. Launch `WINDOWS-FIRST-START.cmd` as the normal Windows user, and sign in.
2. Open **System & Diagnostics** (`/control.html`) as a local administrator.
3. Inspect **Compute queue health**. `Queued` means a job has not started; a nonzero mesh timer does not itself show meshing progress. An old queued job (>60 seconds) suggests the scheduler/worker is not processing the queue. Open the FEM job and its log in Quantum Design Lab.
4. Run **Extended** diagnostics for OS, WSL/Palace detection and a Gmsh unit-box mesh.
5. Run **Scientific workflow validation** for an isolated 1-transmon reference, if adequate resources are available. It runs one case at a time at a single MPI rank. It does not read or modify existing projects.
6. Download the ZIP from the same Web page. Review every file before sharing.

## Fixed scientific validation sequence

| Stage | Operation | Deadline | Evidence | Notes |
|---|---|---:|---|---|
| Geometry | Create nominal circuit, GDSII (HOLD), QGeometry and Palace JSONs | 35s | source hash, GDS file and contract | No solver |
| Mesh | Gmsh 3D for the same reference, preserve hash and element count | 180s | `device.msh`, `mesh.json` | May be slow on a laptop |
| Electrostatic | Palace solve with 1 MPI rank | 180s | `terminal-C.csv`, solve provenance | Real solver required |
| Capacitance | Verify and project solved Maxwell C | 30s | parsed, physically admissible matrix | Requires electrostatic solve |
| Eigenmode | Palace solve with 1 MPI rank | 180s | `eig.csv`, solve provenance | Mode matching not validated |
| Driven | Palace 2-port RF with one excitation per run | 360s total | both `port-S.csv` outputs | Two independent solves |

The diagnostic collector keeps the isolated workspace only for the duration of the run, then deletes it. It archives a restricted, scrubbed text log, checks, runtime metadata and SHA-256 manifest. **Raw FEM field data, project files and model files are not included.** Do not treat a PASS as scientific qualification: solver configuration, mesh refinement, analytic references, field overlap and experimental validation are still required.

The app uses per-stage deadlines. If a prerequisite is not installed, dependent steps are `SKIP`, not `PASS`. If the worker or solver fails, it records `FAIL`; no simulated solver outputs are generated. On Windows a timeout attempts to terminate the local process tree; after a WSL crash, additionally check Ubuntu for orphaned solver processes before starting another solve.

## First release acceptance checks

- Language: all visible Quantum Design Lab and System & Diagnostics text in English.
- `/api/template` returns HTTP 200 after login (integrated prior fix).
- Browser diagnostics are localhost-only, admin-only, CSRF-checked, opt-in and persisted.
- The queue card reports delayed jobs and stale running heartbeats.
- The FEM panel provides **View worker / solver log** and **Cancel job**.
- Scientific diagnostics ZIP includes per-case PASS/FAIL/SKIP, elapsed time, error tail and an integrity manifest.
- Windows/WSL/PALACE execution is not qualified until tested on the target workstation.

## Known limitations

The single-transmon reference uses the existing simplified planar geometry and is **not** a fabrication-qualified chip or numerical accuracy benchmark. Its full 3D mesh may remain expensive; a 180-second deadline will report a timeout rather than concealing a stalled solver. The check is intentionally not a replacement for numerical convergence, EPR extraction or broad coverage of all user-defined materials/topologies. Julia/JosephsonCircuits import remains covered by Extended Diagnostics when installed; an actual nonlinear solve is a separate roadmap step. Remote installation, system administration and code updates are not executed from the browser.
