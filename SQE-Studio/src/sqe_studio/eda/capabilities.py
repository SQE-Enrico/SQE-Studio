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
    EdaEdge('capacitance_to_conditional_transmon', 'Verified saved Palace capacitance and conductor selection',
            'Conditional single-mode scqubits research spectrum', 'native_conditional',
            'A11/A12 existing reduction + native scqubits Transmon',
            'Same-owner source run, unchanged physical context, declared additional C_J and E_J/h or L_J, scqubits 4.3.1',
            'Executable conditional model only: preserve source SHA/revision and assumptions; geometry registration, EM convergence, EPR and physical qualification remain unestablished'),
    EdaEdge('sheet_to_palace', 'Reviewed film properties / Gmsh surfaces', 'Native sheet-impedance EM model',
            'blocked', 'not_implemented', 'Revision-bound reviewed Palace sheet boundary adapter',
            'Require film regime, physical surface ID, Ls provenance and matched PEC control'),
    EdaEdge('schematic_to_julia', 'Reviewed schematic and RF ports', 'JosephsonCircuits.jl native RF results',
            'blocked', 'josephson_adapter', 'Qualified Julia runtime/netlist and port correspondence',
            'Require solver/native comparison, operating point, harmonics and reference planes'),
    EdaEdge('geometry_revision_to_native_em', 'Saved geometry candidate revision', 'Fresh native EM job',
            'native_conditional', 'orchestration.optimization',
            'Reviewed process, saved native Palace EM solve, immutable project head and bounded geometry dimensions',
            'Maximum 3 fresh 900 s solves across one SHA-linked, review-bound iteration lineage (2700 s total); require each new revision, fresh native submission and expert review'),
    EdaEdge('native_em_to_exploratory_iteration_plan', 'Hash-verified native candidate run',
            'Revision-bound next geometry proposal', 'native_conditional', 'orchestration.optimization',
            'Completed fresh Palace run, immutable Store/review/solver-snapshot chain and native artifact SHA verification; remaining three-solve budget and new operator review',
            'Indexed eigenfrequencies are unassigned observations only; goal feasibility, mode identity, cross-engine transfer and automatic ranking stay blocked'),
    EdaEdge('saved_revision_to_cad_parameter_compare', 'Reviewed immutable Store CAD revision',
            'Unit-exact CAD target/constraint and revision diff', 'verified_inspection',
            'orchestration.optimization.inspect_saved_geometry_candidate',
            'Owner-scoped Store revision, source/project digest, reviewed candidate and bounded native lineage',
            'Only literal named dimensions can be compared; no native solver timing, mode/EPR/scientific ranking or fabrication approval'),
    EdaEdge('native_revisions_to_b10_mode_review', 'Two fresh SHA-bound Palace eigenmode revisions',
            'Mesh-locked B10 candidate inspection', 'verified_inspection',
            'orchestration.optimization.inspect_b10_revision_pair',
            'Two separate reviewed revisions, completed native runs, fingerprinted artifact manifests and exact Gmsh mesh member hashes',
            'Verifies source/target mesh and solver lineage; B10 physical objectives remain BLOCKED without independent normalized complex-field registration, expert mode identity and acceptance'),
    EdaEdge('native_em_to_geometry_objectives', 'Verified revision-bound native EM observables',
            'Numerically ranked design candidates', 'blocked', 'not_implemented',
            'Verified physical mode overlap or port identity and reference-plane mappings for every candidate',
            'No automatic numerical score, optimizer ranking, scientific qualification or fabrication approval'),
    EdaEdge('cad_to_fab', 'Verified QDesign / GDS', 'Fabrication-ready export',
            'blocked', 'not_implemented', 'Approved foundry PDK and DRC/LVS',
            'Always fabrication HOLD without independent signoff'),
)


def list_capabilities() -> list[dict]:
    """Defensive copies suitable for a read-only authenticated GUI endpoint."""
    return [asdict(edge) for edge in _EDGES]
