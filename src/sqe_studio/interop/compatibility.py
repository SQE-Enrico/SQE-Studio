"""Non-invasive handoff declarations to parallel agents; not adapter ABI changes."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompatibilityDeclaration:
    consumer: str
    input_types: tuple[str, ...]
    output_types: tuple[str, ...]
    required_gate: str
    blocked_without: tuple[str, ...]
    native_engine: str
    status: str = 'declaration_only_no_adapter_integration'


DECLARATIONS = (
    CompatibilityDeclaration(
        'A02', ('CircuitNetlist', 'QGeometryPin', 'PortPinMapping', 'ElementGeometryMapping', 'ArtifactRef', 'EvidenceRecord'),
        ('QDesignHandoff',), 'preflight_design_to_qdesign',
        ('revision-authenticated recipe', 'complete explicit pin/port/element coverage', 'reviewed netlist and geometry mapping'),
        'quantum_metal',
    ),
    CompatibilityDeclaration(
        'A03', ('MeshRegion', 'SolverPort', 'NetworkNormalization', 'ArtifactRef'),
        ('EMMode', 'CapacitanceMatrix', 'NetworkObservation'), 'native_boundary_and_port_review',
        ('native SQDMetal/Gmsh/Palace', 'reviewed material/mesh/boundary/port correspondence', 'real native artifacts'),
        'sqdmetal_palace',
    ),
    CompatibilityDeclaration(
        'A04', ('EMMode', 'CapacitanceMatrix', 'HamiltonianTerm', 'EvidenceRecord'),
        ('QuantumModelHandoff',), 'preflight_em_to_quantum',
        ('reviewed mode/coupling derivation', 'independently supplied Hamiltonian values', 'native scqubits'),
        'scqubits',
    ),
    CompatibilityDeclaration(
        'A05', ('CircuitNetlist', 'CircuitPort', 'SolverPort', 'NetworkNormalization'),
        ('NetworkObservation',), 'native_josephson_netlist_port_review',
        ('explicit signed port orientation', 'verified native Julia netlist mapping', 'JosephsonCircuits.jl runtime'),
        'josephson_circuits',
    ),
    CompatibilityDeclaration(
        'A06', ('RevisionBinding', 'ArtifactRef', 'EvidenceRecord', 'ProvenanceEdge'),
        ('ProvenanceEdge',), 'reviewed_edge',
        ('authenticated revision and checked SHA-256 bytes', 'evidence document identity', 'native artifact manifest'),
        'native_scientific_engines_only',
    ),
)


def compatibility_for(consumer: str) -> CompatibilityDeclaration:
    for declaration in DECLARATIONS:
        if declaration.consumer == consumer:
            return declaration
    raise ValueError('No A01 compatibility declaration for this consumer')
