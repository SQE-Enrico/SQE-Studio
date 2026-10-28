## 0.17.0 — 2026-10-28

- Rebuilt the Web home page as a single, responsive five-step workflow from project to support ZIP.
- Consolidated project workflows, full regression suites and scientific diagnostics into one run-and-results journey while preserving specialist editors.
- Added best-effort first-launch provisioning of optional scientific packages and bounded, allowlisted browser-based repair.
- Isolated the Quantum Metal/SQDMetal stack in Python 3.11 and the JosephsonCircuits package in a Julia project, with diagnostic smoke checks and ZIP evidence.
- Added dependency manager access-control and failure-report tests; preserved the Palace validation and example projects.
- Kept all new source, messages and documentation in English, clearly separating package readiness from solver accuracy.

## v0.16.0 — Web-first multi-engine experiments and support bundles

- Added Research Experiments Web workspace with engine readiness, reference-project plans, bounded asynchronous worker runs, live status, logs, cancellation and one-click ZIP exports.
- Added secure custom workflow ZIP import with path, size, file-type and executable-code restrictions.
- Added per-job Web support ZIP with SHA-256 manifest, explicit file exclusions, size limits and access controls.
- Added a minimal support ZIP for failed workstation diagnostic runs.
- Kept Palace numeric diagnostics, scientific reference profiles, existing project formats and all previous test projects.
- Added regression tests for permissions, CSRF, Web experiment execution, support archives and hostile ZIP input.
- Entire new UX, source and documentation are English; updated the release and diagnostics versions.
- External solver installation, numerical accuracy, manufacturing qualification and commercial-grade parity remain unverified.

## [0.15.0] — 2026-10-28 — Multi-engine adapter and workflow refactor

- Added a **separate topology-independent research workflow** with validated
  per-step engine/operation/source/dependencies, reproducible immutable runs,
  local input snapshots, artifact SHA-256 and explicit epistemic statuses.
- Added lazy, real API adapters to Quantum Metal/QGeometry, SQDMetal Palace
  capacitance/eigenmode prepare and opt-in native execution, scqubits Transmon,
  Fluxonium, TunableTransmon and custom Circuit YAML, JosephsonCircuits.jl SI
  export and experimental opt-in Julia linear S-parameter sweep.
- Preserved legacy Palace/Gmsh, QPU geometric audit and convergence tests,
  Web diagnostics, existing GUI and project capsules unchanged. Added three
  non-production example projects and 8 new contract tests.
- Added explicit security gates for trusted Python design factories and native
  solver execution. SQDMetal and JosephsonCircuits solver paths were **not**
  exercised against real external runtimes here; no FEM convergence or
  QuantumPro commercial equivalence is claimed.

## v0.14.1 — QPU FEM Geometry & Convergence Audit

- Added browser-based QPU Geometry & Boundary Audit against real MSH 2.2 physical element groups, terminal order and electrostatic boundary conditions.
- Added opt-in, resource-bounded experimental electrostatic Palace AMR profile with strict audit preflight.
- Added per-terminal energy consistency check using authentic hashed `domain-E.csv` and `terminal-C.csv` values, without silent rescaling or overriding convergence status.
- Added small authenticated scientific evidence CSVs to diagnostic ZIPs, along with SHA-256 checksum verification and strict allowlists.
- Preserved all v0.14 profiles and read-only local Web control workflow; no project migration or solver reinstall required.
- Synthetic regression tests cover preflight, mismatches, tampering, AMR setup and UI options. New Palace solve remains unverified on Windows.

## v0.14.0 — QPU Mesh Convergence & Field Evidence

