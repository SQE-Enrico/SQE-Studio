# Unified physical QPU design model

SQE Studio keeps a shared parametric specification of geometry, materials, layer stack, Josephson junction intent, chip boundaries, qubit cells, physical couplers, CPW routes and RF ports. A single revision can export a GDSII layout, Quantum Metal QGeometry manifest, nominal electrical circuit, and Gmsh/Palace configuration contracts.

## Fidelity boundaries

The same identifiers and model revision link output files, but the nominal capacitances and inductances are **declared assumptions** until a real FEM extraction is available. Layout candidates are marked **HOLD** for fabrication and must not be treated as foundry-qualified masks. Couplers represented as distinct metal nets do not automatically give valid extracted g/χ/ZZ.

## Available prototypes

Reference designs include 1-, 2-, 4-, 9- and 16-cell parametric transmon arrangements, with a limited family of user-extensible rectilinear qubit shapes, capacitive/interdigitated couplers, optional isolated CPW buses, route waypoints/meanders, and Dolan/Manhattan process-intent annotations. A versioned physical schema is stored in the project JSON and associated with immutable revisions and jobs.

## Palace outputs and postprocessing

The configured physical job runner can prepare meshes and Palace electrostatic, eigenmode, linearized JJ, driven-response and convergence-study inputs where the mesher accepts the structure. Per-RF-port excitations are run separately when a full S-matrix is required. Raw artifacts, checksums and logs must be inspected and used to distinguish field-based parameters from nominal model values.

EPR and Kerr postprocessing currently require explicit column mapping and true solver participation data; they do not automatically identify JJ participation in arbitrary field CSV output. Dielectric-loss and Purcell estimates rely on declared assumptions until calibrated by measurements and validated field participation. Numerical convergence does not equal physical validation.

## Further development

General polygonal CAD, physical multimetal stack-up FEM, package-aware 3D modeling, calibrated kinetic inductance, true flux-tunable couplers, mode-overlap tracking, comprehensive DRC/LVS and Hamiltonian extraction remain roadmap milestones.
