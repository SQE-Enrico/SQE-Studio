"""A01 typed inter-engine metadata and fail-closed preflight API (v1).

This module does not authenticate reviews, read native results, run engines,
render GDS, infer Hamiltonians or change the frozen adapter ABI. Import only
explicitly documented typed classes; no arbitrary dynamic import paths.
"""
from .quantities import ComplexQuantity, Dimension, InteropValidationError, Quantity
from .models import (
    ArtifactRef, CapacitanceMatrix, CircuitElement, CircuitNetlist, CircuitPort,
    EMMode, ElementGeometryMapping, ElementKind, EvidenceKind, EvidenceRecord, HamiltonianTerm,
    MeshRegion, NetworkKind, NetworkNormalization, NetworkObservation,
    NetworkSample, Point2D, PortPinMapping, ProvenanceEdge, QGeometryPin,
    RevisionBinding, SolverPort, canonical_json, content_digest,
)
from .preflight import (
    InteropBlocked, MissingEvidence, QDesignHandoff, QuantumModelHandoff,
    StaleRevision, UnsafeMapping, preflight_design_to_qdesign,
    preflight_em_to_quantum, require_active_revision, reviewed_edge,
)
from .transformations import (
    capacitance_as, convert_network_frequency_units, frequency_as,
    reorder_network_ports,
)
from .compatibility import CompatibilityDeclaration, DECLARATIONS, compatibility_for

INTEROP_SCHEMA = 'sqe.interop.a01.v1'