- Added opt-in browser-based **QPU C convergence** and **QPU Modes** scientific profiles, with two levels of Palace uniform h-refinement on the same fixed single-transmon model.
- Added verified, size-bounded C matrix comparison, projected differential coordinates, frequency tables, field/energy CSV metadata, and L0 ParaView file inventory.
- Enhanced failure handling, state reports, SHA-256 provenance checks and reduced unnecessary second-level solver execution on failure.
- Preserved numerical values even when a tolerance is not met. Clearly marked eigenmode matching as **index-only** and numerical results as **not physically qualified**.
- Added 0.14 regression fixtures, documentation and Windows-first acceptance steps; retained Quick / Standard / Numerical / Full.
- **Pending:** real Palace 0.16.0 multi-level QPU runs, visual 3D field viewer, mesh-independent mode overlap matching, and independent physical QPU validation.

## v0.13.0 — FEM Numerical Validation & Results

- Add the browser-controlled **Numerical** scientific profile with real Palace solves of an isolated parallel-plate capacitor (two independent mesh levels) and PEC rectangular cavity eigenmode.
- Add analytical comparisons, explicit physical units, independent provenance/hashes, tolerance gates and distinct `PASS` / `FAIL` / `SKIP` diagnostics.
- Preserve measurable numerical results even when a tolerance fails; retain bounded solver log tails for failure analysis.
- Add Web capacitance-matrix tables with terminal ordering, fF units, symmetry and minimum-eigenvalue information for Standard/Full QPU extraction.
- Add allowlisted `scientific-results.json` to Web diagnostic bundles, in the SHA-256 manifest.
- Add regression tests for reference generation, patch-test metrics, eigenfrequency parsing, tamper rejection and failure handling.
- Do not claim QPU convergence or full Palace scientific qualification; new solver benchmarks still require Windows/WSL2 acceptance.

## [0.12.0] - 2026-10-28

### Palace benchmarking profiles and solver observability

- Replaced one expensive default scientific run with opt-in **Quick**, **Standard**, and **Full** profiles in the Web control center. Quick is the default and never runs a full QPU mesh or FEM solve.
- Quick checks a small native Gmsh 3D box and actually invokes the Palace command-line `--help` through the current Ubuntu/Spack environment.
- Standard generates a reduced-resolution one-transmon reference and performs electrostatic extraction when Palace is installed; Full retains the comprehensive capacitance, eigenmode and two-port driven workflow. Neither profile claims numerical convergence or fabrication readiness.
- Captures disk-backed, bounded stage output and Palace solver-log tails even when a stage exits with error or reaches its deadline; error messages and paths are redacted best-effort in support ZIPs.
- Adds Linux-side bounded process execution for WSL launched Palace, preventing unlimited solver life after an interrupted Windows proxy. Adds optional GNU time CPU/memory accounting to solver logs where available.
- Adds profile-specific progress, elapsed-time and element-count evidence; retains authenticated localhost-only Web diagnostics, immutable projects, prior login and Windows startup fixes.
- Adds profile and failure-log regression tests. Real Palace/FEM qualification on the Windows/WSL2 workstation remains the next acceptance milestone.

## [0.11.0] - 2026-10-28

### Windows workstation consolidation and scientific workflow diagnostics

- Localized remaining Quantum Design Lab and Palace workbench UI strings to English, including job notifications, physical editor and roadmap.
- Integrated the v0.10 Web login hotfix and the Windows first-run Shapely probe correction.
- Added queue health, elapsed queued time, FEM worker/solver log access and cancellation controls.
- Added opt-in, isolated, time-bounded scientific validation: physical design/GDS/JSON, real 3D mesh, Palace electrostatic, capacitance extraction, eigenmode, two independent RF excitations.
- Added per-stage status and progress in the Web control center and a downloadable sanitized diagnostic ZIP with checksums. Missing native solvers produce SKIP, never fabricated PASS results.
- Unified WSL Palace detection with the working application backend and improved WSL path conversion for the runner.
- Added tests for geometry reference export, skip handling, queue endpoint authentication and English UI notices.
- The real Palace FEM solve on Windows/WSL is still pending on-device acceptance testing.

## [0.10.0] - 2026-10-28

