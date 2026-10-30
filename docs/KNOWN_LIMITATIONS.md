# Current limitations (updated for integrated GUI/EDA consolidation)

This document replaces the outdated pre-agent foundation descriptions. **Status: EXPERIMENTAL / NO SCIENTIFIC RC.** No feature should be promoted on the basis of only a software unit test.

| Area | Present code path | Still missing / blocked |
|---|---|---|
| Design | Generic `sqe.project.v1` revisions, editable device family/templates, symbolic canvas | Trustworthy native QGeometry/field/mesh drawing in GUI; general geometry variable graph |
| Quantum Metal | Reviewed QComponent recipes, QDesign/GDS adapter | Real-laptop end-to-end regression, schematic ↔ geometry/LVS identity, GDS/foundry signoff |
| SQDMetal/Gmsh/Palace | Declarative native studies, preflight, output hashes, eigenmode inspection | Installer/probed Palace executable, real test cases with port/mesh/material review, converged driven/capacitance and kinetic sheet workflows |
| scqubits | Native adapter for explicit independent transmon/fluxonium and composite quantum model inputs; spectrum inspection | Independently qualified basis and measurement benchmarks; trusted EM-derived parameter lineage |
| Kinetic inductance | Research-only reviewed sheet-deck prototype exists | General GUI revision-bound sheet boundary model and native result validation; unavailable as a toggle |
| EPR | Native EPR artifacts may be preserved | Junction/mode identity, normalization/participation checks and versioned EPR → Hamiltonian conversion |
| JosephsonCircuits.jl | Deliberately fail-closed adapter | Verified native Julia integration, RF port conventions, cross-simulator validation |
| Comparison | Hashed native spectrum/EM display; compatible input and run comparison | Automatic field-based mode matching, full complex RF comparison and uncertainty propagation |
| Optimization | Native-study numeric sweeps bounded to 24 points | Geometry-variable graph, true feedback optimization with validated observable/constraint evaluator |
| Platform | Local authenticated HTTP app and Python Windows `.pyw` launcher | Signed standalone installer, live Windows/Chromium acceptance and all-native laptop benchmark |
| Fabrication | Export intentions with HOLD | Actual PDK, DRC/LVS, ground/layer/etch review and independent foundry signoff |

## How to report scientific status

Mark separately: *design draft*, *deck prepared*, *native run completed*, *result hash/units verified*, *mesh/basis converged*, *reference method reproduced*, *independently validated*, and *fabrication released*. None implies the next. A QPU is not the only goal: the same rules apply to resonators, readout, parametric amplifiers and microwave components.

See [engineering principles](DEVELOPER_PRINCIPLES.md), [architecture](EDA_EXTENSION_ARCHITECTURE.md), and [literature-based cases](SCIENTIFIC_DESIGN_CASES.md).
