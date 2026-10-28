# SQE Studio 0.14.1 — QPU FEM Geometry & Convergence Audit

## Why this release exists

The first two-level QPU electrostatic study on a Windows 11 / Ubuntu WSL2 / Palace 0.16 workstation completed both solves, but the projected capacitances changed by roughly 32–47%. This is a genuine *failure to establish numerical convergence*, not evidence that Palace crashed. Potential causes include insufficient initial resolution, inaccurate physical group assignment, boundaries, and postprocessing assumptions. No conclusion about which cause dominates has yet been established.

## New browser profiles

Go to **System & Diagnostics → Palace scientific diagnostics**:

1. **QPU Geometry & Boundary Audit** (recommended first): generates a new fixed single-transmon reference geometry and Gmsh mesh. It streams the *actual MSH 2.2 element tags* and compares domain groups, terminal IDs, ground attributes, terminal ordering and JSON boundary conditions with the versioned geometry contract. Does **not** run Palace. A passing audit does **not** certify spatial placement of faces or topology/continuity of OpenCASCADE geometry.
2. **QPU Adaptive Refinement** (experimental, opt-in): repeats the audit and, only if it passes, prepares one separate Palace electrostatic run using `MaxIts=1`, `MaxSize=150000` (DOFs), `Tol=0.02`, `UpdateFraction=0.5`, with `Nonconformal=false`. This does not alter the earlier two uniform-refinement profiles. The solver may stop before adaptation if a resource cap is reached, and its numerical validity is **not** presumed. No evidence on the target Palace 0.16 is yet available for this profile.
3. Existing **QPU C convergence** retains L0/L1 uniform refinement. In v0.14.1 it also reports a terminal-by-terminal electric-energy consistency check **if** `domain-E.csv` has the expected columns.

### Energy consistency

For the electrostatic terminal excitations Palace applies one volt on the selected terminal with others grounded. The expected total stored energy is `0.5 * C[i,i] * 1 V²` in joules, where raw `terminal-C.csv` entries are converted from fF to F. A separately verified `domain-E.csv` is compared against these values. No empirical scaling is permitted. Outcomes:

- `CONSISTENT` if the relative discrepancy is no more than 5%; this is an output consistency check only.
- `MISMATCH_REQUIRES_INVESTIGATION` with both values and ratios preserved.
- `NOT_AVAILABLE` or `NOT_COMPARABLE` where the available CSV cannot support the comparison.

Energy comparison does not replace geometric correctness, convergence, accurate material properties or experimental validation. It does not change the numerical convergence result by itself.

### Evidence included in diagnostic ZIPs

For QPU profiles, the ZIP now optionally includes bounded, **allowlisted** evidence files in `evidence/`: real `terminal-C.csv`, `terminal-Cm.csv`, `terminal-V.csv`, `domain-E.csv` and `error-indicators.csv` from successful, authenticated fixed-device Palace runs, plus fixed diagnostic geometry/mesh/Palace JSON metadata. Each CSV is checked against the solve's SHA-256 manifest; nothing is synthesized. File count and total bytes are limited. Large `device.msh`, ParaView/VTU and binary field data remain excluded. The ZIP includes updated `manifest.json` and `SHA256SUMS.txt`. Scientific QPU user project data are not scanned or copied.

Inspect any support archive before sharing. Reports can contain numerical data or unintended paths in error messages; sanitization is best-effort.

## Installation and test sequence (Windows)

1. Stop SQE Studio. Back up `studio-data`.
2. Unpack v0.14.1 over the *application* directory. Keep `.venv` and `studio-data`. Do not replace the existing independent Ubuntu/Spack/Palace installation.
3. Start with `WINDOWS-FIRST-START.cmd`, sign in as an administrator, and refresh the browser with Ctrl+Shift+R.
4. Open `http://127.0.0.1:8000/control.html`, choose **QPU Geometry & Boundary Audit**, and run checks.
5. Download the ZIP and inspect `scientific-results.json` and `evidence/geometry-boundary-audit.json` before sharing it.
6. **Do not run QPU Adaptive Refinement if the preflight failed.** If it passed, decide whether to try the explicit experimental, slower AMR profile; do not run simultaneous heavy jobs.

## Acceptance boundaries

- Code validation includes synthetic MSH 2.2 fixtures, tampering tests, CSV energy consistency and API regression. These are not actual Palace solves.
- Genuine Gmsh and Palace numerical execution of the new v0.14.1 profiles must be tested on the Windows workstation. Our development environment currently lacks `gmsh` and `palace` executables.
- A complete geometry/boundary audit is still **not** available. It must ultimately test the physical location of faces, connected nets and air/substrate interfaces in 3D, not only identifiers and attributes.
- One AMR solve is not a numerical convergence demonstration; robust QPU verification needs more independent meshes, asymptotic trends, a validated physical model and eventually comparison with measurements.

## Palace compatibility references

- Palace configuration schema: <https://awslabs.github.io/palace/dev/config/reference/>
- Palace electrostatic problems: <https://awslabs.github.io/palace/stable/guide/problem/>
- Palace postprocessing: <https://awslabs.github.io/palace/stable/guide/postprocessing/>
