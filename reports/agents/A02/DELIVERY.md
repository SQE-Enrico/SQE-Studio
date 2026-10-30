# A02 delivery evidence — 2026-10-29 UTC

## Scope / identity

Agent: **A02**, implementation only, isolated from all other agent deltas.
Unchanged uploaded archive filename: `SQE-Studio-product-foundation-CLEAN(2).zip`.
Archive SHA-256: `27fd2ec0cec6c8cbc67e21a180fe90ffa0465532fe7cc534d4a1a09b364b4e07` **verified before extraction**.
Original `FOUNDATION_LOCK.json` tree SHA-256: `4a3d24b0d43ab5a6bec18f21276db1c21f904fe09a7c6bfc193d870a20998a9c`.
Frozen contract digest: `6ffd28ebea3dcfa815a61c22598733520055d8e2b902c1e7ec5ffd5255f74171`.
`tools/delta.py verify` on untouched BASE: **PASS**. All original files are unchanged in BASE; WORK contains A02-owned modifications only. Final identity/preimage checks are performed by `tools/delta.py admit`.

## Actual runtime / versions

- Runner: Linux `6.18.55`, x86_64; **not Windows 11**.
- Python `3.13.5` (target Windows uses Python 3.11; Windows not tested).
- pytest `9.0.2`.
- `qiskit_metal` importable: **NO**; distribution `quantum-metal`: **not installed** (no native engine version to report).
- Native GDS viewer: **not installed/tested**; external viewer/visual layer check **BLOCKED**.
- Native QGDSRenderer execution, emitted valid GDS, full geometrical comparisons, transmon junction placement: **NOT EXECUTED; BLOCKED by absent Quantum Metal**.
- No native scientific/GDS output was fabricated, and no external package was silently replaced.

## Implementation changes and evidence

Files are listed with preimage SHA-256 and new SHA-256 in `DELTA_MANIFEST.json` produced by the official `delta.py` tool.

1. `src/sqe_studio/adapters/quantum_metal_adapter.py`: static reviewed public Quantum Metal component allowlist; bounded declarative options (mm/um/orientation/layers); transmon connection pads, resonators, launch pads, terminations, CPW routes, explicit ordered anchors and pathfinder collision constraint. All terminal name, pin, net and geometry checks fail closed. Deterministic sorted build and immutable recipe SHA-256 returned via `build_qdesign(layout) -> QDesignBuild` for A03 in-process consumption.
2. `tests/adapters/test_quantum_metal_recipe.py`: real validation/negative tests, layer map mismatch, missing/unauthenticated junction assets, no fallback, malformed GDS rejection.
3. `tests/adapters/test_quantum_metal_native.py`: **conditional only** real `qiskit_metal` QDesign pin/net, geometry, native GDS render, structural readback, missing pin/cell/mismatched-layer checks. They honestly skip with explicit reason on this runner.
4. `docs/agents/A02.md`: recipe interface, sample input, HOLD rules, dependencies and schema migration request.
5. This report.

GDS write path remains exclusively `QGDSRenderer.export_to_gds`. Read-only, bounded GDSII structural record scanning checks HEADER/BGNLIB/UNITS/ENDLIB, nonempty cells, geometry records, layer presence and allowed map. **No direct alternative GDS writer or library was added**. This deliberately satisfies foundation's frozen `tests/ui/test_static.py` rule forbidding direct GDS implementation libraries in adapter source. The inspector does not establish DRC, cell placement, netlist correspondence, mask signoff or correctness of geometry.

## Test execution and actual raw logs

Final command: `PYTHONPATH=src python -m pytest -ra tests` from WORK/SQE-Studio.
Final result and actual exit code: **0**, `42 passed, 5 skipped, 2 warnings` (the 5 native-only cases skipped because `qiskit_metal` is not installed). Raw stdout/stderr, environment, command and `ACTUAL_TEST_EXIT_CODE=0` are in `logs/A02-tests.log` in the delta.

An earlier full run yielded 40 passed, 5 skipped, 1 failed (a frozen static rule rejected even the word naming a direct GDS-inspection dependency). That finding was addressed **without changing any unowned test or contract** by replacing that dependency with bounded read-only GDSII structure inspection; the final full suite is reported above. No claim of native pass is made.

## Inputs / provenance boundary

`project['layout']` is the sole design recipe. Native run consumes `study['kind']='gds_draft'`, the immutable caller-supplied project snapshot and a worker-controlled output directory. The frozen worker owns source revision identification, source digest and artifact SHA-256 in `sqe.artifact.v1`; A02 never invents project revision evidence.

The accepted GDS mask input additionally requires `layout.gds.layer_map.main` integer layers and `layout.gds.negative_layers` subset. Native QGeometry layer numbers and QGDSRenderer output layers must be covered. `gds_hold.json` contains recipe digest, polarity selection, layer readback, native version (when available) and `HOLD` status. If there are any transmon junctions, the native GDS export **refuses even when a `junction_cell` name is declared**, because the frozen snapshot/worker does not supply an authenticated, read-only, hash-checked junction GDS library. This is intentional fail-closed behavior rather than a finished junction-mask workflow.

## Blocked checks / residual limitations

- **Blocked:** real Quantum Metal installed runtime/API and Windows 11 engine smoke tests; actual QDesign/QGeometry construction, route convergence, fabricated-cell verification, GDS file render and KLayout/external viewer acceptance.
- **Blocked:** complete junction/mask mapping, DRC/LVS, PDK, polarity/ground verification, chip packaging, fabrication signoff; no GDS release qualification.
- **Restricted intentionally:** route endpoints must reference distinct explicitly named terminal pins, each terminal pin may participate in at most one route; each route net is unique. Branched nets, vias, multi-chip links, arbitrary lead jogs, custom QComponents and advanced routing expressions are not inferred.
- **Known interoperability risk:** different Quantum Metal distribution versions may change behavior of QComponent options or route net IDs; the conditional native tests MUST run in the target independently installed runtime before A09 accepts a native release.
- **No** substitute physics, native solver, S-parameters, experimental measurements, fabricated GDS data or fake junction cells.

## Typed frozen-contract migration requested from A09

Propose versioned `sqe.project.v2` / reviewed recipe extension: `gds.junction_asset` typed as
`{artifact_id: UUID, sha256: lowercase hex64, source_revision_id: UUID,
validated_cell_ids: list[identifier], cell_layers: list[int], unit: documented_unit,
evidence_id: UUID}`. A06/A08 trusted worker must resolve it inside run-scoped immutable storage and validate digest+cells+layers before handing only that trusted path to `QGDSRenderer.options.path_filename`. Extend A01/contract validation for explicit branched net graphs and typed component/pin/constraint/layer mapping, plus immutable provenance of any derived geometry and process layer mapping. A09 owns schema/version changes; **none were made by A02**.

## Qualification conclusion

**Delta acceptance candidate only; native geometry, GDS readback, Windows and foundry qualifications remain BLOCKED/NOT QUALIFIED.** Source conflict resolution is delegated to A09; no cross-agent edits or merge performed.
