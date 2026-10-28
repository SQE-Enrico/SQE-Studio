# Reusable workflow projects (v0.15.0)

Use project-local data and an ordered JSON DAG; each step has a chosen **engine**,
**operation**, **source**, optional **needs** and **settings**. Each output lives
under `steps/<id>/` in an immutable run directory, with SHA-256 checks. These
are independent of the legacy single-transmon Palace sample.

| Project | Requires | What it proves |
| --- | --- | --- |
| `native-1q/` | core SQE | 1Q graph modes, RF sweep, JosephsonCircuits SI export; no field solve |
| `quantum-models/` | scqubits extra for first step | Real scqubits transmon numerical diagonalization and 4Q Julia netlist export |
| `metal-palace/` | Python 3.11, Quantum Metal + SQDMetal + gmsh, explicit trusted-code flag | QComponent-based QDesign and SQDMetal Palace mesh/config preparation; **not** a validated FEM solve |

From repository root:

```sh
python -m sqw ecosystem doctor
python -m sqw ecosystem plan --project examples/ecosystem/native-1q/workflow.json
python -m sqw ecosystem run --project examples/ecosystem/native-1q/workflow.json --out build/eco-native-1q
python -m sqw ecosystem verify --out build/eco-native-1q
```

For `metal-palace/` add `--allow-project-code` to the `run` command;
it loads the project's `build_design()` Python factory. **Only use trusted
local source files.** The example intentionally defaults to preparing a
candidate solver model rather than solving it. To request a real solve, set
`settings.execute` to `true` and add `--allow-solvers`; audit its material,
ports, boundaries and convergence independently first. The example does NOT
claim this qualification.

The generic workflow CLI does not yet run inside the Studio web job queue;
the original Studio projects and Palace diagnostic UI remain unchanged.
