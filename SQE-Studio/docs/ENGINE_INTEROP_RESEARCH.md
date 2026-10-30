# Research-backed interoperability decisions (29 October 2026)

## Reference products and community solutions

1. Keysight's ADS QuantumPro describes an integrated schematic -> layout -> EM -> quantum parameter extraction -> optimization loop. Its technical overview references full EM, EPR, black-box and quasi-static extraction plus nonlinear circuit simulation. **Design reference only**: the SQE foundation does not provide those capabilities automatically. Source: https://www.keysight.com/us/en/assets/3124-1387/technical-overviews/Keysight-EDA-Electronic-Design-Automation-Software.pdf
2. SQDMetal documents consuming a Quantum Metal/Qiskit Metal `QDesign` and preparing Gmsh/Palace capacitance, RF S-parameter and eigenmode simulations. This is the preferred bridge instead of rewriting a mesh generator. Sources: https://sqdlab.github.io/SQDMetal/simulations/simpalace.html and https://sqdlab.github.io/SQDMetal/index.html
3. Quantum Metal's public `QGDSRenderer.export_to_gds` is the authoritative GDS output path; junction cells and mask polarity require special handling. New community releases are `quantum-metal`, with import path `qiskit_metal` currently maintained but scheduled to change. Sources: https://qiskit-community.github.io/qiskit-metal/tut/3-Renderers/3.2-Export-your-design-to-GDS.html and https://github.com/qiskit-community/qiskit-metal
4. Palace is a native CLI solver, consuming mesh + JSON solver configuration. It supports electrostatic, magnetostatic, eigenmode, driven and transient study types. The solver does **not** create meshes. Source: https://awslabs.github.io/palace/dev/quick/
5. scqubits supplies superconducting-qubit Hamiltonian models, spectra and composite Hilbert spaces. Require explicit parameter provenance; do not infer energy scales from CAD dimensions. Source: https://scqubits.readthedocs.io/en/latest/
6. JosephsonCircuits.jl provides frequency-domain harmonic-balance and scattering models for Josephson circuits; it must consume a verified netlist and port convention. Source: https://github.com/kpobrien/JosephsonCircuits.jl
7. OpenMDAO demonstrates cross-discipline variable connections with units, data-recording and optimization. W3C PROV models entities/activities/agents and derivation chains. These are **architecture patterns**, not extra mandatory runtime dependencies. Sources: https://openmdao.org/newdocs/versions/latest/features/core_features/working_with_groups/connect.html and https://www.w3.org/TR/prov-o/

## Decisions

- **One geometry authority:** Quantum Metal `QDesign`. SQDMetal consumes it in-process/through a deterministic declarative recipe; no SQE-owned GDS or geometry solver.
- **One scientific artifact format:** every native file has a type, content hash, engine ID/version, project/revision identity, units, port mapping, assumptions and validation status. No opaque module-to-module JSON passthrough.
- **Explicit conversion gates:** electrical graph ↔ QGeometry, QDesign ↔ mesh, mesh ↔ FEM solver deck, EM observables ↔ quantization parameters and S/Y/Z ports. Each has an owner, tests and fail-closed behavior.
- **Native engines remain independent:** scqubits is not a Palace substitute; JosephsonCircuits is not an SQE reduced-order solver; an unvalidated synthetic curve is not a native S-parameter result.
- **Product UI:** progressive disclosure, few top-level choices, accessible dark canvas, one project and revision, keyboard navigation, diagrams when supported, avoid claiming any unavailable step as complete.

## Compatibility risks

Quantum Metal import path transition; SQDMetal/Metal version coupling; Palace Windows/WSL path executability; Gmsh mesh unit and boundary interfaces; Julia/Python process isolation; GDS layer/junction export mapping; basis and convergence costs on a laptop. Agents must pin/test version ranges, record exact environment and report blockers rather than paper over them.
