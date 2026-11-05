# Product development execution

The owner's 2026-11-05 execution directive sets the product goal: practical,
scientifically credible QuantumPro competition through complete workflows.
Historical source locks document baselines; justified current changes require
meaningful numerical and product validation. Authentication, CSRF, provenance,
truthful evidence and human fabrication authorization remain required.

The current stack remains useful: Python HTTP, SQLite revisions, modular browser
UI, native Quantum Metal/SQDMetal/Gmsh/Palace, scqubits and JosephsonCircuits.
No frontend rewrite or replacement numerical solver is justified by current gaps.
The [capability matrix](QUANTUMPRO_COMPETITOR_MATRIX.md) distinguishes the base
W3704B target from nonlinear extensions.

| Order | Increment / acceptance | Owning implementation | Required evidence |
|---|---|---|---|
| 1 | Finish Case A: saved native capacitance to spectrum, explicit pads/ground/junction inputs | transmon_design.py, capacitance_identity.py, existing extraction, UI and testing/native_transmon.py | Native profile, stale/tampered-source guards, real browser, Software and wheel |
| 2 | Case B: parametric transmon plus CPW; saved native eigenmodes and supported EPR inspection | Quantum Metal recipes, Palace eigenmode adapter, native result readers and result UI | Genuine local solve, original port-EPR/eig files, native SQDMetal readback, browser and negative tests |
| 3 | Establish numerical confidence for A/B before design claims | Existing jobs/sweeps and convergence readers; #4 | Predeclared mesh/domain/material series, independent reference, mode identity where applicable |
| 4 | Case F/G: GUI geometry edit, fresh solve, comparison, export/reopen/restart | component_editor, jobs, comparisons, projects/revisions | Separate run/revision hashes, real changed result, persistence and source rejection |
| 5 | Case D and driven analysis: improve native EM setup, fields and port studies | Existing Palace and VTK integrations | Published resonator/port reference, frequency and field checks, convergence |
| 6 | Case C: two-transmon native matrix and validated coupled quantum model | Declared multi-island geometry identities, existing reducer/scqubits | No guessed matching; native matrix, coupled-basis evidence, GUI saved results |
| 7 | Case E: schematic-to-native Josephson linear/HB response | Existing josephson_adapter and schematic editor | Native Julia references, operating point/harmonic convergence, saved UI workflow |
| 8 | Extend EPR/co-simulation, film properties, optimization and scriptability | Typed source-bound interop, native functions and current orchestration | Independent references, native end-to-end cases, mode-aware objectives |

Each increment updates the test inventory and evidence documents, runs focused
checks and Recommended, then the applicable native and broad integration checks.
Ordinary local implementation and isolated open-source dependencies are authorized.
Paid tools, administrative changes, destructive data changes and license
acceptance require owner authorization.

Commit verified increments on codex/ feature branches. Keep issue/PR evidence
current, preserve original local reports, and never merge or force-push without
authorization. Existing baseline PR #6 remains a dependency until integrated.

Completion is assessed per capability: implemented, backend tested, native
executed, frontend exercised, reference validated, or still blocked. A successful
Case A does not complete the overall product objective.
