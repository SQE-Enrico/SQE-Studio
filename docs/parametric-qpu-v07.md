# Parametric physical QPU specification — schema v2

## Design goals

SQE Studio v0.7 introduced a reusable project-level physical schema, rather than solver-specific hardcoded materials or qubit/coupler choices. Materials and process parameters are edited in the Web parametric QPU panel and advanced JSON editor. The design model retains named nets and layer IDs through GDSII and Palace input generation.

## Parametric domains

- **Materials**: dielectric and conductor libraries with user-declared physical properties; entries are not automatically qualified loss/kinetic-inductance models.
- **Stack-up**: layer name, material, elevation, thickness, functional role, and GDS layer mapping. The FEM mesher supports only the geometries it can represent; unsupported combinations must fail closed.
- **Josephson junction process**: Dolan, Manhattan or generic process intent, declared orientation, linewidth, overlap, undercut and lead extension; evaporation-angle physics requires calibration.
- **Qubits**: built-in rectangular/floating/cross/pocket-like cell choices and user-defined rectilinear `libraries.qubit_shapes`; pin connectivity and geometry checks apply.
- **Couplers**: independent explicit objects with terminal A/B, conductor IDs and configurable dimensions; capacitive pads, interdigitated fingers, isolated CPW bus, effective tunable SQUID representation and `custom_rects` electrodes.
- **Routing**: CPW width, gap, waypoint sequences, orthogonal Manhattan paths and meanders, with ground-plane subtraction and available 2D clearance checks.

Examples: `examples/parametric-v07/dolan-4q.json`, `manhattan-2q.json`, `custom-2q.json` and `planar-9q.json`.

## Geometry versus electrical extraction

A drawn capacitor or coupler does not provide its physical Maxwell capacitance or qubit coupling merely because an estimated circuit value exists. Nominal fields are labeled separately from authentic Palace outputs. DRC is preliminary planar geometry checking; it is not a production rule deck or netlist-versus-layout signoff.

## Fabrication limitations

Dolan/Manhattan annotations are process-intent masks, not full angle-dependent evaporation and shadow-overlap simulations. Multi-material/multimetal layer data may be exported, but an unsupported stack-up must never silently become an inaccurate Palace mesh. The resulting GDS is a review candidate only.

## Supported workflow

Create or open a project, select a parametric QPU prototype, edit libraries/materials/couplers/routes, rebuild and inspect geometry and checks, save a revision, export GDS/QGeometry/nominal circuit, and submit only those FEM tasks for which the geometry engine reports support. Future phases will add full graphical CAD, constrained routing and stronger 3D models.
