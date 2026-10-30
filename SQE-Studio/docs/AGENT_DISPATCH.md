# Agent launch plan — one unchanged foundation, eight independent deltas

## Prepare a single source baseline

Record the SHA-256 of `SQE-Studio-product-foundation.zip`, and preserve this exact file for all agents and A09. The ZIP includes all source, frozen contracts, detailed instructions, test fixtures and the delta tool; it is not itself an integrated release.

## Dispatch in parallel

- A01: typed transformations and provenance / unit/port validation.
- A02: Quantum Metal native QDesign, routing, GDSII and layer/pin mapping.
- A03: SQDMetal/Gmsh/Palace meshing, deck generation, native EM and field data.
- A04: scqubits physics models and verified Hamiltonian spectral inputs.
- A05: JosephsonCircuits.jl native circuit and RF analysis.
- A06: deterministic artifact DAG, job scheduling, caching, optimization loops.
- A07: unified commercial-quality UI, design canvases, native result viewers.
- A08: security, Windows packaging, sidecars and executable health checks.

**Each agent receives the complete original foundation plus ONLY its `agents/Axx.md`.** The agent may use read-only references throughout the foundation, but may edit only paths in `contracts/ownership.json`. Agents do not need each other's delta; for cross-boundary feature requests, deliver an ABI/migration recommendation to A09 rather than modifying foreign files.

## Integrate only at the end

Send A09 the exact original foundation and all eight finished `A01-delta.zip`..`A08-delta.zip`. No incremental early merge. A09 rejects package/ownership/hash/frozen contract errors, runs admission and dry-run first, merges deterministically and performs genuine end-to-end qualification. Failed native solver or browser checks must remain visible and block release approval.

## Definition of 'working product'

From one versioned project, the user can (1) define a generic schematic and design intent; (2) create a QDesign through Quantum Metal and render real GDS; (3) derive a typed, physically valid 3D EM setup through SQDMetal/Gmsh; (4) execute Palace native studies with verified ports and mesh convergence; (5) derive/fit supported Hamiltonian quantities under explicit assumptions and run scqubits; (6) run compatible Josephson circuit and RF analyses through Julia; (7) compare native artifacts across project revisions; and (8) deliver `HOLD` fabrication artifacts with DRC/LVS/foundry checks explicit. For every step, unknown or incompatible inputs block safely rather than producing visual imitations of science.

## Priority of integration

1. A01 port/unit/provenance contract + A02 QDesign source of truth.
2. A03 bridge to Gmsh/Palace with realistic small chip + actual native solver acceptance.
3. A04/A05 consume only explicitly validated model/nets.
4. A06 attach artifacts and iteration graph to immutable revision and provenance.
5. A07/A08 unify UX and installer/diagnostic quality.

The integrations are separate by file ownership but must converge on the frozen interop contracts. If a contract is genuinely insufficient, A09 handles a documented versioned migration after reviewing all recommendations.