- Consolidated the uploaded workstation source into a clean English-first release, excluding local user databases, setup tokens, diagnostics, hotfix artifacts and caches.
- Added authenticated loopback-only Web **System & Diagnostics** control center with background execution, run history, per-check reports and downloadable privacy-reviewed ZIPs.
- Added server-side admin ACL, CSRF and route security regression tests; remote production deployments cannot run native diagnostic probes.
- Startup scientific tests now write a local Web-visible report and no longer block the browser on an optional regression failure.
- Reworked English workstation, Palace, Quantum Metal and Julia docs, and retained optional native installers outside privileged browser actions.
- Palace real-world Windows/WSL2 reference simulation, Quantum Metal runtime and JosephsonCircuits.jl HB remain unqualified.

## [0.9.0] - 2026-10-28

- Diagnostic hardware feedback loop: `WINDOWS-DIAGNOSTICS.cmd` and `-Extended`, supported without starting SQE Studio.
- Privacy-minimised allowlisted ZIP with structured checks, stable reason codes, unit-test results and per-file SHA-256 checksums.
- Read-only WSL2/Ubuntu/Palace-Spack detection; optional native Gmsh 3D smoke, Julia JosephsonCircuits import.
- Resilient PowerShell-only fallback when Python is missing, regression tests for ZIP integrity and safe collection.
- Important: not yet executed on a real Windows machine; real Palace solve/Julia HB are not claimed.

## [0.8.0] - 2026-10-28

- Added revisioned Web physical jobs for eigenmode and electrostatic Palace mesh-convergence sweeps (UniformLevels 0/1/2), with verified solver outputs and explicit numerical-vs-scientific qualification gates.
- Added conservative SI netlist export for JosephsonCircuits.jl: physical JJ branches preserved, RF coupling capacitors modeled, effective SQUIDs refused rather than silently flattened.
- Added optional Windows Julia/Juliaup + JosephsonCircuits guided environment setup, standalone CLI and upgrade roadmap R1–R15 with acceptance criteria.
- 110 tests run, 4 optional skipped; real Palace/Gmsh/Julia/Windows qualification still outstanding.

## [0.7.0] - 2026-10-28

- Introduced physical schema v2 for material libraries, user-defined stack-up, Dolan/Manhattan JJ process intent, and the qubit/coupler/routing graph with user-specified rectilinear geometry.
- Added interdigitated capacitive couplers and isolated CPW bus conductor nets with explicit nominal circuit values.
- Added CPW width/gap/waypoint/Manhattan/meander routes, Boolean ground subtraction and fail-closed preliminary planar DRC.
- Added multilayer GDS review candidates, Quantum Metal QGeometry manifest v2 and conservative Gmsh/Palace physical exporter.
- Added parametric and advanced JSON Web editing, examples and Shapely for Windows bootstrap.
- Native Palace solver validation, multilayer metal FEM and fabrication sign-off remained outstanding.

## 0.6.0 — Unified physical QPU / GDS / Quantum Metal / Palace (2026-10-28)

- Added independent 1-, 2-, 4-cell physically tiled superconducting transmon reference design with stable named nets, ground reconnection, port/JJ ids and geometry SHA-256; no invented interqubit couplers.
- One saved physical specification exports a positive-metal mask GDS (HOLD), QGeometry manifest, separately labelled *nominal* electrical circuit, and Palace/Gmsh terminal/port/JJ configurations.
- Added FEM `physical:*` revisioned jobs for packaging, volume mesh, actual electrostatic C, authentic capacitance projection, eigenmode and per-port RF driven runs. Integrity and solver log checks fail closed.
- Added analytical first-order EPR Kerr (explicitly supplied/mapped participation), user-input dielectric T1, and two-mode dispersive Purcell estimates, never treated as automatically extracted loss.
- Corrected the legacy Palace driven RF flow to run two separate excitations for the two S-matrix columns instead of a simultaneous excitation.
- New browser panel, Windows/WSL installation reuse, CLI exporters and field-data postprocessor, research examples, regression/security tests, and limitations/qualification document.
- Scientific qualification of new multi-cell Gmsh meshes, Palace field solves, Quantum Metal import and Windows WSL installation is pending; no fabrication signoff.

