"""Fail-closed, side-effect-free interoperability handoff preflights.

A passing preflight is NOT native execution, validation of submitted hashes,
scientific correctness, or qualification. The caller must authenticate and
hash-verify the immutable revision, artifacts and signed review records first.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import (
    ArtifactRef, CapacitanceMatrix, CircuitNetlist, EMMode, EvidenceKind,
    EvidenceRecord, ElementGeometryMapping, HamiltonianTerm, PortPinMapping, ProvenanceEdge,
    QGeometryPin, RevisionBinding,
)
from .quantities import InteropValidationError


class InteropBlocked(RuntimeError):
    """Mandatory scientific interoperability conditions were not established."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f'{code}: {detail}')


class MissingEvidence(InteropBlocked):
    def __init__(self, detail: str):
        super().__init__('MISSING_REVIEW_EVIDENCE', detail)


class StaleRevision(InteropBlocked):
    def __init__(self):
        super().__init__('STALE_REVISION', 'Source/destination evidence does not bind to the active immutable revision')


class UnsafeMapping(InteropBlocked):
    def __init__(self, detail: str):
        super().__init__('UNVERIFIED_MAPPING', detail)


@dataclass(frozen=True, slots=True)
class QDesignHandoff:
    netlist_sha256: str
    recipe_sha256: str
    declared_component_ids: tuple[str, ...]
    pins: tuple[QGeometryPin, ...]
    mappings: tuple[PortPinMapping, ...]
    element_mappings: tuple[ElementGeometryMapping, ...]
    evidence: tuple[EvidenceRecord, ...]
    revision: RevisionBinding
    status: str = 'PREFLIGHT_ONLY_NOT_NATIVE_EXECUTION'


@dataclass(frozen=True, slots=True)
class QuantumModelHandoff:
    source_artifacts: tuple[ArtifactRef, ...]
    terms: tuple[HamiltonianTerm, ...]
    evidence: tuple[EvidenceRecord, ...]
    revision: RevisionBinding
    status: str = 'PREFLIGHT_ONLY_NO_INFERRED_HAMILTONIAN'


def require_active_revision(active: RevisionBinding, *items: ArtifactRef | EvidenceRecord) -> None:
    if not isinstance(active, RevisionBinding) or any(
        not isinstance(item, (ArtifactRef, EvidenceRecord)) or item.revision != active for item in items
    ):
        raise StaleRevision()


def _review_bundle(
    evidence: tuple[EvidenceRecord, ...],
    required: set[EvidenceKind],
    parents: tuple[ArtifactRef, ...],
    active: RevisionBinding,
) -> None:
    if not isinstance(evidence, tuple) or any(not isinstance(e, EvidenceRecord) for e in evidence):
        raise MissingEvidence('Reviewed, document-hashed evidence records must be explicit')
    require_active_revision(active, *evidence)
    parent_hashes = {p.sha256 for p in parents}
    for item in evidence:
        if not set(item.source_artifact_sha256) <= parent_hashes:
            raise UnsafeMapping(f'Evidence {item.evidence_id} references a non-parent artifact')
    kinds = {e.kind for e in evidence}
    missing = sorted(k.value for k in required - kinds)
    if missing:
        raise MissingEvidence('Required reviewed declarations missing: '+', '.join(missing))
    for kind in required:
        # Every mandatory review must explicitly bind to at least one parent.
        if not any(e.kind == kind and e.source_artifact_sha256 for e in evidence):
            raise MissingEvidence('Unbound evidence of kind '+kind.value)


