# Quantum Metal geometry interchange

SQE Studio supports an optional, isolated integration with the open-source Quantum Metal/Qiskit Metal ecosystem. The core Web application does not require Quantum Metal to start.

## What works

Parameterized physical components have stable IDs, nets, materials, ports and layout layers. The available exporter generates a QGeometry-compatible manifest of named positive-metal shapes and the GDSII representation where supported. `scripts/quantum_metal_bridge.py` can consume the interchange from a dedicated Quantum Metal Python environment. Use the optional `WINDOWS-QUANTUM-METAL-SETUP.cmd` only when this environment is needed.

## What is not proved

Interchange of named polygons is not equivalent to validated QComponent routing, net continuity, production DRC or faithful 3D Palace meshing. Custom qubit/coupler geometry is currently limited by the project schema and underlying rectangular primitives; arbitrary polygon/editing support is a future CAD milestone. The true circuit values remain nominal until extraction from electromagnetic simulation.

## Future adapter contract

Preserve unit conversion, net names, layer and component IDs, junction orientations, positive/negative polygons, ports and mesh-boundary assignments. Add round-trip equivalence tests before claiming a bidirectional interchange, and ensure external toolkit versions remain pinned and optional.

## Update 0.15.0

The generic `sqw ecosystem` workflow accepts either the existing positive-
metal QGeometry manifest or a trusted Python `build_design()` factory that
creates a real Quantum Metal QDesign, and can hand that QDesign to SQDMetal's
public Palace preparation APIs; see [the multi-engine guide](ecosystem-workflow.md).
No automatic positive-mask-to-qualified-Palace geometry equivalence is claimed.
