# SQE Studio 0.13.0 — FEM Numerical Validation & Results

## Browser-first acceptance procedure

1. Close the running workstation and replace the application files with v0.13.0. Keep `.venv/`, `studio-data/`, your own projects, and the independent Palace installation in Ubuntu/WSL2. Back up `studio-data/` first.
2. Start `WINDOWS-FIRST-START.cmd`, sign in as the existing administrator, and hard-refresh the browser (Ctrl+Shift+R).
3. Open **System & Diagnostics** at `http://127.0.0.1:8000/control.html`.
4. Verify a prior **Quick** and **Standard** result if desired; for this release select **Palace scientific diagnostics → Numerical** and click **Run checks**. Do not run other FEM jobs concurrently.
5. Once completed, inspect **Numerical results** (matrix tables, analytical reference error, mesh-level change and cavity frequency), then download **Diagnostic ZIP**. Inspect the ZIP before sharing.
6. If a numerical stage fails, share the ZIP. It contains stage outcomes and bounded solver-log excerpts; the stage's numeric values are included when Palace produced readable, provenance-checked CSV files.

## What each profile means

| Profile | Geometry and test | Scope |
| --- | --- | --- |
| Quick | Tiny Gmsh box + Palace executable launch | Installation sanity; **not** an EM solve |
| Standard | Reduced 1-transmon geometry, Gmsh mesh, Palace electrostatics, C extraction | FEM execution; **not** analytical validation |
| Numerical (**new**) | Two structured independent parallel-plate meshes, genuine Palace electrostatics, analytical `epsilon*A/d` check, PEC cavity eigenmode | Numerical **reference checks**, not QPU qualification |
| Full | Larger single-transmon mesh + electrostatic/eigenmode/driven | High computational cost; no automatic analytical qualification |

**The Numerical profile uses fixed reference problems, not user designs.** No geometry or solver output is fabricated. A missing Palace binary results in `SKIP`, and an unsuccessful Palace solve results in `FAIL`. This profile may take several minutes; its stages have independent deadlines. This release uses one Palace process and does not change or install Palace/Spack.

## Physical meanings and acceptance criteria

### Capacitor patch test

A dielectric box (`epsilon_r=11.45`, dimensions **1000 × 800 × 500 μm**) has one fully grounded face, an opposing 1 V terminal face, and zero-charge sidewalls. The exact capacitance is

`C_exact = epsilon_0 * epsilon_r * A / d` (farads).

Two independently generated structured tetrahedral meshes, at subdivisions `4 × 4 × 2` and `8 × 8 × 4`, are solved with Palace Electrostatic. Raw `terminal-C.csv` must be nonempty, have documented Palace units in **F**, and match the input geometry and solver-record hashes. The analytical deviation must be **≤5%** on both meshes and the between-mesh difference must be **≤2%**.

**Important limitation:** The exact solution has a linear potential and should be reproduced by piecewise-linear tetrahedral basis functions. Thus this is a **patch test** and stability check of the solver, units and boundary conditions; it is *not* sufficient evidence that a QPU geometry has converged. A physically realistic convergence study needs nontrivial fields, geometry-specific refinements and material interfaces.

### Lightweight PEC-cavity eigenmode

A **40 × 27 × 19 mm** perfectly conducting rectangular cavity uses a small structured tetrahedral mesh and Palace eigenmode. The first observed frequency is compared to the analytical PEC-box spectrum; the allowable relative error is **≤10%** (a deliberately initial qualification threshold, not an RF metrology specification).

Eigenmode **order** is not proof of modal identity, especially for degenerate modes. This release does not perform field-overlap-based mode tracking, and a pass does not authorize Kerr, χ, g or T1 predictions.

### QPU capacitance viewer

In **Standard** and **Full**, the Web report now presents the **raw terminal Maxwell capacitance matrix** and the projected **differential-coordinate capacitance matrix**, both in **fF**. It also displays terminal ordering, the largest asymmetry, the smallest symmetric eigenvalue and the CSV SHA-256. The projected matrix is conditioned on the assumptions encoded in the QPU extractor (for example grounded feedlines); it is not a directly fitted circuit or an independently qualified result.

## Report format

Scientific reports additionally contain allowlisted `scientific-results.json`, listed in `manifest.json` and `SHA256SUMS.txt`. This JSON includes only a fixed-reference numeric result summary, source hashes, mesh levels, benchmark thresholds and recorded stage outcomes. It contains no project layouts or arbitrary solver input files. `checks.json`, `test-results.txt` and `SUMMARY.txt` remain available. The browser displays the same values as read-only tables.

The reports and logs undergo best-effort redaction. Review them before upload. Never share `.venv/`, `studio-data/`, secrets or your QPU project archive unless intentionally required for separate debugging.

## Verification status and expected next steps

Automated unit tests verify reference input generation, independent analytical formulas, CSV schema checks, input/output hashes, error detection, UI contracts, reports and threshold failures. Numerical tests involving a simulated Palace CSV are **fixture-only** and must never be reported as a real FEM validation.

The new Numerical profile has **not been run against Palace on the user's Windows workstation yet**. That run is the immediate acceptance step. If Palace's eigenmode backend is unavailable, the report must show the exact error or timeout rather than report a fabricated success. A follow-up release can introduce geometry-aware h-refinement/convergence for actual transmon/coupler layouts and field-overlap eigenmode tracking.

Official Palace reference: <https://awslabs.github.io/palace/stable/guide/problem/>.
