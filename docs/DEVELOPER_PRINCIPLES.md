# SQE Studio Engineering Principles — normative for future contributors

**Applies to:** every new UI feature, adapter, model, scientific transformation, test, example and release. **Direction:** an integrated electronic-design-automation (EDA) application for superconducting, microwave and quantum circuits. A QPU is an application family, not the product boundary. This document supersedes exploratory CLI and experiment-log framing.

## Product contract

1. **Design is the center.** A user defines engineering targets and constraints, constructs a schematic and physical layout, runs appropriate native simulations, sees comparable results with limitations, and iterates the design. No "experiment registry" as the primary product, no detached demo app, no per-example workflow, and no CLI required for a normal designer.
2. **A single UI and model.** Guided and Expert modes operate on the *same* canonical project, revision and backend. All published cases enter through **New project** and follow the general specifications → schematic → layout → EM → circuit/quantum → results → revision loop. Not every case needs every step; the workflow must accommodate passive RF and nonlinear devices as well as qubits.
3. **Native authority.** Quantum Metal is responsible for QDesign/GDS, SQDMetal/Gmsh/Palace for mesh/EM, scqubits for supported Hamiltonian calculations, JosephsonCircuits.jl for its validated nonlinear/RF circuit analyses. SQE composes these engines; it does not silently replace them with approximate native-looking results.
4. **Typed scientific interoperability.** Every cross-engine edge specifies physical quantity, SI or explicit frequency-energy unit conventions, reference plane, coordinate frame, materials, mode/junction/port identity, assumptions, uncertainty, source revision and artifact content hashes. A mathematical formula is insufficient proof of the correct physical mapping.
5. **Fail closed.** Lack of native engines, convergence, geometry/port mapping, EPR normalization or material review is displayed as an unmet gate. No placeholder measurements, fabricated GDS, hidden defaults, unvalidated lineages or "green" statuses for merely configured studies. An imported result has to pass the same checks as a locally computed one.
6. **Optimization acts on a real design.** Future objective functions and constraints operate on explicit design parameters and verified observables. Every candidate is a saved design revision with replayable solver settings; optimizer failures and nonconvergence are visible, not silently interpolated. No synthetic optimizer scoring presented as science.
7. **Scientific comparisons are conditional.** Never compare unrelated mode ordinals or ports as physical identities. EPR-derived and independently entered Hamiltonian parameters have different lineage; show disagreement and the prerequisites for comparison. Record basis/mesh convergence, solver versions and uncertainty, without promoting a "pass" to experimental proof.
8. **Device-neutral platform.** A CPW resonator, fluxonium, readout network, matching circuit, JPA and multi-qubit chip use the same project, parameter, solver, artifact and visualization services. Device-specific plugins supply typed domain recipes, not special controller routes.
9. **Safe local desktop first.** A bounded laptop workflow, authenticated loopback service, CSRF, ACL, immutable revisions and hashed results are required. No untrusted Python imports, arbitrary Julia code, external solver command templates or unsafe artifact paths from project JSON. User-facing controls must be keyboard-accessible and must state when the visualization is symbolic.
10. **Fabrication is another gated output.** GDS is not a fabrication authorization. PDK, process/material models, DRC, LVS, layer mapping, mask review and independent foundry approval remain HOLD until supported by evidence.

## Change acceptance checklist (blocking)

- The change fits the **existing generic workflow**; no new solver, demo or special route created merely for a use case.
- Data are expressed in documented, versioned schemas; frozen JSON/contracts and agent protocol remain unchanged absent an approved migration. Additive *read-only catalog metadata* is not a migration of `sqe.project.v1`.
- An engine bridge has explicit input/output types, unit checks, solver version, identity mapping, upstream revision hash, native regression and fail-closed tests.
- Results distinguish inputs, estimates, fixtures, native solutions, published reference data, measurements and independently qualified comparisons.
- Quality gates exist for security, determinism, native result provenance, scientific convergence and UI flows; unit tests alone cannot qualify a scientific release.
- The feature is documented once at its current location; obsolete documents and duplicate starter mechanisms are removed or explicitly deprecated. Never delete audit evidence or foundation locks as "cleanup."

## Explicitly forbidden shortcuts

- `f01` computed from arbitrary Palace eigenmode number; automatic EPR → EJ/EC without checked junction and mode lineage.
- A "kinetic inductance enabled" UI switch that only changes a label or an unreviewed material constant.
- An optimizer that optimizes mock output, unchecked solver logs, or unrelated simulation revisions.
- Lossy conversion of complex S-parameters into magnitudes without keeping phase, frequency unit, port order and reference impedance.
- Copying a paper's figures or numbers and claiming this build has reproduced them.

## Required handoff for the next developer

Read, in order: this document → [architecture and extension points](EDA_EXTENSION_ARCHITECTURE.md) → [scientific use cases](SCIENTIFIC_DESIGN_CASES.md) → [quality gates](QUALITY_GATES.md) → `contracts/`, `src/sqe_studio/interop/`, `src/sqe_studio/eda/`, `agents/` and `docs/AGENT_PROTOCOL.md` when working with historical source ownership. Contributors must identify which *currently blocked edge* their change enables and supply native evidence before marking it enabled.

## Workstation qualification and RC evidence

All contributors must maintain the shared, user-invoked desktop qualification pathway described in [LAPTOP_QUALIFICATION.md](LAPTOP_QUALIFICATION.md). Never add privileged test execution to the local HTTP API, use production design files in automatic QA, or label missing dependencies as PASS. When a new native adapter or a typed EDA edge is introduced, add a genuine native acceptance gate and a machine-readable report entry; fixtures remain separate. A GUI EDA release candidate requires verified installed-package, browser, physical interoperability and independent scientific evidence, not merely a clean software suite.
