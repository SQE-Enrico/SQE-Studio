"""Immutable, strict typed evidence edges; no scientific solvers or geometrical inference."""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import Enum
import hashlib
import json
import re
from typing import Any
from uuid import UUID

from .quantities import ComplexQuantity, Dimension, InteropValidationError, Quantity

_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,47}$')
_HEX = re.compile(r'^[0-9a-f]{64}$')
_ALLOWED_ARTIFACTS = frozenset({
    'circuit.netlist', 'quantum_metal.qdesign_recipe', 'quantum_metal.gdsii',
    'gmsh.mesh', 'palace.deck', 'palace.eigenmodes', 'palace.sparameters',
    'palace.capacitance_matrix', 'scqubits.spectrum', 'josephson.sparameters',
    'validation.report', 'measurement.dataset',
})
_ALLOWED_ENGINES = frozenset({'quantum_metal', 'sqdmetal_palace', 'scqubits', 'josephson_circuits'})


def _identifier(value: str, description: str = 'identifier') -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise InteropValidationError(f'Invalid {description}: requires identifier of length <=48')


def _digest(value: str) -> None:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise InteropValidationError('SHA-256 must be 64 lowercase hexadecimal characters')


def _uuid(value: str) -> None:
    if not isinstance(value, str):
        raise InteropValidationError('Revision and project IDs must be UUID strings')
    try:
        parsed = UUID(value)
    except ValueError:
        raise InteropValidationError('Revision and project IDs must be UUID strings') from None
    if str(parsed) != value or parsed.version is None:
        raise InteropValidationError('UUID must use canonical lowercase representation')


def _nonempty_tuple(values: tuple[Any, ...], label: str) -> None:
    if not isinstance(values, tuple) or not values:
        raise InteropValidationError(f'{label} requires nonempty tuple')


def _unique(values: tuple[Any, ...], label: str) -> None:
    if len(set(values)) != len(values):
        raise InteropValidationError(f'Duplicate {label}')


def _positive_port(value: int) -> None:
    if type(value) is not int or value < 1:
        raise InteropValidationError('Port and mode indices are positive, one-based integers')


def _port_sequence(indices: tuple[int, ...]) -> None:
    _nonempty_tuple(indices, 'port indices')
    if tuple(sorted(indices)) != tuple(range(1, len(indices) + 1)):
        raise InteropValidationError('Ports must be unique, contiguous and numbered from 1')


def _portable(obj: Any) -> Any:
    if isinstance(obj, Quantity):
        return obj.portable()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return {f.name: _portable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, (tuple, list)):
        return [_portable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _portable(v) for k, v in sorted(obj.items())}
    if type(obj) in (str, int, bool) or obj is None:
        return obj
    raise InteropValidationError('Unsupported portable interop value')