## 0.5.0 — Quantum Metal / Palace FEM Windows bridge (2026-10-28)

- Parametric physical layout single-transmon editable and previewable in the Quantum Lab Web section, with explicit separation from multi-QPU lumped netlists.
- Palace native-Linux or WSL2 backend: Windows-path translation, sandboxed temporary ext4 execution, Spack runtime probing, bounded status API and persistent results retrieval.
- Opt-in guided WSL2/Ubuntu/Spack/Palace source installation; automatic Gmsh wheel check on first Windows launch. No silent elevation, no made-up solver output.
- Palace JSON workflow adds driven two-excitation S(f), plus separate linearized JJ eigenmode Web action; output CSV and hashes kept per job.
- Interchange to Quantum Metal QComponent/QGeometry using named metal nets and unit conversion mm/um and checksummed manifest; optional isolated Python installer and CLI sidecar.
- Additional automated scientific, WSL wrapper with fake solver, backend routing and access-control regression tests; documentation, validation and limitations.

# Changelog

## [0.4.0] — 2026-10-27

- Browser-based Quantum Design Lab with standalone JS/CSS editor and QPU circuit templates.
- New scientifically explicit reduced-order modes/χ, S/Touchstone, SQUID flux, two-level dynamics, one-mode Duffing, Monte Carlo yield, Q budget, EJ tuning and circuit checks.
- Asynchronous `mode=lab` jobs integrated with immutable revisions, project ACLs, result SHA-256 checks and capsule export.
- Export of multi-QPU **concept-only** GDSII with explicit fabrication disclaimer.
- Windows one-click per-user Python/bootstrap/launch scripts, local loopback startup and Windows scheduler lock/cancellation support.
- New physical limitations/feature-gap benchmark and 11 integration/scientific tests.
- Native Palace/3D FEM on Windows and true multi-QPU geometry-to-circuit EM equivalence remain unimplemented/require qualification.

## 0.3.0 — 2026-10-27

- Added SQE Studio, a browser workspace for INRiM's Superconducting Quantum Electronics Group, maintained by Emanuele Enrico.
- Added account setup/activation, session/CSRF protection, project ownership and membership, persistent drafts and immutable revisions.
- Added a durable resource-aware queue, separate job subprocesses, concurrent execution, cancellation and compatible-checkpoint reuse.
- Connected process junction area/Jc or laboratory Ic/Cj to the forward quantum model.
- Added process/wafer/junction/accessory editing, chip/wafer GDS candidates, raster logos and laboratory-cell assembly integration.
- Added project capsules, source inspection, administrator-reviewed Python macros, WSGI/proxy/container deployment materials and application tests.
- Reframed the repository for continuing group research; retained training as an optional guide.

## 0.2.0 — 2026-10-27

- Added recursive stage fingerprints, downstream invalidation and `sqw verify`.
- Preserved imported extraction by default; an explicit flag is required to replace it with a surrogate.
- Added isolated-environment preflight, environment drift checks, custom venvs and offline wheelhouse installation plans.
- Added independent P1 capacitor FEM and standalone capacitor/PEC-cavity meshes for native Palace qualification.
- Recorded raw solver-output hashes, rejected missing/changed results, and strengthened CAD equivalence to a full-region Boolean XOR.
- Retained the explicit pending status of external dependency installation, Palace chip solves and fabrication qualification.

## 0.1.0 — 2026-10-26

- Added isolated Python bootstrap, core pins, reference-stack candidate pins and native Palace build helpers.
- Added shared Al-on-Si geometry, native and QPDK/GDSFactory GDS export, Gmsh/Palace adapters and laboratory junction-cell assembly.
- Added floating-pad capacitance reduction, exact/scqubits spectra, coupled-mode parameters, thermal estimates and measurement simulations.
- Added stage provenance, synthetic import/benchmark and process-tolerance examples, six module scripts, a guided notebook and GitHub CI.
- Documented external-tool qualification, measured-chip validation and process-mask integration still required before fabrication.
