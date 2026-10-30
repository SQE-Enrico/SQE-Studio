# A03 agent delivery — SQDMetal / Gmsh / Palace

**2026-10-29, Linux development container. Scientific acceptance: BLOCKED / NOT QUALIFIED.**

## Authorization / isolation

- Source ZIP as supplied: `SQE-Studio-product-foundation-CLEAN(3).zip`.
- SHA-256 verified by `sha256sum`: `27fd2ec0cec6c8cbc67e21a180fe90ffa0465532fe7cc534d4a1a09b364b4e07` (exact authorized identity).
- Unmodified foundation `tools/delta.py verify` passed:
  - Tree digest `4a3d24b0d43ab5a6bec18f21276db1c21f904fe09a7c6bfc193d870a20998a9c`.
  - Frozen contract digest `6ffd28ebea3dcfa815a61c22598733520055d8e2b902c1e7ec5ffd5255f74171`.
- Independently extracted base at `/mnt/data/a03_base/SQE-Studio`, copied to isolated `/mnt/data/a03_work/SQE-Studio` before edits. No other agent delta used; no external archive substituted; no frozen or foreign files edited.

## What was implemented

- New A03-specific `study.inputs.em` preflight: explicitly reviewed silicon/sapphire substrate, PEC aluminium layer, vacuum cap, matched chip thickness, physical QDesign ground, six air-box spacings, named ordered CPW/junction/terminal mappings, numeric units, finite solver settings, bounded CPU count, ordered mesh-refinement *plan*, and strictly uniform Hz sweep. Missing/contradictory definitions raise `EngineBlocked` before native import or output creation.
- A02 bridge is **required**, not invented: the A03 module calls `quantum_metal_adapter.build_qdesign(project)` and fails closed if A02 has not exported a deterministic QDesign builder. It does not reverse-engineer or construct an independent geometry from the baseline's limited GDS-only API.
- When the above plus native engines become available: documented `SQDMetal.PALACE.{Capacitance_Simulation,Eigenmode_Simulation,Frequency_Driven_Simulation}` routes, `add_metallic`, `add_ground_plane`, `enforce_full_3D_simulation`, absolute air-box boundaries, physical RF ports, native Gmsh mesh/Palace deck generation. No SQE mesh synthesis, FEM code, or synthetic result.
- Native data validation gates: nonempty 3D mesh elements, Gmsh physical groups, exhaustive and nonoverlapping air/substrate volume attributes, numerical material match, boundary/terminal/port tag match, Palace L0/path/order, eigenmode target, driven excitation/sweep. Unsafe paths or unexpected deck fields block. Native artifact sizes bounded.
- Operator-only Palace binary configuration (`SQE_PALACE_BACKEND`, `SQE_PALACE_BINARY`, `SQE_PALACE_WSL_BINARY`), executable/version probe, bounded direct `subprocess.run` argv (no SQDMetal shell execution) with preserved solver log and required native CSV check.
- Typed `a03-native-artifacts.json` metadata *when native generation succeeds*: source engine versions, mesh/deck/native log/CSV SHA-256, `gmsh.mesh` / `palace.deck` / Palace result type, axis Hz, explicit native port order/reference impedance, user-specified convergence plan with `convergence_observed=false`. Only A06 worker's pre-existing revision-bound `RESULT_MANIFEST.json` asserts source revision. All results remain unqualified.

## Exact test evidence

The **raw unedited command transcript** is included in `logs/A03-tests.log` in the delta. Tests run with `env PYTHONPATH=src python -m pytest -ra` and `/usr/bin/time -v`. Exit code **0**. **40 passed, 2 Python import deprecation warnings**; 29 A03 adapter tests (including three valid structural preflight examples, missing-stack/ground/port/boundary failure paths, duplicate/numbered/unknown ports, wrong material or chip thickness, native group/deck mismatch, S-axis and WSL/native readiness refusal) plus 11 foundation tests. These are **structural/negative/fixture unit tests, not native engine acceptance**.

