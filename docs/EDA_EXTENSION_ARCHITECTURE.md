# EDA extension architecture and work packages

## The single computational loop

```
Design targets / constraints
      |  sqe.project.v1  (immutable revision)
      v
Schematic / QComponent layout  --------> native Quantum Metal QDesign / GDS (HOLD)
      |                                  |
      | reviewed geometry/materials      | verified identities, layers, nets
      v                                  v
SQDMetal / Gmsh / Palace EM [capacitance, eigenmode, RF ports]
      | native artifacts + provenance + convergence + expert matching
      +----- verified coupling / EPR / effective circuit parameters [BLOCKED]
      |                                       |
      v                                       v
EM result comparison              scqubits Hamiltonian/spectra [EM edge BLOCKED]
                                              |
                 explicit independent inputs -> scqubits native spectra [CONDITIONAL]
Schematic + verified RF ports ------> JosephsonCircuits.jl [BLOCKED]
      |                                                  |
      +---- native results / targets / scientific comparison
                                  |
                                  v
                      design revision / guided optimization
```

The application is a **design tool**, not a repository of run logs. Revisions and hashes support safety and reproducibility *in service of making the next better design*. The thin UI is a controller/view: do not implement physics in JavaScript.

## Current module boundaries

| Module | Responsibility | Extension rule |
|---|---|---|
| `contracts.py`, `contracts/*.json` | Frozen v1 project/study schemas and protocol | Versioned migration and compatibility tests for changes; never silently extend project keys |
| `design_library.py`, `_starter_models.py` | Allowlisted, editable starting models | Add a standard `sqe.project.v1` template, never a custom solver path |
| `eda/use_cases.py` | Read-only literature-based case definitions, acceptance conditions and readiness | Add citations, no invented outcomes; planned cases have `starter_template=None` |
| `eda/capabilities.py` | Explicit cross-domain capability edges and missing gates | Only change `blocked` to `native_conditional` after engine implementation plus evidence |
| `interop/` | Typed quantities, physical ports, dimensions, transformations, compatibility | Expand schema through approved versioning; no implicit reference-plane or unit conversion |
| `adapters/` | Native engine calls and verified input/output checks | Adapter owns engine version, safe parameters and exact native output; no arbitrary user code |
| `orchestration/`, `jobs.py`, `worker.py` | Revision-bound work, timeout/budgets, artifact validation and sweeps | Never bypass source hashes or let background jobs masquerade as complete |
| `server.py`, `store.py` | Authenticated API, ACL, revisions and safe local service | New routes require authentication + tests; no LAN exposure |
| `web/` | Generic guided/expert forms, symbolic preview, observations and iteration | Use the same data model and controls; no bespoke use-case screens |

New read-only API catalogs `/api/design/use-cases` and `/api/design/capabilities` exist for the generic GUI; neither exposes arbitrary execution or produces physics. Supported examples are ordinary templates obtained from `/api/design/templates` and created with the standard `/api/projects` POST.

## Proposed extensibility seams (NOT IMPLEMENTED)

1. **Typed design parameters / constraints:** add a versioned parameter graph for layout dimensions, electrical parameters, materials and experiment conditions. Variable identity is different from a string path to a JSON property; dimensional analysis, permitted bounds and revision snapshot are mandatory.
2. **Native solver capability handshake:** native engine/version feature detection, supported analyses, study restrictions, runtime budget, mesh quality, produced typed artifacts. Do not treat a Python import as qualification.
3. **Verified transformations:** physical interfaces rather than ad-hoc conversion scripts. Implement `layout → native QDesign`, `QDesign → mesh/deck`, `Palace EPR → Hamiltonian`, `geometry/materials → kinetic sheet model`, `schematic → RF netlist`, each with full input and output evidence and expert signoff when unresolved.
4. **Optimization service:** objective + constraints in explicit units; deterministic candidate generation, revision-save → native job → observable verification → constraint evaluation, with visible compute budget, failure/timeout handling and human-approved stopping conditions. No optimization result without native evaluations.
5. **Visualization and comparison:** native field/mesh viewers, complex RF response (ports and reference impedance), mode matching by field overlap, parameter trace from EM through Hamiltonian, error/convergence bars, target residuals and side-by-side revisions. Independent implementations may disagree; disagreements are a first-class design input.
6. **Fabrication interface:** PDK-versioned rule checks, LVS comparison of circuit/physical nets, GDS mask validation, export signoffs. Separate engineering "CAD generated" from foundry "approved".

### Sample future solver bridge boundary

A cross-engine conversion should conceptually receive a `source_artifact` (typed, SHA-256, origin revision, engine/version), `physical_identity_map` (ports, surfaces, modes, junctions), `assumptions` (material/units/reference frame), `operator_review` (reviewer/date/rationale) and a `requested_target` type. It must yield either a traceable, versioned derived artifact **or an explicit blocked reason**. These are design requirements, **not** a working API and not authorization to bypass frozen A01/A06 artifacts.

## Prioritized engineering backlog

**P0 — credible single-design loop:** native QDesign rendering in UI; validated layout→SQDMetal port/layer mapping; actual local Palace eigenmode on small CPW; manifest/units; mesh convergence; browser acceptance on Windows and Linux; verify native scqubits against cutoff convergence.

**P1 — physics across engines:** versioned EPR/junction mapping and passivity/participation checks; supported kinetic inductance sheet model with physical-surface review; independently replayed coupled-transmon/resonator benchmark; correct complex S-parameter and RF port reference-plane handling.

**P2 — design optimization:** constrained parameter graph spanning geometry and EM; bounded optimizer feeding actual native jobs; design-variable sensitivities and surrogate models marked exploratory; cross-engine target dashboard; cached results keyed on revision/options/version without claiming uncomputed work.

**P3 — product breadth:** readout filter/multiplexer, Josephson parametric amplifier, multi-qubit layout, PDK import, LVS/DRC and a signed desktop installer. Hardware fabrication and physical measurement validation require external partners.

## Migration and provenance protocol

Do not update `FOUNDATION_LOCK.json`, the original `contracts/`, `tools/delta.py`, `docs/AGENT_PROTOCOL.md`, or source agent mandates merely to make tests pass. The foundation lock records **historical baseline**, not a claim that the current expanded tree equals the locked digest. Track cumulative changes separately in release manifests. If `sqe.project.v1` cannot represent a new capability, propose `sqe.project.v2`, write migration/rejection rules, versioned artifact compatibility tests, native cross-engine regressions, and obtain code-owner/integrator approval before enabling it.