def canonical_json(obj: Any) -> str:
    return json.dumps(_portable(obj), sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def content_digest(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class RevisionBinding:
    project_id: str
    revision_id: str
    revision_sha256: str

    def __post_init__(self) -> None:
        _uuid(self.project_id)
        _uuid(self.revision_id)
        _digest(self.revision_sha256)


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    artifact_type: str
    sha256: str
    revision: RevisionBinding
    engine: str
    engine_version: str
    schema_version: str = 'sqe.artifact.v1'

    def __post_init__(self) -> None:
        if self.schema_version != 'sqe.artifact.v1':
            raise InteropValidationError('Unsupported artifact schema version')
        _identifier(self.artifact_id, 'artifact id')
        if self.artifact_type not in _ALLOWED_ARTIFACTS:
            raise InteropValidationError('Unregistered artifact type; request frozen-contract migration')
        _digest(self.sha256)
        if not isinstance(self.revision, RevisionBinding):
            raise InteropValidationError('Artifact requires immutable revision binding')
        if self.engine not in _ALLOWED_ENGINES and self.engine != 'external':
            raise InteropValidationError('Unrecognized producing engine')
        if not isinstance(self.engine_version, str) or not self.engine_version.strip() or len(self.engine_version) > 100:
            raise InteropValidationError('Native producer/version is required')


class EvidenceKind(str, Enum):
    NETLIST_REVIEW = 'netlist_review'
    GEOMETRY_REVIEW = 'geometry_review'
    PORT_CORRESPONDENCE = 'port_correspondence'
    MATERIAL_AND_BOUNDARY_REVIEW = 'material_and_boundary_review'
    MODE_IDENTIFICATION = 'mode_identification'
    QUANTIZATION_DERIVATION = 'quantization_derivation'
    COUPLING_REVIEW = 'coupling_review'
    EXTRACTION_VALIDATION = 'extraction_validation'


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    kind: EvidenceKind
    document_sha256: str
    reviewer: str
    revision: RevisionBinding
    source_artifact_sha256: tuple[str, ...]
    schema_version: str = 'sqe.evidence-record.a01.v1'

    def __post_init__(self) -> None:
        if self.schema_version != 'sqe.evidence-record.a01.v1':
            raise InteropValidationError('Unsupported evidence record schema version')
        _identifier(self.evidence_id, 'evidence id')
        if not isinstance(self.kind, EvidenceKind):
            raise InteropValidationError('Evidence kind must be allowlisted')
        _digest(self.document_sha256)
        _identifier(self.reviewer, 'reviewer identity')
        if not isinstance(self.revision, RevisionBinding):
            raise InteropValidationError('Evidence needs revision binding')
        _nonempty_tuple(self.source_artifact_sha256, 'evidence source digests')
        for digest in self.source_artifact_sha256:
            _digest(digest)
        _unique(self.source_artifact_sha256, 'evidence source digests')


@dataclass(frozen=True, slots=True)
class ProvenanceEdge:
    source: tuple[ArtifactRef, ...]
    target: ArtifactRef
    operation: str
    evidence: tuple[EvidenceRecord, ...]
    schema_version: str = 'sqe.evidence-edge.a01.v1'

    def __post_init__(self) -> None:
        if self.schema_version != 'sqe.evidence-edge.a01.v1':
            raise InteropValidationError('Unsupported evidence edge schema version')
        _nonempty_tuple(self.source, 'edge source artifacts')
        _nonempty_tuple(self.evidence, 'edge evidence')
        _identifier(self.operation, 'operation')
        if not isinstance(self.target, ArtifactRef) or any(not isinstance(a, ArtifactRef) for a in self.source):
            raise InteropValidationError('Edge source/target must be artifacts')
        if any(a.revision != self.target.revision for a in self.source):
            raise InteropValidationError('Provenance crossing immutable revisions is blocked')
        _unique(tuple(a.artifact_id for a in self.source), 'edge source artifacts')
        if self.target.artifact_id in {a.artifact_id for a in self.source}:
            raise InteropValidationError('Provenance self-derivation is blocked')
        source_hashes = {a.sha256 for a in self.source}
        for e in self.evidence:
            if not isinstance(e, EvidenceRecord) or e.revision != self.target.revision or not set(e.source_artifact_sha256) <= source_hashes:
                raise InteropValidationError('Evidence lineage does not match source artifacts and revision')
        _unique(tuple(e.evidence_id for e in self.evidence), 'edge evidence IDs')
        if set().union(*(set(e.source_artifact_sha256) for e in self.evidence)) != source_hashes:
            raise InteropValidationError('Every provenance parent must be cited by review evidence')


class ElementKind(str, Enum):
    CAPACITOR = 'capacitor'
    INDUCTOR = 'inductor'
    RESISTOR = 'resistor'
    JOSEPHSON_JUNCTION = 'josephson_junction'
    WIRE = 'wire'


_ELEMENT_DIM = {
    ElementKind.CAPACITOR: Dimension.CAPACITANCE,
    ElementKind.INDUCTOR: Dimension.INDUCTANCE,
    ElementKind.RESISTOR: Dimension.RESISTANCE,
    ElementKind.JOSEPHSON_JUNCTION: Dimension.ENERGY_OVER_H,
}


@dataclass(frozen=True, slots=True)
class CircuitElement:
    element_id: str
    kind: ElementKind
    positive_node: str
    negative_node: str
    value: Quantity | None

    def __post_init__(self) -> None:
        _identifier(self.element_id, 'element id')
        _identifier(self.positive_node, 'positive node')
        _identifier(self.negative_node, 'negative node')
        if self.positive_node == self.negative_node:
            raise InteropValidationError('Element terminals must be different nodes')
        if not isinstance(self.kind, ElementKind):
            raise InteropValidationError('Unsupported circuit element kind')
        if self.kind == ElementKind.WIRE:
            if self.value is not None:
                raise InteropValidationError('Wire must not contain a guessed physical value')
        elif not isinstance(self.value, Quantity):
            raise InteropValidationError('Element requires explicitly unit-aware value')
        else:
            self.value.require(_ELEMENT_DIM[self.kind], strictly_positive=True)


@dataclass(frozen=True, slots=True)
class CircuitPort:
    index: int
    signal_node: str
    return_node: str

    def __post_init__(self) -> None:
        _positive_port(self.index)
        _identifier(self.signal_node, 'signal node')
        _identifier(self.return_node, 'return node')
        if self.signal_node == self.return_node:
            raise InteropValidationError('Signal and return nodes must differ; no implicit ground')


@dataclass(frozen=True, slots=True)
class CircuitNetlist:
    nodes: tuple[str, ...]
    elements: tuple[CircuitElement, ...]
    ports: tuple[CircuitPort, ...]
    source: ArtifactRef

    def __post_init__(self) -> None:
        _nonempty_tuple(self.nodes, 'netlist nodes')
        for n in self.nodes:
            _identifier(n, 'node')
        _unique(self.nodes, 'nodes')
        _nonempty_tuple(self.elements, 'netlist elements')
        _nonempty_tuple(self.ports, 'netlist ports')
        if any(not isinstance(e, CircuitElement) for e in self.elements) or any(not isinstance(p, CircuitPort) for p in self.ports):
            raise InteropValidationError('Netlist elements and ports must be strictly typed')
        if not isinstance(self.source, ArtifactRef) or self.source.artifact_type != 'circuit.netlist':
            raise InteropValidationError('Verified netlist source artifact required')
        _unique(tuple(e.element_id for e in self.elements), 'element IDs')
        _port_sequence(tuple(p.index for p in self.ports))
        nodes = set(self.nodes)
        if any(e.positive_node not in nodes or e.negative_node not in nodes for e in self.elements):
            raise InteropValidationError('Unknown netlist element terminal node')
        if any(p.signal_node not in nodes or p.return_node not in nodes for p in self.ports):
            raise InteropValidationError('Unknown netlist port node')


@dataclass(frozen=True, slots=True)
class Point2D:
    x: Quantity
    y: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.x, Quantity) or not isinstance(self.y, Quantity):
            raise InteropValidationError('Point coordinates must be explicit length quantities')
        self.x.require(Dimension.LENGTH)
        self.y.require(Dimension.LENGTH)


@dataclass(frozen=True, slots=True)
class QGeometryPin:
    pin_id: str
    component_id: str
    pin_name: str
    start: Point2D
    end: Point2D
    width: Quantity

    def __post_init__(self) -> None:
        for value in (self.pin_id, self.component_id, self.pin_name):
            _identifier(value, 'QGeometry pin identity')
        if not isinstance(self.start, Point2D) or not isinstance(self.end, Point2D):
            raise InteropValidationError('Explicit QGeometry endpoints required')
        if not isinstance(self.width, Quantity):
            raise InteropValidationError('Pin width must be a length quantity')
        self.width.require(Dimension.LENGTH, strictly_positive=True)
        if self.start == self.end:
            raise InteropValidationError('Degenerate QGeometry pin')


@dataclass(frozen=True, slots=True)
class PortPinMapping:
    circuit_port: int
    signal_pin_id: str
    return_pin_id: str

    def __post_init__(self) -> None:
        _positive_port(self.circuit_port)
        _identifier(self.signal_pin_id, 'signal pin')
        _identifier(self.return_pin_id, 'return pin')
        if self.signal_pin_id == self.return_pin_id:
            raise InteropValidationError('Explicit separate signal/return pins required')


@dataclass(frozen=True, slots=True)
class ElementGeometryMapping:
    """Reviewed intent-only equivalence; does not assert native QDesign construction."""
    element_id: str
    component_id: str
    geometry_id: str
    positive_node: str
    negative_node: str
    represented_kind: ElementKind

    def __post_init__(self) -> None:
        for value in (self.element_id, self.component_id, self.geometry_id,
                      self.positive_node, self.negative_node):
            _identifier(value, 'element geometry mapping')
        if not isinstance(self.represented_kind, ElementKind):
            raise InteropValidationError('Element geometry role must be explicitly declared')
        if self.positive_node == self.negative_node:
            raise InteropValidationError('Element geometry terminal polarity is ambiguous')


@dataclass(frozen=True, slots=True)
class MeshRegion:
    region_id: str
    physical_group: int
    material_id: str
    role: str
    source: ArtifactRef

    def __post_init__(self) -> None:
        _identifier(self.region_id, 'mesh region')
        _identifier(self.material_id, 'material')
        if type(self.physical_group) is not int or self.physical_group <= 0:
            raise InteropValidationError('Mesh physical group must be a positive integer')
        if self.role not in ('dielectric', 'conductor', 'vacuum', 'boundary', 'junction'):
            raise InteropValidationError('Explicit known mesh region role required')
        if not isinstance(self.source, ArtifactRef) or self.source.artifact_type != 'gmsh.mesh':
            raise InteropValidationError('Mesh region must originate in a hashed Gmsh artifact')


@dataclass(frozen=True, slots=True)
class SolverPort:
    index: int
    signal_boundary: int
    return_boundary: int
    circuit_port: int
    reference_impedance: Quantity

    def __post_init__(self) -> None:
        _positive_port(self.index)
        _positive_port(self.circuit_port)
        if type(self.signal_boundary) is not int or type(self.return_boundary) is not int or self.signal_boundary <= 0 or self.return_boundary <= 0 or self.signal_boundary == self.return_boundary:
            raise InteropValidationError('Distinct explicit positive signal/return boundary tags required')
        if not isinstance(self.reference_impedance, Quantity):
            raise InteropValidationError('Reference impedance must be a resistance quantity')
        self.reference_impedance.require(Dimension.RESISTANCE, strictly_positive=True)


class NetworkKind(str, Enum):
    S = 'S'
    Y = 'Y'
    Z = 'Z'


@dataclass(frozen=True, slots=True)
class NetworkNormalization:
    kind: NetworkKind
    ports: tuple[SolverPort, ...]
    reference_planes: tuple[str, ...]
    convention: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, NetworkKind):
            raise InteropValidationError('Network kind must be S, Y or Z')
        _nonempty_tuple(self.ports, 'solver ports')
        if any(not isinstance(p, SolverPort) for p in self.ports):
            raise InteropValidationError('Network ports must be typed solver ports')
        _port_sequence(tuple(port.index for port in self.ports))
        _port_sequence(tuple(port.circuit_port for port in self.ports))
        if not isinstance(self.reference_planes, tuple) or len(self.reference_planes) != len(self.ports):
            raise InteropValidationError('Reference plane required for every solver port')
        for plane in self.reference_planes:
            _identifier(plane, 'reference plane')
        _unique(self.reference_planes, 'reference planes')
        if self.kind == NetworkKind.S and self.convention not in ('power_wave', 'pseudo_wave', 'traveling_wave'):
            raise InteropValidationError('S-parameter wave definition must be explicit')
        if self.kind != NetworkKind.S and self.convention != 'voltage_current':
            raise InteropValidationError('Y/Z must declare voltage/current convention')