- Measured pytest elapsed wall clock: **4.63 seconds**.
- Measured pytest maximum resident set size: **145532 KiB** (reported by GNU `/usr/bin/time -v`; this is test-process memory, **not Palace memory**).
- Python: **3.13.5**, Linux x86_64 `6.18.55`; pytest **9.0.2**.
- SQDMetal: **NOT INSTALLED**; `gmsh` Python module/executable: **NOT INSTALLED**; `qiskit_metal` / quantum-metal: **NOT INSTALLED**; `palace`, `mpirun` and `wsl.exe`: **NOT FOUND**. The available engine versions are **unknown**, not estimated.
- A02 builder `build_qdesign`: **absent from the authorized foundation**. Independent of environment, this blocks any QDesign-to-mesh bridge until the A02-owned addition is admitted by A09.
- Native mesh/deck dry-run: **BLOCKED** (no SQDMetal/Gmsh/Quantum Metal and absent A02 builder). Native Palace small smoke: **BLOCKED** (no Palace binary or validated mesh/deck). Windows 11 and WSL: **NOT TESTED** (Linux container). Native runtime and memory: **not measured**. No scientific CSV, solver log, solver convergence metric or experiment was fabricated.

## Scope and limitations

- This is an **implemented guarded path**, not demonstrated functional integration, due to environment/parallel API blockers. Native backend path, output conventions and Gmsh physical-group semantics must be checked against exact installed package and Palace versions before qualification.
- Reviewed stack presently supports **one** substrate and **one** uniform PEC conductor layer plus vacuum, not arbitrary multilayer wafer stacks, finite metal conductivity, kinetic inductance, nonlinear Josephson phenomena, anisotropic tensor material mapping, PDK mask or fabrication signoff. `source=reviewed` and `ground.verified=true` are declarative attestations in this local experimental schema, **not independently authenticated review evidence**.
- Capacitance native conductor-to-terminal mapping is not guessable premesh: requires explicit physical tag values and an exact post-mesh check. This may need a two-phase reviewed workflow in A09.
- Port numbering is native creation order, 1-based. Driven one-port excitation is an S-parameter **column**, never a complete arbitrary multiport S matrix. S-parameter CSV values are not reconstructed, rewritten, interpolated or qualified.
- Mesh refinement levels are **planned only**; the adapter generates level zero and labels convergence **unobserved**. Additional separate native runs and numerical convergence comparisons remain required. No convergence achieved claim.
- Native Palace `--version` must identify Palace and exit zero. Executables that cannot be safely identified are blocked; WSL test/launch still needs actual Windows 11 acceptance.
- The frozen `run(study, project, output_dir)` ABI contains no authenticated revision ID, job cancellation object or native-phase-specific timeout budget. Worker handles immutable revision identity and 180s external timeout. A03 has an additional solver-only 120s limit; mesh generation remains under worker's outer limit.
- SQDMetal `prepare_simulation` may create nonessential generated preview images. They are not returned as scientific native artifacts.

## Proposed reviewed migrations for A09 (no frozen changes performed)

1. **A02/A09 geometry API**, exported from A02-owned module: `build_qdesign(project: dict) -> QDesign` with a documented return contract for components, pin names, connected ground, QGeometry layer IDs, exact source digest and reproducible native version evidence; test its equality with the saved QDesign/GDS recipe. Until then native A03 is blocked.
2. **A01/A09 `sqe.interoperability.v2`**: typed `EMStack`, `EMBoundary`, `EMPort`, `EMMeshPlan`, evidence/provenance fields and separate stages for `mesh.native` -> `deck.native` -> `solve.native`. Include validated terminal physical ID preimage and a two-phase mesh-first review, rather than asserting `verified=true` by fiat. Keep `sqe.project.v1` without silent edits.
3. **A06/A09 worker integration**: pass trusted revision identity and output provenance to an ABI-v2 adapter context, preserve per-phase artifacts for explicit cached revision fingerprints, support 2–3 independent mesh refinement runs with actual convergence evidence, and enforce Windows worker cancellation/time limits.
4. **A09 engine compatibility test plan**: pin tested native package versions, real QDesign/Gmsh/Palace capacitance/eigenmode/driven smoke on a reviewable small chip, compare port numbers/material domains/frequencies against a native reference, test WSL process and mount access, record solver peak memory and runtime, and independent EM numerical/convergence review.

## Implementation references (documentation, not evidence of an executed native run)

- SQDMetal Palace documentation: https://sqdlab.github.io/SQDMetal/simulations/simpalace.html
- SQDMetal public implementation: https://github.com/sqdlab/SQDMetal/tree/main/SQDMetal/PALACE
- Palace native config, results and ports: https://awslabs.github.io/palace/stable/quick/ and https://awslabs.github.io/palace/stable/guide/problem/
- Native output and requested schema: `docs/agents/A03.md` (included owned document).

**Final gate: BLOCKED for scientific/native acceptance; DELTA ADMISSION is a separate ownership/hash check, not qualification.**
