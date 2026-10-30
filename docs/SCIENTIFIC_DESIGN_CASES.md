# Literature-informed scientific design cases

**Intent:** acceptance scenarios for the **same** GUI and native engines, not standalone demos. Cases are registered in `src/sqe_studio/eda/use_cases.py`. Their readiness and necessary transitions are visible in the New project dialog. All starter numbers are illustrative user-editable inputs; **none** are measured values or reproduced paper results. A source publication documents a *method or example*, not qualification of SQE Studio.

## 1 — Quarter-wave CPW resonator: native eigenmode workflow (starter available)

- **Reference:** [SQDMetal: Basic Eigenmode Simulation of Side-coupled Resonator](https://sqdlab.github.io/SQDMetal/examples/Palace_Eigenmode_Res_Gmsh.html) and [Sommers et al., Open-Source Highly Parallel Electromagnetic Simulations for Superconducting Circuits, arXiv:2511.01220](https://arxiv.org/abs/2511.01220).
- **Design task:** edit launchpads, route meander, CPW line width/gap, substrate, mesh and boundary conditions; compare eigenfrequency to a design target.
- **Entry:** **New project → CPW resonator / native EM study**. Existing model is an **adaptation**, not the paper's exact CoupledLineTee feedline or physical port geometry.
- **Laptop budget:** one small eigenmode study at a time; start with coarse mesh then refine; save each design revision and Palace native output. Don't imply a runtime budget or successful solve before testing the installed stack.
- **Acceptance:** native QDesign/QGeometry inspection; Gmsh feature and port IDs confirmed; Palace native eigenmode table and fields; matched mode across at least two refinements; unit-check and convergence/error assessment. Optional comparison to published frequencies requires *identical* geometry, material, boundary and solver settings; not currently met.
- **Available today:** editable model, preflight, authenticated job interface and verified result reader. **Not** guaranteed: installed native solver or converged frequency.

## 2 — Transmon quantum spectrum (starter available; independent Hamiltonian)

- **References:** [Krantz et al., A quantum engineer's guide to superconducting qubits, Applied Physics Reviews 6, 021318 (2019)](https://doi.org/10.1063/1.5089550); [scqubits Transmon API](https://scqubits.readthedocs.io/en/v4.0/api-doc/_autosummary/scqubits.core.transmon.Transmon.html).
- **Design task:** specify EJ, EC in **E/h GHz**, normalized offset charge in units of **2e**, and charge basis cutoff. Study f01 and anharmonicity and vary explicit model parameters.
- **Entry:** **New project → Transmon / explicit scqubits spectrum**. It uses the standard quantum study editor and the same revision/job API.
- **Scientific caution:** QComponent geometry and Hamiltonian values **are not linked**. Do not label EJ/EC as extracted from a pad geometry, capacitance, junction size or EM solver.
- **Acceptance:** run actual scqubits; verify eigenenergy differences E1–E0 and E2–E1, units, cutoff convergence, and normal form/model version. Any comparison to measured or published transmon requires matching parameters and provenance.

## 3 — Fluxonium spectrum versus flux (starter available; independent Hamiltonian)

- **Reference:** [scqubits Fluxonium](https://scqubits.readthedocs.io/en/latest/guide/qubits/fluxonium.html), based on the fluxonium model and harmonic-oscillator basis.
- **Design task:** explicit EJ, EC, EL (GHz), external flux (Phi0) and basis cutoff; bounded native sweep over flux. Interpret avoided crossings and state labels with expert supervision.
- **Entry:** **New project → Fluxonium / scqubits flux sweep**; regular quantum stage and results view; no proprietary runner.
- **Acceptance:** exact model/units saved; native eigenvalues over the saved flux grid; basis convergence near challenging flux points; never match eigenstates across crossings merely by row index.
- **Caution:** a quantum model starter is not a verified fluxonium CAD layout, junction array model, or material extraction.

## 4 — Superconducting thin-film kinetic inductance (planned; blocked)

- **Reference:** [Palace Boundary Conditions: Impedance / Crack](https://awslabs.github.io/palace/dev/guide/boundaries/); SQDMetal published method above.
- **Design task:** compare a PEC CPW baseline to a physically justified surface-impedance model (thin film `Crack=false` versus thick limit `Crack=true`) on the **same** geometry with reviewable Gmsh physical surfaces.
- **Acceptance needed:** material thickness, London penetration depth and model validity; explicit surface IDs; correct sheet inductance (`mu0*lambda^2/d` thin-limit or `mu0*lambda` thick-limit, per Palace conventions); physical convergence of both native solutions; field-based mode matching and uncertainty analysis.
- **Status:** a research utility can prepare experimental sheet decks, but the general **GUI revision-bound adapter remains blocked**. There is deliberately no kinetic-inductance-enabled starter claiming it can run.

## 5 — Resonator-coupled transmon: automated EM→Hamiltonian extraction (planned; blocked)

- **References:** [Minev et al., Energy-participation quantization of Josephson circuits, npj Quantum Information 7, 131 (2021)](https://doi.org/10.1038/s41534-021-00461-8), [SQDMetal worked examples](https://sqdlab.github.io/SQDMetal/examples/index.html), and [pyEPR reference implementation](https://pyepr-docs.readthedocs.io/en/latest/).
- **Design task:** construct QDesign; native Palace eigenmodes and EPR tables; map every junction to a physical surface and every mode to a field pattern; derive the effective Hamiltonian and compare native quantum predictions to independent circuit parameters.
- **Acceptance needed:** correct junction inductances and participating energy; mode normalization; positive/physical participation; stable mesh/basis; typed quantity/uncertainty lineage into scqubits; dressed transition comparison against published/experimental references only when identical device inputs are established.
- **Status:** missing a versioned, trusted EPR→Hamiltonian bridge. Preserving raw EPR files **does not** count as extraction.

## 6 — Josephson parametric amplifier: nonlinear circuit/RF (planned; blocked)

- **Reference:** [JosephsonCircuits.jl documentation and JPA worked example](https://josephsoncircuits.org/stable/), including its comparison methodology against WRspice/ADS.
- **Design task:** edit Josephson lumped topology and pump conditions; compute gain/frequency-dependent complex S-parameters, conversion and noise; compare to an independently simulated circuit under the same drive/reference-plane conventions.
- **Acceptance needed:** validated netlist schema, ports and reference impedances; real Julia runtime; harmonic-balance and pump convergence; complex S-parameter phase/magnitude; stable bias and physical losses; independent reference.
- **Status:** the native Julia adapter is deliberately blocked until it meets those requirements. No example pretends to run a synthetic amplifier solver.

## General acceptance / experimental comparison protocol

For *each* use case, distinguish: (1) **starter design input**, (2) **native engine output with verified hashes**, (3) **numerical convergence**, (4) **method reproduction** with matching reference conditions, (5) **independent measurement validation**, and (6) **fabrication qualification**. Progression is **not automatic**. Reject missing solver, stale revision, absent units, unreviewed port/mode mapping, incomplete data or nonconvergence. In a literature comparison record reference DOI/URL, exact digitized/reference values rights permitting, model differences and tolerance before claiming numerical agreement. A publication may establish scientific plausibility of a method; it cannot automatically validate an SQE implementation.