@dataclass(frozen=True, slots=True)
class NetworkSample:
    frequency: Quantity
    values: tuple[tuple[ComplexQuantity, ...], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.frequency, Quantity):
            raise InteropValidationError('Sample frequency must be explicitly unit-aware')
        self.frequency.require(Dimension.FREQUENCY, strictly_positive=True)
        _nonempty_tuple(self.values, 'network rows')
        n = len(self.values)
        if any(not isinstance(row, tuple) or len(row) != n for row in self.values):
            raise InteropValidationError('Network sample must be a square matrix')
        if any(not isinstance(v, ComplexQuantity) for row in self.values for v in row):
            raise InteropValidationError('Network values must have explicit complex quantities')


@dataclass(frozen=True, slots=True)
class NetworkObservation:
    normalization: NetworkNormalization
    samples: tuple[NetworkSample, ...]
    source: ArtifactRef

    def __post_init__(self) -> None:
        if not isinstance(self.normalization, NetworkNormalization) or not isinstance(self.source, ArtifactRef):
            raise InteropValidationError('Network requires normalization and native source')
        _nonempty_tuple(self.samples, 'network samples')
        n = len(self.normalization.ports)
        dim = {NetworkKind.S: Dimension.DIMENSIONLESS, NetworkKind.Y: Dimension.CONDUCTANCE, NetworkKind.Z: Dimension.RESISTANCE}[self.normalization.kind]
        frequencies = []
        for sample in self.samples:
            if not isinstance(sample, NetworkSample) or len(sample.values) != n:
                raise InteropValidationError('Network sample dimension does not match port count')
            frequencies.append(sample.frequency.si().value)
            if any(v.real.dimension != dim for row in sample.values for v in row):
                raise InteropValidationError('S/Y/Z dimensions do not match network kind')
        if frequencies != sorted(set(frequencies)):
            raise InteropValidationError('Network frequencies must be distinct and increasing')
        if self.source.artifact_type not in ('palace.sparameters', 'josephson.sparameters', 'measurement.dataset'):
            raise InteropValidationError('Unverified or unsupported network source artifact')
        if self.normalization.kind != NetworkKind.S and self.source.artifact_type != 'measurement.dataset':
            raise InteropValidationError('Native Y/Z artifact types require A09 frozen-contract migration')


