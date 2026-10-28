# SQE Studio 0.16.0 — multi-engine quantum EDA workflow

> Scope: a **topology-independent, reproducible workflow** available from
> the **Research Experiments Web UI** in the local Studio workstation. This is not a claim that SQE
> has feature parity, model accuracy or qualification equivalent to ADS QuantumPro.

## 1. Architecture: reuse solvers, do not fork them

```text
                        project/workflow.json
                                 |
                        validate + plan DAG
                                 |
                 +---------------+----------------+
                 |               |                |
           design geometry  reduced circuit   quantum Hamiltonian
           Quantum Metal     QuantumLab /      scqubits
           QDesign            JosephsonCircuits   (E/h GHz)
                 |                |               |
             SQDMetal        Julia netlist/      spectra
             Palace + Gmsh   linear S (opt-in)
                 |
              Palace FEM (external, opt-in)
                 |
          raw native results + validation
                                 |
         run.json + input snapshots + artifact SHA-256
```

The provider is selected **per step**, not globally. Each step consumes a local
file and outputs its own directory; independently designed and mixed-topology
circuits can use the same document structure. This adds to (does not replace)
SQE's older *fixed-device* `sqw run`/`sqw stage` and its separate Web diagnostic
pipeline. The original v0.14.1 QPU convergence/audit tests are retained.

**Provider/action catalog** (Python imports are lazy):

| Adapter | Input | Output/state | External stack |
| --- | --- | --- | --- |
| `quantumlab.modes`, `quantumlab.sparameters` | QuantumLab JSON, 1–32 QPU assignments | `result.json`, `COMPUTED_REDUCED_ORDER` | bundled NumPy/SciPy, **not field FEM** |
| `scqubits.spectrum` | Transmon/Fluxonium/TunableTransmon JSON or custom Circuit YAML | `spectrum.json`, `COMPUTED_QUANTUM` | real scqubits API; E/h in GHz, input parameters are nominal unless extracted |
| `quantum-metal.inspect` | checksummed SQE positive-metal manifest or a trusted `build_design()` Python file | `inventory.json`, `INSPECTED_GEOMETRY` | real `qiskit_metal` QGeometry/QComponents |
| `sqdmetal.palace_capacitance`, `.palace_eigenmode` | QDesign as above | SQDMetal native mesh/config files, `PREPARED_NOT_SOLVED` by default | real SQDMetal Gmsh/Palace API; `SOLVED_UNQUALIFIED` only on explicit solver request |
| `josephsoncircuits.export` | QuantumLab JSON with explicit JJ branches | SI Julia netlist and source mapping, `EXPORTED_NOT_SIMULATED` | no Julia needed to export; rejects underspecified SQUID |
| `josephsoncircuits.linear_sweep` | QuantumLab JSON with ports | real Julia invocation and raw complex S in CSV, `SOLVED_LINEAR_UNQUALIFIED` | JosephsonCircuits.jl, explicit solver opt-in; **no pump/nonlinear HB** |

The `sqdmetal` adapter uses the public `PALACE_Capacitance_Simulation` or
`PALACE_Eigenmode_Simulation` class, `add_metallic`, optional
`add_ground_plane`/`create_port_JosephsonJunction`, `prepare_simulation`, and
optionally `run`. It **does not** invent a Maxwell-matrix mapping: the native
outputs still need inspection, convergence and explicit node/port matching.
The simple SQE positive-mask bridge lacks CPW routes and complete junction
physics; it **cannot** be used to request a solver run directly. Use a
properly reviewed QDesign source for that.

## 2. Workflow document and execution

Example from `examples/ecosystem/native-1q/workflow.json`:

```json
{
  "schema_version": 1,
  "name": "One-qubit lumped reference without FEM",
  "steps": [
    {"id":"modes", "engine":"quantumlab", "operation":"modes", "source":"design.json"},
    {"id":"rf", "engine":"quantumlab", "operation":"sparameters",
     "source":"design.json", "needs":["modes"], "settings":{"points":31}},
    {"id":"julia-netlist", "engine":"josephsoncircuits", "operation":"export",
     "source":"design.json", "needs":["modes"]}
  ]
}
```