def preflight_design_to_qdesign(
    *, netlist: CircuitNetlist, recipe: ArtifactRef,
    declared_component_ids: tuple[str, ...], declared_pins: tuple[QGeometryPin, ...],
    port_mappings: tuple[PortPinMapping, ...], element_mappings: tuple[ElementGeometryMapping, ...],
    evidence: tuple[EvidenceRecord, ...], active_revision: RevisionBinding,
) -> QDesignHandoff:
    """Review *declared* pin geometry and circuit connectivity before A02 builds QDesign.

    No pin extraction, placement, ground, junction or wire routing is inferred.
    These declarations are inputs, not claims about a successfully built QDesign.
    """
    if not isinstance(netlist, CircuitNetlist) or not isinstance(recipe, ArtifactRef):
        raise UnsafeMapping('Typed netlist and Quantum Metal recipe are both required')
    if recipe.artifact_type != 'quantum_metal.qdesign_recipe':
        raise UnsafeMapping('Recipe artifact type must be quantum_metal.qdesign_recipe')
    require_active_revision(active_revision, netlist.source, recipe)
    if (not isinstance(declared_component_ids, tuple) or not declared_component_ids or
            any(not isinstance(c, str) or not c or len(c) > 48 for c in declared_component_ids) or
            len(set(declared_component_ids)) != len(declared_component_ids)):
        raise UnsafeMapping('Explicit unique declarative QComponent IDs required')
    if not isinstance(declared_pins, tuple) or not declared_pins or any(not isinstance(p, QGeometryPin) for p in declared_pins):
        raise UnsafeMapping('Explicit reviewed geometry pin declarations required')
    if any(p.component_id not in declared_component_ids for p in declared_pins):
        raise UnsafeMapping('Pin references a component absent from the reviewed recipe declaration')
    if not isinstance(port_mappings, tuple) or not port_mappings or any(not isinstance(p, PortPinMapping) for p in port_mappings):
        raise UnsafeMapping('Explicit one-to-one circuit-port/QGeometry pin declarations required')
    pins = tuple(p.pin_id for p in declared_pins)
    if len(pins) != len(set(pins)):
        raise UnsafeMapping('Duplicate geometry pin identity')
    netlist_ports = {p.index for p in netlist.ports}
    mapped_ports = [p.circuit_port for p in port_mappings]
    if len(mapped_ports) != len(set(mapped_ports)) or set(mapped_ports) != netlist_ports:
        raise UnsafeMapping('Every netlist port needs exactly one reviewed signal/return mapping')
    used_pins = [pin for m in port_mappings for pin in (m.signal_pin_id, m.return_pin_id)]
    if len(used_pins) != len(set(used_pins)) or set(used_pins) != set(pins):
        raise UnsafeMapping('Pin mapping must cover all declared pins exactly once; no hidden grounds')
    if (not isinstance(element_mappings, tuple) or
            any(not isinstance(m, ElementGeometryMapping) for m in element_mappings)):
        raise UnsafeMapping('Explicit element-to-geometry declarations are required')
    elements = {e.element_id: e for e in netlist.elements}
    if len(element_mappings) != len(elements) or {m.element_id for m in element_mappings} != set(elements):
        raise UnsafeMapping('Every circuit element must be mapped to a declared geometry identity')
    if len({m.geometry_id for m in element_mappings}) != len(element_mappings):
        raise UnsafeMapping('Geometry element identity cannot be reused without a reviewed model')
    for mapping in element_mappings:
        element = elements[mapping.element_id]
        if mapping.component_id not in declared_component_ids or (mapping.positive_node, mapping.negative_node, mapping.represented_kind) != (element.positive_node, element.negative_node, element.kind):
            raise UnsafeMapping('Element/geometry identity, kind or signed terminals do not match the netlist')
    _review_bundle(evidence, {EvidenceKind.NETLIST_REVIEW, EvidenceKind.GEOMETRY_REVIEW, EvidenceKind.PORT_CORRESPONDENCE}, (netlist.source, recipe), active_revision)
    # Ensure the geometry and mapping reviews actually include the recipe artifact,
    # and the netlist review includes the netlist artifact.
    for kind, parent in ((EvidenceKind.NETLIST_REVIEW, netlist.source.sha256),
                         (EvidenceKind.GEOMETRY_REVIEW, recipe.sha256),
                         (EvidenceKind.PORT_CORRESPONDENCE, recipe.sha256)):
        if not any(e.kind == kind and parent in e.source_artifact_sha256 for e in evidence):
            raise MissingEvidence(f'{kind.value} must cite its exact input artifact')
    return QDesignHandoff(netlist.source.sha256, recipe.sha256, declared_component_ids,
                          declared_pins, port_mappings, element_mappings, evidence, active_revision)


