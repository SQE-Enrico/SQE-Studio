# SQE Studio 0.14.0 — QPU Mesh Convergence & Field Evidence

## Purpose and scope

This increment provides **browser-driven, two-level h-refinement studies** of a fixed, isolated single-transmon reference. It uses the same Palace configuration model as the QPU workbench, with identical GDS/geometry and the same initial Gmsh mesh, then asks Palace to apply `Model.Refinement.UniformLevels = 0` and `1`. It is **not** a three-level asymptotic convergence study. It does not validate surface losses, multilayer manufacturing processes, EPR-based quantization or a user's own device.

The previous **Quick**, **Standard**, **Numerical** and **Full** diagnostics remain available. Two additional opt-in profiles are available in **System & Diagnostics → Palace scientific diagnostics**:

- **QPU C convergence:** fixed QPU geometry and GDS → one reduced-resolution base 3D mesh → configurations for L0/L1 → two verified Palace electrostatic solves → Maxwell and projected differential capacitance comparison. This profile is the recommended first v0.14 test.
- **QPU Modes:** the same fixed geometry and base mesh → two verified Palace eigenmode solves → ordered mode frequencies, differences, and field/energy inventory where available. **Mode identity is not established.** A successfully parsed mode comparison deliberately produces a `WARN` instead of a scientifically qualified PASS. Comparing rows by solver index must not be used to infer `g`, `χ`, Kerr, or to declare convergence through avoided crossings.

Only one profile runs at a time. The WSL Palace launcher explicitly accepts only `convergence-electrostatic-L0..L3.json` and `convergence-eigenmode-L0..L3.json` in addition to the existing known solver configurations; arbitrary names and shell fragments are rejected. The executor is bounded (including Linux-side timeout for WSL); L1 can be much more expensive than L0. If L0 fails, L1 is skipped to avoid unnecessary expensive calculations. Existing projects are not accessed by the diagnostic.

## What the browser shows

The Web report displays stage timings and statuses and, when genuine Palace solver records pass SHA-256 provenance checks:

1. Raw Maxwell C (fF) for each level and its numerical maximum entrywise change.
2. The two projected capacitance matrices for QPU differential and readout coordinates, with eigenvalue and relative-change checks. Nominal JJ capacitance is **not** silently included.
3. Eigenfrequency vectors (GHz) for the two levels and the index-by-index change, clearly labeled **informational only** until field-overlap matching is implemented.
4. When Palace actually creates `domain-E.csv`, `port-EPR.csv`, `surface-Q.csv`, or probe CSVs, their file hashes, header names and limited numeric summaries. One low-level ParaView frame is requested on L0 and only its file inventory is recorded. Raw VTK/ParaView data is **not** rendered by this version or included in diagnostic ZIPs.
5. Logs, stage status and the reproducible compact `scientific-results.json` in the downloadable ZIP.

The fixed threshold is **1%** for the C convergence diagnostic. A PASS means only that this particular numerical change falls below the stated threshold: it does not establish asymptotic convergence, appropriate meshing of singular edges, boundary-condition correctness, or experimental accuracy. Actual output values remain visible even if the 1% criterion fails.

### Palace output specifics

Palace supports `Problem.OutputFormats.Paraview`, `Solver.Electrostatic.Save`, and `Solver.Eigenmode.Save` to save fields, and CSV postprocessing for domain energy, ports and surfaces. The L0 diagnostic enables one ParaView frame. The L1 refinement does not request additional volumetric frames to limit local disk consumption. The browser does not attempt to reinterpret raw binary VTU files as scalar samples. For full 3D visualization, the authenticated workbench will need a separate field-data service or controlled ParaView export in a future release.

Official documentation:

- <https://awslabs.github.io/palace/stable/guide/postprocessing/>
- <https://awslabs.github.io/palace/stable/guide/problem/>
- <https://awslabs.github.io/palace/stable/quick/>

## Windows workstation acceptance procedure

1. Back up the existing `studio-data` folder and stop the Web server.
2. Extract the complete v0.14 ZIP over the existing source installation, **preserving** `.venv`, `studio-data`, and the independent Ubuntu/Spack/Palace installation. Do not copy the old `src/` folder back on top.
3. Double-click `WINDOWS-FIRST-START.cmd`, sign in with the existing administrator account, refresh with Ctrl+Shift+R.
4. Open `http://127.0.0.1:8000/control.html` and select **Palace scientific diagnostics → QPU C convergence**. Do not run other FEM jobs concurrently.
5. Review the two C matrices and the per-level checks; download and inspect the diagnostic ZIP before sharing it.
6. Only after C convergence is evaluated, consider the much heavier **QPU Modes** profile. It is optional and explicitly not a mode-identity qualification.

**Do not rerun Palace installation** when upgrading the application. If a stage fails or times out, preserve the report rather than immediately repeating the workload.

## Validation and limitations

The source release has unit tests for stage gating, profile registration, two-level configuration integrity, mock fixture provenance and tamper rejection, positive-definite projected C, preserved numerical metrics on threshold failure, and disclosure of unqualified mode identity. Mock CSV fixtures are **not real Palace simulation evidence**. Real two-level QPU Palace runs and field output must be verified on the target Windows/WSL2 system.

The diagnostic deliberately uses a fixed one-qubit specimen, not personal project files. User-selectable arbitrary multilayer stacks and user-designed couplers are outside the scope of this scientific regression. A broader CAD-linked convergence workflow can be implemented once this fixed reference works reliably.
