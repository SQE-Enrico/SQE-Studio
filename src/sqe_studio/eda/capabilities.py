"""Auditable EDA integration map, not a substitute execution DAG.

An edge is usable only if a native adapter and all relevant evidence gates exist.
This is a product capability declaration: A01 interoperability types and A06
revision-bound execution remain authoritative for scientific data and jobs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

CapabilityStatus = Literal['native_conditional', 'verified_inspection', 'blocked']


@dataclass(frozen=True)
class EdaEdge:
    id: str
    source: str
    destination: str
    status: CapabilityStatus
    provider: str
    prerequisite: str
    scientific_gate: str


_EDGES = (
    EdaEdge('layout_to_qdesign', 'sqe.project.v1.layout', 'Quantum Metal QDesign',
            'native_conditional', 'quantum_metal_adapter', 'Installed Quantum Metal, valid QComponent recipe',
            'Review native QGeometry and object/port identities; canvas is symbolic'),
    EdaEdge('qdesign_to_em', 'Quantum Metal QDesign', 'Gmsh mesh / Palace deck',
            'native_conditional', 'sqdmetal_palace_adapter', 'SQDMetal, Gmsh and Palace toolchain',
            'Review layer/ground/port/mesh/BC mappings and solver release'),
    EdaEdge('em_to_results', 'Palace native files', 'Verified EM result view',
            'verified_inspection', 'native_views + artifacts', 'Completed revision-bound native artifact',
            'Check hashes, units, matching and mesh convergence before numerical conclusions'),
    EdaEdge('independent_to_scqubits', 'Independent explicit Hamiltonian input', 'scqubits native spectrum',
            'native_conditional', 'scqubits_adapter', 'Installed scqubits 4.x and explicit model parameters',
            'Source must stay independent; check energy units and basis convergence'),
    EdaEdge('em_to_hamiltonian', 'Native EM + EPR tables', 'Verified Josephson Hamiltonian input',
            'blocked', 'not_implemented', 'Versioned EPR lineage and junction/mode identity',
            'Require junction energy participation, units, normalization, uncertainty and approval'),
    EdaEdge('sheet_to_palace', 'Reviewed film properties / Gmsh surfaces', 'Native sheet-impedance EM model',
            'blocked', 'not_implemented', 'Revision-bound reviewed Palace sheet boundary adapter',
            'Require film regime, physical surface ID, Ls provenance and matched PEC control'),
    EdaEdge('schematic_to_julia', 'Reviewed schematic and RF ports', 'JosephsonCircuits.jl native RF results',
            'blocked', 'josephson_adapter', 'Qualified Julia runtime/netlist and port correspondence',
            'Require solver/native comparison, operating point, harmonics and reference planes'),
    EdaEdge('cad_to_fab', 'Verified QDesign / GDS', 'Fabrication-ready export',
            'blocked', 'not_implemented', 'Approved foundry PDK and DRC/LVS',
            'Always fabrication HOLD without independent signoff'),
)


def list_capabilities() -> list[dict]:
    """Defensive copies suitable for a read-only authenticated GUI endpoint."""
    return [asdict(edge) for edge in _EDGES]
