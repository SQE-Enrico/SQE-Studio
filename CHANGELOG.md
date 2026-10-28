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