@dataclass(frozen=True, slots=True)
class EMMode:
    index: int
    frequency: Quantity
    source: ArtifactRef
    label: str

    def __post_init__(self) -> None:
        _positive_port(self.index)
        if not isinstance(self.frequency, Quantity):
            raise InteropValidationError('Mode frequency must be explicitly unit-aware')
        self.frequency.require(Dimension.FREQUENCY, strictly_positive=True)
        _identifier(self.label, 'EM mode label')
        if not isinstance(self.source, ArtifactRef) or self.source.artifact_type != 'palace.eigenmodes':
            raise InteropValidationError('Modes need native hashed Palace eigenmode artifact')


@dataclass(frozen=True, slots=True)
class CapacitanceMatrix:
    conductors: tuple[str, ...]
    values: tuple[tuple[Quantity, ...], ...]
    convention: str
    source: ArtifactRef

    def __post_init__(self) -> None:
        _nonempty_tuple(self.conductors, 'capacitance conductor IDs')
        for c in self.conductors:
            _identifier(c, 'conductor')
        _unique(self.conductors, 'conductors')
        n = len(self.conductors)
        if not isinstance(self.values, tuple) or len(self.values) != n or any(not isinstance(row, tuple) or len(row) != n for row in self.values):
            raise InteropValidationError('Capacitance matrix must be square with explicit conductors')
        if self.convention not in ('maxwell', 'mutual'):
            raise InteropValidationError('Capacitance convention must be Maxwell or mutual')
        for i, row in enumerate(self.values):
            for j, entry in enumerate(row):
                if not isinstance(entry, Quantity):
                    raise InteropValidationError('Matrix entries must be quantities')
                entry.require(Dimension.CAPACITANCE)
                if i == j and entry.value <= 0:
                    raise InteropValidationError('Diagonal capacitance must be positive')
                if i != j:
                    if self.convention == 'maxwell' and entry.value > 0:
                        raise InteropValidationError('Maxwell off-diagonal coefficient must be nonpositive')
                    if self.convention == 'mutual' and entry.value < 0:
                        raise InteropValidationError('Mutual capacitance must be nonnegative')
        if not isinstance(self.source, ArtifactRef) or self.source.artifact_type != 'palace.capacitance_matrix':
            raise InteropValidationError('Capacitance matrix needs native hashed Palace source')


@dataclass(frozen=True, slots=True)
class HamiltonianTerm:
    parameter: str
    value: Quantity
    model: str
    method: str
    source_artifact_sha256: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.parameter not in ('EJ', 'EC', 'EL', 'EJmax', 'g', 'chi', 'omega', 'anharmonicity'):
            raise InteropValidationError('Unknown Hamiltonian term; no inferred parameters')
        _identifier(self.model, 'quantum model')
        if self.method not in ('reviewed_epr', 'reviewed_black_box', 'reviewed_circuit_quantization'):
            raise InteropValidationError('Hamiltonian term requires explicit reviewed derivation method')
        if not isinstance(self.value, Quantity):
            raise InteropValidationError('Hamiltonian term requires explicit E/h quantity')
        self.value.require(Dimension.ENERGY_OVER_H)
        if self.parameter in ('EJ', 'EC', 'EL', 'EJmax') and self.value.value <= 0:
            raise InteropValidationError('EJ/EC/EL and EJmax must be positive')
        _nonempty_tuple(self.source_artifact_sha256, 'Hamiltonian term parents')
        for value in self.source_artifact_sha256:
            _digest(value)
        _unique(self.source_artifact_sha256, 'Hamiltonian term parents')
