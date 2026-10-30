# SQE Studio — One GUI, one design-to-simulation loop (experimental)

## Product intent

SQE Studio is an integrated **design / native simulation / expert comparison / design revision** workspace for superconducting devices, not an experiment registry and not a resonator-only wizard. A QPU is one family among resonators, readout paths, amplifiers and other superconducting/RF circuits. Guided and Expert are two views of the same `sqe.project.v1` model. The only computational backends are the installed native engines; a visual preview never substitutes for CAD/GDS or an EM solution.

## Laptop workflow — no command-line operations in the design flow

**Open SQE Studio** using the Windows double-click `Launch SQE Studio.pyw` launcher in the source package (requires an installed Python interpreter with Tkinter), then register with the one-time token displayed by that local desktop launcher. On other platforms an installer or GUI desktop launcher is still needed; the wheel alone is not a desktop executable.

1. **New project:** choose Blank or any supported starter from the general catalog (CPW eigenmode, independent transmon spectrum, fluxonium flux sweep). The same dialog shows literature-driven planned cases and their missing scientific bridges. `CPW resonator / native EM study` creates an ordinary editable project, not a new route or specialized app. Its geometry is an *adaptation* of a SQDMetal worked example, not a reproduced result.
2. **Specifications:** enter quantitative targets, units and tolerances. For later native comparisons, supported explicit names are `f01` with GHz (scqubits `E1-E0`) and `em_mode_1`, `em_mode_2`, etc., with GHz (ordinal Palace eigenmodes; *mode identity unverified*).
3. **Schematic:** edit electrical intent (not LVS). `Layout` supports the reviewed Quantum Metal QComponent catalog, including launchpads, terminations and routed CPW primitives; select an element and edit its properties in ordinary forms. The layout canvas visualizes **intent**, with dashed nets that are not actual QGeometry or GDS.
4. **EM analysis:** edit the material stack, boundaries, ground, physical port-to-QComponent mapping, mesh refinement, eigenmode/capacitance/driven-study settings. Record **explicit reviewer, HTTPS source and rationale** for assumptions. An example ground is **not** pre-approved, even after material review: inspect the actual QDesign/Gmsh physical features before checking it. Run `Check draft mapping` to see fail-closed adapter preflight reasons; save a revision, then request a native deck/solve if installed.
5. **Quantum models:** scqubits uses explicit Hamiltonian values, with no unreviewed EM-derived parameters. JosephsonCircuits.jl remains blocked pending a verified native adapter and port/netlist mapping.
6. **Results:** inspect content-hash-verified native spectra/Palace eigenfrequencies, compare engineering goals, compare compatible native runs, and vary the numeric inputs of a saved native study via sequential bounded parametric exploration. The backend uses the existing real `Jobs.start_sweep` and permits a maximum of 24 points. No optimizer, surrogate model, unverified mode matching or synthetic solver output is introduced. To explore *layout dimensions*, edit the parameter in the layout GUI, save a new revision and run the native EM study again; automatic topology/geometry sweeps require a future versioned graph contract.
7. **Fabrication:** always HOLD until independent PDK/DRC/LVS and foundry signoff.

## What this build does **not** provide yet

- Direct native 3D rendering of QGeometry and mesh inside the browser; existing canvas is a connectivity/placement preview, with precise labeling.
- End-to-end automated EM-to-Hamiltonian extraction (EPR/mode/junction mappings remain scientifically unreviewed). Raw EPR can be preserved by A03, not auto-quantized.
- Automatic kinetic inductance solve in the general A03 worker. The earlier research utility prepares reviewed native Palace sheet-impedance decks; it has **not** been promoted into a general revision-bound GUI capability. Current A03 maps an explicit aluminium PEC stack only. It would be misleading to offer an operational Ls toggle.
- Physical geometry sweeps across multiple QDesign snapshots; the implemented sweeps vary scalar numeric `study.inputs` and run native engines sequentially. No convergence claim is implied.
- Independently validated native Quantum Metal, SQDMetal/Palace, scqubits, JosephsonCircuits.jl, Windows installer or real browser qualification in this environment.
- QuantumPro feature parity. Keysight's platform provides more integrated EM, material, co-simulation, quantum extraction and nonlinear design capabilities than this experimental build.

## Design invariants

- Only authenticated, CSRF-checked APIs serve catalogs, saved revisions, design checks, jobs, sweeps and results. A template cannot select dynamic Python imports or alternate execution routes.
- Project and job schemas, `FOUNDATION_LOCK.json`, frozen contracts and agent protocol are unchanged.
- A design check validates declaration structure, **not** an actual EM simulation, and does not turn material/source review into an independent scientific endorsement.
- Native job results, including sweep points, require valid project revision and content manifests. Failures remain failures, not substituted approximations.

## Scientific design cases and developer rules

The authoritative catalog and its readiness gates are in [scientific design cases](SCIENTIFIC_DESIGN_CASES.md). New features must follow [developer principles](DEVELOPER_PRINCIPLES.md) and [EDA extension architecture](EDA_EXTENSION_ARCHITECTURE.md). Scientific examples are not separate tools.

## Literature basis

- [SQDMetal worked examples](https://sqdlab.github.io/SQDMetal/examples/index.html): native capacitance, eigenmode, RF driven, EPR and resonator workflows on Gmsh / Palace.
- [SQDMetal Palace simulation guide](https://sqdlab.github.io/SQDMetal/simulations/simpalace.html): native solver parameters, ports, mesh, kinetic inductance hooks and EPR methods.
- [Keysight QuantumPro](https://www.keysight.com/us/en/products/design-engineering-software/electronic-design-automation/quantum-design-suite/quantum-em-professional-quantumpro.html): benchmark capabilities for integrated layout, EM, quantum extraction and superconducting materials; commercial product references are comparison targets, not claims of parity.