def preflight_em_to_quantum(
    *, modes: tuple[EMMode, ...], capacitance: CapacitanceMatrix | None,
    reviewed_terms: tuple[HamiltonianTerm, ...], evidence: tuple[EvidenceRecord, ...],
    active_revision: RevisionBinding,
) -> QuantumModelHandoff:
    """Gate A04 quantization without deriving any parameter from EM observables.

    Term values must have been produced and separately reviewed outside SQE.
    In particular, an eigenfrequency is never silently turned into EJ/EC/g.
    """
    if not isinstance(modes, tuple) or any(not isinstance(m, EMMode) for m in modes):
        raise UnsafeMapping('EM modes must be typed native observations')
    if capacitance is not None and not isinstance(capacitance, CapacitanceMatrix):
        raise UnsafeMapping('Capacitance must be typed native observation')
    if not modes and capacitance is None:
        raise MissingEvidence('No native EM observable supplied')
    if not isinstance(reviewed_terms, tuple) or not reviewed_terms or any(not isinstance(t, HamiltonianTerm) for t in reviewed_terms):
        raise MissingEvidence('No separately derived and reviewed Hamiltonian parameter values; raw EM frequency is insufficient')
    sources = tuple(dict((a.artifact_id, a) for a in ([m.source for m in modes] + ([capacitance.source] if capacitance else []))).values())
    require_active_revision(active_revision, *sources)
    if len({m.index for m in modes}) != len(modes):
        raise UnsafeMapping('Mode indices are not unique')
    source_hashes = {a.sha256 for a in sources}
    for term in reviewed_terms:
        if not set(term.source_artifact_sha256) <= source_hashes:
            raise UnsafeMapping('Hamiltonian term references unrelated EM artifacts')
    if set().union(*(set(t.source_artifact_sha256) for t in reviewed_terms)) != source_hashes:
        raise UnsafeMapping('Every supplied EM observable must have an explicit reviewed term relationship')
    if len(set((t.model, t.parameter) for t in reviewed_terms)) != len(reviewed_terms):
        raise UnsafeMapping('Duplicate model/parameter terms')
    _review_bundle(evidence, {EvidenceKind.MODE_IDENTIFICATION, EvidenceKind.QUANTIZATION_DERIVATION,
                              EvidenceKind.COUPLING_REVIEW, EvidenceKind.EXTRACTION_VALIDATION}, sources, active_revision)
    # Quantization and coupling reviews must actually cite every EM parent of each
    # handed-off term; a token review of an unrelated mode is not enough.
    for term in reviewed_terms:
        parents = set(term.source_artifact_sha256)
        for kind in (EvidenceKind.QUANTIZATION_DERIVATION, EvidenceKind.COUPLING_REVIEW,
                     EvidenceKind.EXTRACTION_VALIDATION):
            if not any(e.kind == kind and parents <= set(e.source_artifact_sha256) for e in evidence):
                raise MissingEvidence(f'{kind.value} does not cover {term.model}.{term.parameter} parents')
    return QuantumModelHandoff(sources, reviewed_terms, evidence, active_revision)


def reviewed_edge(*, parents: tuple[ArtifactRef, ...], target: ArtifactRef,
                  evidence: tuple[EvidenceRecord, ...], active_revision: RevisionBinding,
                  operation: str = 'reviewed_mapping') -> ProvenanceEdge:
    """Create a checked edge; caller must externally verify artifact/evidence hashes."""
    require_active_revision(active_revision, *parents, target)
    if not evidence:
        raise MissingEvidence('A derived edge requires explicitly reviewed evidence')
    try:
        return ProvenanceEdge(parents, target, operation, evidence)
    except InteropValidationError as exc:
        raise UnsafeMapping(str(exc)) from exc