For regular use, open **Research Experiments** at `/experiments.html`, choose
**One-qubit lumped reference without FEM**, inspect the plan, click **Run
selected workflow**, and download the resulting support ZIP. Developers can
still invoke the underlying module from automation or CI; no CLI is necessary
for ordinary design, tests, debugging, or report export.

Each `source` is a **relative** project file path. A step may also consume an
output of a preceding step with `{"step":"step-id","file":"result.json"}`;
its ID must be listed in `needs`. The current built-in operations expect their
specific input file types, so a step dependency does *not* imply that two
incompatible numerical formats magically convert. File references reject
parent traversal, symlink escape and absolute paths. A run is only allowed in
an empty directory. Every input up to 32 MiB gets a self-contained snapshot
under `inputs/`, with a SHA-256 for every produced artifact and a version
record in `run.json`. Integrity checks do **not** certify physical accuracy.

Failures remain recorded in `run.json` with state `FAILED`; no success data is
created to disguise unavailable external software. Exact versions of third-
party engines should be recorded with the science notebook / qualification
report for published numerical comparisons.

## 3. Optional installations — do not overload the base Studio env

- **Core:** Python 3.11–3.13, install SQE Studio as usual. Reduced-order tests,
  reference projects, and Julia *export* run without any external engine.
- **scqubits:** `python -m pip install 'scqubits>=4.3.2,<5'` in the environment
  used by `sqw ecosystem run`. Custom Circuit YAML uses the public
  `scqubits.Circuit.from_yaml_file` API (4.3.2+). For independent spectra use
  `examples/ecosystem/quantum-models/`.
- **Quantum Metal:** `python -m pip install 'quantum-metal[mesh]>=0.9,<1'`.
  The distribution is **quantum-metal**, but the Python import is still
  `qiskit_metal` at the time of this release. The Windows `WINDOWS-QUANTUM-METAL-SETUP.cmd`
  creates a separate `.venv-metal` environment; install SQE in that same
  environment (`.venv-metal\\Scripts\\python -m pip install -e .`) or run with
  `PYTHONPATH=src` for development.
- **SQDMetal:** its published main branch presently specifies **Python 3.11
  only** and depends on `quantum-metal[full]`, COMSOL-related dependencies and
  other heavy packages. Do not force it into the regular Python 3.12/3.13
  Studio worker. Use a *separate Python 3.11 virtual environment*, install
  the SQDMetal package from its official repository after verifying its
  version/requirements, then install SQE editable in that env. Verify
  `python -c 'from SQDMetal.PALACE.Capacitance_Simulation import PALACE_Capacitance_Simulation'`.
- **JosephsonCircuits.jl:** run the existing
  `WINDOWS-JOSEPHSONCIRCUITS-SETUP.cmd` or create a Julia environment with
  `using Pkg; Pkg.add("JosephsonCircuits")`. The setup script uses
  `.julia-josephson`. Set `SQE_JULIA_ENV` to its absolute path before executing
  a Julia sweep, or add `settings.julia_project` with that path in the
  workflow. Specify a Julia executable as `settings.julia` if needed.

On Windows, execute with the *Python environment that contains the needed
engine*. The Web app retains its own stable base Python environment and
isolated diagnostics. Julia and Palace are **not automatically installed or
run** by the ecosystem commands.

## 4. Access controls and reproducibility

Loading a Python source file that defines `build_design()` runs arbitrary
trusted project code. `--allow-project-code` must be explicitly supplied;
never enable it for untrusted ZIPs/remote users. The flag is intended for an
operator-controlled local Web interface, available to the authenticated workstation administrator.
Python input imports remain restricted; only the bundled trusted factory can
be explicitly enabled in the Web UI. To
run SQDMetal/Julia solvers, the workflow must request `settings.execute=true`
(SQDMetal) or `josephsoncircuits.linear_sweep` (Julia), **and** the operator
must pass `--allow-solvers`. The original Palace Web worker queue and its
resource policy are a separate subsystem; the local Web runner has no equivalent distributed job
scheduler, distributed orchestration or sandbox. Treat external native jobs
as locally trusted scripts and apply your own time/memory limits. The Julia
linear sweep has a ten-minute process timeout but SQDMetal's native `run()`
has no in-process wall-clock timeout yet.

The Julia `linear_sweep` operation is intentionally **not** a nonlinear
harmonic-balance study; pumped gain, quantum noise and Floquet analysis require
new qualified, version-specific adapters. The SQDMetal `SOLVED_UNQUALIFIED`
state means the external `.run()` returned normally; inspect solver logs and
convergence before using any physical values. Device fabrication remains HOLD.

## 5. What would still be needed to compete with ADS QuantumPro?

| Layer | New 0.15.0 integration | Critical gap before commercial-grade parity |
| --- | --- | --- |
| Schematic/netlists | Generic JSON DAG, multi-QPU nominal circuit, Josephson export | Full visual schematic editor, library management, SPICE interoperability, parametric design rules |
| CAD/layout | Quantum Metal QDesign components and inventory | True bidirectional editable layout, robust nets/ports, advanced DRC/LVS/PDK, chip-to-package/co-design |
| EM | SQDMetal → Gmsh/Palace, existing native Palace/QPU test bench | Mesh/boundary QA at scale, robust EM extraction transfer, automated convergence, calibrated losses, radiation and packaging |
| Circuit / quantization | scqubits exact spectra, QuantumLab reduced order | Arbitrary coupled Hilbert spaces, validated EPR/LOM, experiment-calibrated uncertainty propagation |
| Nonlinear / microwave | JosephsonCircuits export + opt-in linear S | Pumped harmonic balance, transient/nonlinear verification, noise, mixer, qubit-control and network analysis |
| Reproducible science | Provenance, input snapshots, SHA integrity, regression tests | Cross-backend benchmarks, approved native solver installation matrices, traceable experimental and metrology references |
| Operations / product | Browser Studio and local multi-engine experiments | Integrated web job orchestration for all engines, scheduling, secured plugin execution, industrial UX and support |

**Scientific acceptance gate:** validate named material/ground/port geometry,
check independent mesh refinements and E/M energy balance, match modes by
fields and inspect solver residuals. Then compare cross-tool extracted
capacitances, eigenmodes and S-parameters on independent *measured* reference
chips. Neither a mock in CI nor an API import fulfills these gates.

## 6. API sources and version maintenance

- Quantum Metal docs: <https://qiskit-community.github.io/qiskit-metal/installation.html>
- SQDMetal Palace classes/examples: <https://sqdlab.github.io/SQDMetal/simulations/simpalace.html>
- scqubits custom Circuit API: <https://scqubits.readthedocs.io/en/latest/guide/circuit/ipynb/custom_circuit_define.html>
- JosephsonCircuits.jl API: <https://josephsoncircuits.org/stable/>

Confirm package APIs against an installed lockfile before enabling native
solves. SQDMetal and Julia calls were not run against installed third-party
runtimes in this release environment; these paths are tested only against
public API stubs and require qualification on the target workstation.

## 7. Extend the engine registry without editing SQE core

External adapters can be packaged by independent groups as trusted Python
entry points in the `sqw.ecosystem_adapters` group. An entry-point name is the
engine key; the loaded object must expose a tuple `operations` and a callable
`run(operation, source, settings, output, *, allow_solvers)` returning
`(status, relative_artifact_filenames, metadata_dictionary)`. For example,
a plugin's `pyproject.toml` can declare:

```toml
[project.entry-points."sqw.ecosystem_adapters"]
my-solver = "research_solver.sqe_adapter:adapter"
```

The plugin can then appear in `workflow.json` as
`{"engine":"my-solver","operation":"analyze",...}`. Plugins are **not
loaded by default**: the operator must pass `--allow-plugins` to `sqw
ecosystem plan/run/doctor`. Third-party plugin entry points can execute
arbitrary Python and must be installed and activated only from a trusted
supplier. Output names are constrained to the step directory and hashed by
the core orchestrator. This entry point is the planned seam for future MoM,
HFSS/Q3D, AWR, independent material models or measured-data extractors.
