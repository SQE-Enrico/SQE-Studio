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


# A12 review declarations are separate from the A01 preflight ABI. These types
# describe inspected inputs and bounded arithmetic; NONE authenticate a review,
# verify source bytes, qualify a solver or confer mode identity across revisions.
@dataclass(frozen=True, slots=True)
class EPRModeNormalization:
    """A single native *mode*, not a frequency-based cross-run mode match.

    Electric and magnetic energies are cycle-averaged Joules at the SAME
    field-amplitude normalization. Junction currents must use PEAK phasor A;
    <U_Lj> = L_j |I_peak|^2/4 and p_mj = <U_Lj>/<U_magnetic>.
    `field_export_sha256` identifies the external native field/energy export;
    its bytes and coordinate frame must be independently checked by the caller.
    """

    mode: EMMode
    magnetic_energy: 'QuantityInterval'
    electric_energy: 'QuantityInterval'
    field_export_sha256: str
    coordinate_frame: str
    current_convention: str = 'peak_phasor_amperes'
    energy_convention: str = 'cycle_averaged_joules'
    schema_version: str = 'sqe.epr-normalization.a12.v1'

    def __post_init__(self) -> None:
        from .quantities import QuantityInterval
        if self.schema_version != 'sqe.epr-normalization.a12.v1':
            raise InteropValidationError('Unsupported EPR normalization schema')
        if not isinstance(self.mode, EMMode) or any(not isinstance(e, QuantityInterval) for e in
                                                  (self.magnetic_energy, self.electric_energy)):
            raise InteropValidationError('Native mode and typed energy intervals are required')
        self.magnetic_energy.require(Dimension.ENERGY, strictly_positive=True)
        self.electric_energy.require(Dimension.ENERGY, strictly_positive=True)
        _digest(self.field_export_sha256)
        _identifier(self.coordinate_frame, 'EPR coordinate frame')
        if (self.current_convention != 'peak_phasor_amperes' or
                self.energy_convention != 'cycle_averaged_joules'):
            raise InteropValidationError('Unreviewed current/field energy normalization convention')


@dataclass(frozen=True, slots=True)
class A11ReviewedModeIdentity:
    """Contract for a *separately verified* A11 physical mode identification.

    Two different native modal solves, their mesh and field exports, and a
    *native H(curl), material-weighted, common-coordinate* complex overlap
    report must be independently verified by the authenticated caller. The
    numerical bounds and an expert decision are necessary, not sufficient:
    constructing this Python object does NOT verify files or reviewer authority.
    A11's diagnostic ParaView point-sampled L2 overlap is NOT this evidence.
    """

    target_mode: EMMode
    reference_mode: EMMode
    target_mesh: ArtifactRef
    reference_mesh: ArtifactRef
    target_field_export_sha256: str
    reference_field_export_sha256: str
    native_overlap_report_sha256: str
    physical_mode_id: str
    coordinate_frame: str
    overlap_magnitude: 'QuantityInterval'
    expert_minimum_overlap: Quantity
    review: EvidenceRecord
    overlap_method: str = 'native_hcurl_material_weighted_complex_overlap'
    phase_convention: str = 'complex_phase_invariant_common_frame'
    schema_version: str = 'sqe.a11-reviewed-mode-identity.a12.v1'

    def __post_init__(self) -> None:
        from .quantities import QuantityInterval
        if self.schema_version != 'sqe.a11-reviewed-mode-identity.a12.v1':
            raise InteropValidationError('Unsupported A11 reviewed mode identity contract')
        if (not isinstance(self.target_mode, EMMode) or not isinstance(self.reference_mode, EMMode) or
                not isinstance(self.target_mesh, ArtifactRef) or not isinstance(self.reference_mesh, ArtifactRef)):
            raise InteropValidationError('Two typed native modes and two meshes are required')
        modes = (self.target_mode, self.reference_mode)
        meshes = (self.target_mesh, self.reference_mesh)
        if any(m.source.engine != 'sqdmetal_palace' for m in modes) or any(
                a.engine != 'sqdmetal_palace' or a.artifact_type != 'gmsh.mesh' for a in meshes):
            raise InteropValidationError('A11 mode identity requires native Palace/Gmsh sources')
        if len({m.source.sha256 for m in modes}) != 2:
            raise InteropValidationError('A11 reference must be an independent native modal solve')
        revision = self.target_mode.source.revision
        if any(a.revision != revision for a in (self.reference_mode.source, *meshes)):
            raise InteropValidationError('A11 comparison crosses immutable project revisions')
        for sha in (self.target_field_export_sha256, self.reference_field_export_sha256,
                    self.native_overlap_report_sha256):
            _digest(sha)
        sources = (self.target_mode.source.sha256, self.reference_mode.source.sha256,
                   self.target_mesh.sha256, self.reference_mesh.sha256,
                   self.target_field_export_sha256, self.reference_field_export_sha256,
                   self.native_overlap_report_sha256)
        if len(set(sources)) != len(sources):
            raise InteropValidationError('A11 mode comparison lacks independent source/report digests')
        _identifier(self.physical_mode_id, 'reviewed physical mode ID')
        _identifier(self.coordinate_frame, 'mode comparison coordinate frame')
        if (self.overlap_method != 'native_hcurl_material_weighted_complex_overlap' or
                self.phase_convention != 'complex_phase_invariant_common_frame'):
            raise InteropValidationError('Diagnostic VTK/frequency/index overlap is not physical mode identity')
        if not isinstance(self.overlap_magnitude, QuantityInterval) or not isinstance(self.expert_minimum_overlap, Quantity):
            raise InteropValidationError('Complex overlap needs bounded dimensionless values and reviewed criterion')
        self.overlap_magnitude.require(Dimension.DIMENSIONLESS, nonnegative=True)
        self.expert_minimum_overlap.require(Dimension.DIMENSIONLESS, strictly_positive=True)
        if (self.overlap_magnitude.upper.si().value > 1 or self.expert_minimum_overlap.si().value > 1 or
                self.overlap_magnitude.lower.si().value < self.expert_minimum_overlap.si().value):
            raise InteropValidationError('Overlap uncertainty fails the expert-reviewed acceptance floor')
        if (not isinstance(self.review, EvidenceRecord) or self.review.kind != EvidenceKind.MODE_IDENTIFICATION or
                self.review.revision != revision or not set(sources) <= set(self.review.source_artifact_sha256) or
                self.review.document_sha256 in sources):
            raise InteropValidationError('A11 mode identity needs independent revision-bound source-complete review')

    @property
    def source_sha256(self) -> tuple[str, ...]:
        """All physical identity inputs, including the overlap derivation report."""
        return (self.target_mode.source.sha256, self.reference_mode.source.sha256,
                self.target_mesh.sha256, self.reference_mesh.sha256,
                self.target_field_export_sha256, self.reference_field_export_sha256,
                self.native_overlap_report_sha256)


@dataclass(frozen=True, slots=True)
class A17TaggedMaterialRegion:
    """A17 mesh-surface tag and calibrated constitutive values, not a PDK claim.

    Explicit mu (H/m) is needed before converting magnetic B (T) to H (A/m).
    Both epsilon and mu are *bounded declarations*, not inferred from a name.
    The region identifier and physical group must map to one target native mesh
    surface; external callers must authenticate the referenced source bytes.
    """

    region_id: str
    physical_group: int
    material_id: str
    relative_permittivity: 'QuantityInterval'
    permeability: 'QuantityInterval'
    calibration_source_sha256: str
    schema_version: str = 'sqe.a17-tagged-material.a12.v1'

    def __post_init__(self) -> None:
        from .quantities import QuantityInterval
        if self.schema_version != 'sqe.a17-tagged-material.a12.v1':
            raise InteropValidationError('Unsupported A17 tagged material schema')
        _identifier(self.region_id, 'material region ID')
        _identifier(self.material_id, 'material ID')
        if type(self.physical_group) is not int or self.physical_group < 1:
            raise InteropValidationError('A17 native surface requires positive physical group')
        if not isinstance(self.relative_permittivity, QuantityInterval) or not isinstance(self.permeability, QuantityInterval):
            raise InteropValidationError('Material requires bounded epsilon and absolute mu')
        self.relative_permittivity.require(Dimension.DIMENSIONLESS, strictly_positive=True)
        self.permeability.require(Dimension.PERMEABILITY, strictly_positive=True)
        _digest(self.calibration_source_sha256)


@dataclass(frozen=True, slots=True)
class A17ReviewedMaterialBasis:
    """A11/A17 handoff proposal: source-bound *native* basis and material tags.

    Native H(curl) edge DOFs and the B->H constitutive law must have a
    separately verified native report. Visualization VTK point arrays, names
    such as 'Aluminum', scalar eigenfrequencies, and default vacuum mu are
    insufficient. Even a valid object only records declarations: it is NOT
    cryptographic verification or independent scientific qualification.
    """

    target_mesh: ArtifactRef
    reference_mesh: ArtifactRef
    target_basis_sha256: str
    reference_basis_sha256: str
    target_surface_tags_sha256: str
    reference_surface_tags_sha256: str
    target_material_deck_sha256: str
    reference_material_deck_sha256: str
    constitutive_review_report_sha256: str
    coordinate_frame: str
    regions: tuple[A17TaggedMaterialRegion, ...]
    review: EvidenceRecord
    basis_method: str = 'native_complex_hcurl_edge_dofs_with_material_mass_matrix'
    magnetic_field_method: str = 'B_tesla_to_H_amperes_per_m_via_reviewed_spatial_mu'
    schema_version: str = 'sqe.a17-reviewed-material-basis.a12.v1'

    def __post_init__(self) -> None:
        if self.schema_version != 'sqe.a17-reviewed-material-basis.a12.v1':
            raise InteropValidationError('Unsupported A17 material-basis schema')
        for mesh in (self.target_mesh, self.reference_mesh):
            if (not isinstance(mesh, ArtifactRef) or mesh.artifact_type != 'gmsh.mesh' or
                    mesh.engine != 'sqdmetal_palace'):
                raise InteropValidationError('A17 needs native typed Gmsh/Palace meshes')
        if self.target_mesh.revision != self.reference_mesh.revision or self.target_mesh.sha256 == self.reference_mesh.sha256:
            raise InteropValidationError('A17 native material references must be distinct and revision-bound')
        _identifier(self.coordinate_frame, 'A17 coordinate frame')
        if (self.basis_method != 'native_complex_hcurl_edge_dofs_with_material_mass_matrix' or
                self.magnetic_field_method != 'B_tesla_to_H_amperes_per_m_via_reviewed_spatial_mu'):
            raise InteropValidationError('VTK point basis or assumed B/H conversion cannot qualify material transfer')
        if not isinstance(self.regions, tuple) or not self.regions or any(
                not isinstance(r, A17TaggedMaterialRegion) for r in self.regions):
            raise InteropValidationError('A17 material-tagged regions are required')
        if (len({r.region_id for r in self.regions}) != len(self.regions) or
                len({r.physical_group for r in self.regions}) != len(self.regions)):
            raise InteropValidationError('A17 region IDs and surface physical tags must be unambiguous')
        digests = self.source_sha256
        for sha in digests:
            _digest(sha)
        if len(set(digests)) != len(digests):
            raise InteropValidationError('A17 native basis, material and audit sources must be independent')
        if (not isinstance(self.review, EvidenceRecord) or
                self.review.kind != EvidenceKind.MATERIAL_AND_BOUNDARY_REVIEW or
                self.review.revision != self.target_mesh.revision or
                not set(digests) <= set(self.review.source_artifact_sha256) or
                self.review.document_sha256 in digests):
            raise InteropValidationError('A17 requires a separately reviewed source-complete material/basis attestation')

    @property
    def source_sha256(self) -> tuple[str, ...]:
        return (self.target_mesh.sha256, self.reference_mesh.sha256,
                self.target_basis_sha256, self.reference_basis_sha256,
                self.target_surface_tags_sha256, self.reference_surface_tags_sha256,
                self.target_material_deck_sha256, self.reference_material_deck_sha256,
                self.constitutive_review_report_sha256,
                *(r.calibration_source_sha256 for r in self.regions))


@dataclass(frozen=True, slots=True)
class JunctionSurfaceMapping:
    """One physical JJ circuit element, signed geometry and mesh region."""

    junction_id: str
    element_id: str
    geometry_id: str
    mesh_region_id: str
    physical_group: int
    schema_version: str = 'sqe.junction-surface.a12.v1'

    def __post_init__(self) -> None:
        if self.schema_version != 'sqe.junction-surface.a12.v1':
            raise InteropValidationError('Unsupported JJ surface mapping schema')
        for name in (self.junction_id, self.element_id, self.geometry_id, self.mesh_region_id):
            _identifier(name, 'junction mapping identity')
        if type(self.physical_group) is not int or self.physical_group <= 0:
            raise InteropValidationError('Junction requires a positive mesh physical group')


@dataclass(frozen=True, slots=True)
class JunctionEPRSample:
    """Source-bound peak current and independently calibrated LJ declarations.

    The field-export digest pins current amplitude to the SAME EPR mode
    normalization. A distinct extraction review document must cover its mesh,
    field and calibration; that external document is NOT authenticated here.
    """

    junction_id: str
    inductance: 'QuantityInterval'
    peak_current: 'QuantityInterval'
    revision: RevisionBinding
    field_export_sha256: str
    calibration_review_sha256: str
    schema_version: str = 'sqe.junction-epr-sample.a12.v2'

    def __post_init__(self) -> None:
        from .quantities import QuantityInterval
        if self.schema_version != 'sqe.junction-epr-sample.a12.v2':
            raise InteropValidationError('Unsupported EPR sample schema')
        _identifier(self.junction_id, 'junction ID')
        if not isinstance(self.revision, RevisionBinding):
            raise InteropValidationError('Junction sample needs immutable revision binding')
        _digest(self.field_export_sha256)
        _digest(self.calibration_review_sha256)
        if self.field_export_sha256 == self.calibration_review_sha256:
            raise InteropValidationError('Calibration review is not an independent field export')
        if not isinstance(self.inductance, QuantityInterval) or not isinstance(self.peak_current, QuantityInterval):
            raise InteropValidationError('Junction requires typed LJ and peak-current bounds')
        self.inductance.require(Dimension.INDUCTANCE, strictly_positive=True)
        self.peak_current.require(Dimension.CURRENT, nonnegative=True)


@dataclass(frozen=True, slots=True)
class EPRParticipation:
    """A bounded magnetic-energy fraction, NOT a Kerr or coupling parameter."""

    mode_index: int
    mode_label: str
    junction_id: str
    fraction: 'QuantityInterval'
    revision: RevisionBinding
    source_artifact_sha256: tuple[str, ...]
    schema_version: str = 'sqe.epr-participation.a12.v1'

    def __post_init__(self) -> None:
        from .quantities import QuantityInterval
        if self.schema_version != 'sqe.epr-participation.a12.v1':
            raise InteropValidationError('Unsupported EPR participation schema')
        _positive_port(self.mode_index)
        _identifier(self.mode_label, 'mode label')
        _identifier(self.junction_id, 'junction ID')
        if not isinstance(self.fraction, QuantityInterval):
            raise InteropValidationError('Participation needs bounded dimensionless quantity')
        self.fraction.require(Dimension.DIMENSIONLESS, nonnegative=True)
        if self.fraction.upper.si().value > 1:
            raise InteropValidationError('Unphysical EPR participation above one')
        if not isinstance(self.revision, RevisionBinding):
            raise InteropValidationError('Participation requires revision binding')
        _nonempty_tuple(self.source_artifact_sha256, 'EPR parent hashes')
        for sha in self.source_artifact_sha256:
            _digest(sha)
        _unique(self.source_artifact_sha256, 'EPR parent hashes')


@dataclass(frozen=True, slots=True)
class ReviewedHamiltonianParameter:
    """Computed EJ/h with explicit bounds; never a qualified spectrum or g/chi."""

    junction_id: str
    term: HamiltonianTerm
    interval: 'QuantityInterval'
    revision: RevisionBinding
    schema_version: str = 'sqe.reviewed-hamiltonian.a12.v1'

    def __post_init__(self) -> None:
        from .quantities import QuantityInterval
        if self.schema_version != 'sqe.reviewed-hamiltonian.a12.v1':
            raise InteropValidationError('Unsupported reviewed Hamiltonian schema')
        _identifier(self.junction_id, 'junction ID')
        if not isinstance(self.term, HamiltonianTerm) or self.term.parameter != 'EJ':
            raise InteropValidationError('A12 only derives EJ from reviewed junction inductance')
        if not isinstance(self.interval, QuantityInterval):
            raise InteropValidationError('EJ must retain absolute uncertainty bounds')
        self.interval.require(Dimension.ENERGY_OVER_H, strictly_positive=True)
        if self.term.value.si() != self.interval.nominal.si():
            raise InteropValidationError('EJ term/interval values disagree')
        if not isinstance(self.revision, RevisionBinding):
            raise InteropValidationError('Hamiltonian parameter requires revision')


@dataclass(frozen=True, slots=True)
class ReviewedEPRTransition:
    """Reviewable numerical proposal: never native or scientific qualification."""

    normalization: EPRModeNormalization
    mappings: tuple[JunctionSurfaceMapping, ...]
    participations: tuple[EPRParticipation, ...]
    ej_parameters: tuple[ReviewedHamiltonianParameter, ...]
    evidence: tuple[EvidenceRecord, ...]
    revision: RevisionBinding
    mode_identity: A11ReviewedModeIdentity
    material_basis: A17ReviewedMaterialBasis
    schema_version: str = 'sqe.em-epr-hamiltonian.a12.v3'
    status: str = 'NUMERICAL_REVIEW_ONLY_NATIVE_AND_SCIENTIFIC_QUALIFICATION_BLOCKED'

    def __post_init__(self) -> None:
        if (self.schema_version != 'sqe.em-epr-hamiltonian.a12.v3' or
                self.status != 'NUMERICAL_REVIEW_ONLY_NATIVE_AND_SCIENTIFIC_QUALIFICATION_BLOCKED'):
            raise InteropValidationError('Unsupported transition version or qualification state')
        if (not isinstance(self.normalization, EPRModeNormalization) or
                not isinstance(self.revision, RevisionBinding) or
                not isinstance(self.mode_identity, A11ReviewedModeIdentity) or
                not isinstance(self.material_basis, A17ReviewedMaterialBasis) or
                not isinstance(self.mappings, tuple) or not self.mappings or
                not isinstance(self.participations, tuple) or not self.participations or
                not isinstance(self.ej_parameters, tuple) or not self.ej_parameters or
                not isinstance(self.evidence, tuple) or not self.evidence):
            raise InteropValidationError('Incomplete reviewed EPR transition')
        if (self.mode_identity.target_mode != self.normalization.mode or
                self.mode_identity.target_field_export_sha256 != self.normalization.field_export_sha256 or
                self.mode_identity.coordinate_frame != self.normalization.coordinate_frame or
                self.mode_identity.review not in self.evidence or
                self.mode_identity.target_mode.source.revision != self.revision or
                self.material_basis.target_mesh != self.mode_identity.target_mesh or
                self.material_basis.reference_mesh != self.mode_identity.reference_mesh or
                self.material_basis.coordinate_frame != self.normalization.coordinate_frame or
                self.material_basis.review not in self.evidence):
            raise InteropValidationError('Mode identity does not bind EPR normalization and review')
        if any(not isinstance(m, JunctionSurfaceMapping) for m in self.mappings):
            raise InteropValidationError('Invalid EPR junction mapping')
        if any(not isinstance(p, EPRParticipation) or p.revision != self.revision for p in self.participations):
            raise InteropValidationError('Participation provenance is not revision-bound')
        if any(not isinstance(p, ReviewedHamiltonianParameter) or p.revision != self.revision for p in self.ej_parameters):
            raise InteropValidationError('EJ provenance is not revision-bound')
        if any(not isinstance(e, EvidenceRecord) or e.revision != self.revision for e in self.evidence):
            raise InteropValidationError('Review provenance is not revision-bound')
        junctions = {m.junction_id for m in self.mappings}
        if (len(junctions) != len(self.mappings) or
                len(self.participations) != len(junctions) or
                len(self.ej_parameters) != len(junctions) or
                {p.junction_id for p in self.participations} != junctions or
                {p.junction_id for p in self.ej_parameters} != junctions):
            raise InteropValidationError('A12 transition must cover every unique JJ exactly once')
        sources = set(self.mode_identity.source_sha256) | set(self.material_basis.source_sha256)
        for participation in self.participations:
            if (participation.mode_index != self.normalization.mode.index or
                    participation.mode_label != self.normalization.mode.label or
                    not sources <= set(participation.source_artifact_sha256)):
                raise InteropValidationError('A12 participation lost native mode/material provenance')
        for param in self.ej_parameters:
            if (param.term.model != param.junction_id or
                    not sources <= set(param.term.source_artifact_sha256)):
                raise InteropValidationError('A12 Hamiltonian parameter lost JJ or material provenance')


@dataclass(frozen=True, slots=True)
class EPRHandoffResult:
    """GUI-consumable fail-closed scientific state; no implicit usable terms."""

    revision: RevisionBinding
    status: str
    explanation: str
    transition: ReviewedEPRTransition | None = None
    schema_version: str = 'sqe.epr-handoff-decision.a12.v1'

    def __post_init__(self) -> None:
        blocked = ('BLOCKED_A11_MODE_IDENTITY', 'BLOCKED_A17_MATERIAL_BASIS', 'BLOCKED_EPR_REVIEW_OR_UNITS', 'BLOCKED_STALE_REVISION')
        if (self.schema_version != 'sqe.epr-handoff-decision.a12.v1' or
                not isinstance(self.revision, RevisionBinding) or
                not isinstance(self.explanation, str) or not self.explanation.strip() or
                len(self.explanation) > 1000):
            raise InteropValidationError('Invalid GUI EPR handoff decision')
        if self.status in blocked:
            if self.transition is not None:
                raise InteropValidationError('Blocked EPR result must not expose numerical terms')
        elif self.status == 'NUMERICAL_REVIEW_ONLY_NATIVE_AND_SCIENTIFIC_QUALIFICATION_BLOCKED':
            if not isinstance(self.transition, ReviewedEPRTransition) or self.transition.revision != self.revision:
                raise InteropValidationError('Numerical-only decision requires revision-bound proposal')
        else:
            raise InteropValidationError('Unrecognized EPR scientific state')


# RC14.10 B04/B06/B08 specialist contracts. These immutable declarations do
# not read native output, authenticate reviewers or confer scientific PASS.
@dataclass(frozen=True, slots=True)
class CapacitanceECReviewInput:
    """Maxwell electrostatic island C_ii with EVERY other conductor grounded.

    No automatic node elimination, floating island Schur complement, conversion
    from mutual coefficients, or unidentified environmental capacitance. The
    external caller must verify the Palace matrix bytes, conductor ordering and
    independently reviewed electrostatic boundary/ground assumptions.
    """

    matrix: CapacitanceMatrix
    revision: RevisionBinding
    island_conductor: str
    return_conductor: str
    grounded_conductors: tuple[str, ...]
    matrix_export_sha256: str
    island_capacitance: 'QuantityInterval'
    symmetry_tolerance: Quantity
    charge_balance_tolerance: Quantity
    extraction_review: EvidenceRecord
    quantization_review: EvidenceRecord
    schema_version: str = 'sqe.capacitance-ec-input.a12.v1'

    def __post_init__(self) -> None:
        from .quantities import QuantityInterval
        if self.schema_version != 'sqe.capacitance-ec-input.a12.v1':
            raise InteropValidationError('Unsupported B04 capacitance input schema')
        if not isinstance(self.matrix, CapacitanceMatrix) or self.matrix.convention != 'maxwell':
            raise InteropValidationError('B04 needs native Maxwell C matrix, not unsigned mutual coefficients')
        if not isinstance(self.revision, RevisionBinding) or self.matrix.source.revision != self.revision:
            raise InteropValidationError('B04 source must bind the active immutable revision')
        if self.matrix.source.engine != 'sqdmetal_palace':
            raise InteropValidationError('B04 requires a native Palace electrostatic source')
        for identifier in (self.island_conductor, self.return_conductor):
            _identifier(identifier, 'B04 conductor')
        if self.island_conductor == self.return_conductor or self.island_conductor not in self.matrix.conductors:
            raise InteropValidationError('B04 needs distinct selected island/return conductors')
        if (not isinstance(self.grounded_conductors, tuple) or
                len(set(self.grounded_conductors)) != len(self.grounded_conductors) or
                set(self.grounded_conductors) != set(self.matrix.conductors) - {self.island_conductor} or
                self.return_conductor not in self.grounded_conductors):
            raise InteropValidationError('B04 all non-island conductors must be explicitly grounded')
        _digest(self.matrix_export_sha256)
        if self.matrix_export_sha256 == self.matrix.source.sha256:
            raise InteropValidationError('Matrix native export and artifact digests must be distinct')
        if not isinstance(self.island_capacitance, QuantityInterval):
            raise InteropValidationError('B04 requires uncertainty-bounded island capacitance')
        self.island_capacitance.require(Dimension.CAPACITANCE, strictly_positive=True)
        for tol in (self.symmetry_tolerance, self.charge_balance_tolerance):
            if not isinstance(tol, Quantity):
                raise InteropValidationError('B04 numerical tolerances must carry F units')
            tol.require(Dimension.CAPACITANCE, nonnegative=True)
            # A permissive review threshold cannot launder an unphysical matrix.
            minimum_diagonal = min(self.matrix.values[i][i].si().value
                                   for i in range(len(self.matrix.conductors)))
            if tol.si().value >= minimum_diagonal / Decimal(100):
                raise InteropValidationError('B04 matrix tolerance must be below 1% of minimum diagonal')
        expected = {self.matrix.source.sha256, self.matrix_export_sha256}
        for review, kind in ((self.extraction_review, EvidenceKind.EXTRACTION_VALIDATION),
                             (self.quantization_review, EvidenceKind.QUANTIZATION_DERIVATION)):
            if (not isinstance(review, EvidenceRecord) or review.kind != kind or
                    review.revision != self.revision or not expected <= set(review.source_artifact_sha256) or
                    review.document_sha256 in expected):
                raise InteropValidationError('B04 needs source-complete independent extraction and EC reviews')
        if self.extraction_review.document_sha256 == self.quantization_review.document_sha256:
            raise InteropValidationError('B04 extraction and EC quantization reviews must be independent')


@dataclass(frozen=True, slots=True)
class ECScreeningResult:
    """Csum and EC/h *screening*, never an activated Hamiltonian term."""

    revision: RevisionBinding
    island_conductor: str
    effective_capacitance: 'QuantityInterval'
    ec_over_h: 'QuantityInterval'
    parent_sha256: tuple[str, ...]
    status: str = 'NUMERICAL_EC_SCREEN_ONLY_NATIVE_AND_SCIENTIFIC_QUALIFICATION_BLOCKED'
    schema_version: str = 'sqe.capacitance-ec-screen.a12.v1'

    def __post_init__(self) -> None:
        from .quantities import QuantityInterval
        if (self.schema_version != 'sqe.capacitance-ec-screen.a12.v1' or
                self.status != 'NUMERICAL_EC_SCREEN_ONLY_NATIVE_AND_SCIENTIFIC_QUALIFICATION_BLOCKED'):
            raise InteropValidationError('B04 result cannot promote scientific status')
        if not isinstance(self.revision, RevisionBinding):
            raise InteropValidationError('B04 requires revision binding')
        _identifier(self.island_conductor)
        if not isinstance(self.effective_capacitance, QuantityInterval) or not isinstance(self.ec_over_h, QuantityInterval):
            raise InteropValidationError('B04 requires numerical intervals')
        self.effective_capacitance.require(Dimension.CAPACITANCE, strictly_positive=True)
        self.ec_over_h.require(Dimension.ENERGY_OVER_H, strictly_positive=True)
        _nonempty_tuple(self.parent_sha256, 'B04 independent parents')
        for sha in self.parent_sha256:
            _digest(sha)
        _unique(self.parent_sha256, 'B04 independent parents')


@dataclass(frozen=True, slots=True)
class NativeEPRReference:
    """Declared native signed-current orientation + nonnegative energy EPR.

    Current orientation is relative to explicitly ordered circuit terminals;
    p_j is an energy fraction and must NOT carry a negative sign. No phase or
    sign is reconstructed from |I_peak| or mode index.
    """

    junction_id: str
    mode_index: int
    physical_mode_id: str
    positive_node: str
    negative_node: str
    current_orientation: int
    peak_current: 'QuantityInterval'
    energy_fraction: 'QuantityInterval'
    revision: RevisionBinding
    schema_version: str = 'sqe.native-epr-reference.a12.v1'

    def __post_init__(self) -> None:
        from .quantities import QuantityInterval
        if self.schema_version != 'sqe.native-epr-reference.a12.v1':
            raise InteropValidationError('Unsupported native EPR reference schema')
        _identifier(self.junction_id, 'junction ID')
        _positive_port(self.mode_index)
        _identifier(self.physical_mode_id, 'physical mode ID')
        for node in (self.positive_node, self.negative_node):
            _identifier(node, 'oriented JJ node')
        if self.positive_node == self.negative_node or type(self.current_orientation) is not int or self.current_orientation not in (-1, 1):
            raise InteropValidationError('Native JJ orientation must be explicitly signed and terminals distinct')
        if not isinstance(self.peak_current, QuantityInterval) or not isinstance(self.energy_fraction, QuantityInterval):
            raise InteropValidationError('Native EPR requires bounded current and energy fractions')
        self.peak_current.require(Dimension.CURRENT, nonnegative=True)
        self.energy_fraction.require(Dimension.DIMENSIONLESS, nonnegative=True)
        if self.energy_fraction.upper.si().value > 1:
            raise InteropValidationError('Native EPR energy fraction cannot exceed unity')
        if not isinstance(self.revision, RevisionBinding):
            raise InteropValidationError('Native EPR must bind source revision')


@dataclass(frozen=True, slots=True)
class NativeEPRBenchmarkInput:
    """B06 independently reviewed native participation/energy comparison.

    The *native* magnetic energy and its separate export digest are mandatory.
    It must represent cycle-averaged Joules for the exact field amplitude used
    by native *peak-phasor* junction currents. This declaration cannot prove
    the native source bytes, reviewer authority, or the physical mode match.
    """

    transition: ReviewedEPRTransition
    element_mappings: tuple[ElementGeometryMapping, ...]
    samples: tuple[JunctionEPRSample, ...]
    references: tuple[NativeEPRReference, ...]
    native_epr_report_sha256: str
    field_export_sha256: str
    absolute_tolerance: Quantity
    native_extraction_review: EvidenceRecord
    revision: RevisionBinding
    native_magnetic_energy: 'QuantityInterval | None' = None
    native_energy_export_sha256: str = ''
    native_energy_convention: str = 'cycle_averaged_joules'
    native_current_convention: str = 'peak_phasor_amperes'
    schema_version: str = 'sqe.native-epr-benchmark.a12.v2'

    def __post_init__(self) -> None:
        from .quantities import QuantityInterval
        if self.schema_version != 'sqe.native-epr-benchmark.a12.v2':
            raise InteropValidationError('Unsupported B06 native-energy benchmark schema')
        if not isinstance(self.transition, ReviewedEPRTransition) or self.transition.revision != self.revision:
            raise InteropValidationError('B06 needs the reviewed blocked-only A11/A17 EPR proposal')
        for field_name, kind in (('element_mappings', ElementGeometryMapping),
                                 ('samples', JunctionEPRSample), ('references', NativeEPRReference)):
            values = getattr(self, field_name)
            if not isinstance(values, tuple) or not values or any(not isinstance(v, kind) for v in values):
                raise InteropValidationError('B06 needs typed native JJ declaration coverage')
        ids = {m.junction_id for m in self.transition.mappings}
        if (len(self.references) != len(ids) or {r.junction_id for r in self.references} != ids or
                len({r.junction_id for r in self.references}) != len(ids) or
                len(self.samples) != len(ids) or {s.junction_id for s in self.samples} != ids or
                len({s.junction_id for s in self.samples}) != len(ids)):
            raise InteropValidationError('B06 native references and peak currents must cover each JJ exactly once')
        if (any(r.revision != self.revision for r in self.references) or
                any(s.revision != self.revision for s in self.samples)):
            raise InteropValidationError('B06 mixed-source revisions are forbidden')
        if not isinstance(self.native_magnetic_energy, QuantityInterval):
            raise InteropValidationError('B06 requires independent native magnetic-energy normalization')
        self.native_magnetic_energy.require(Dimension.ENERGY, strictly_positive=True)
        if (self.native_energy_convention != 'cycle_averaged_joules' or
                self.native_current_convention != 'peak_phasor_amperes' or
                self.transition.normalization.energy_convention != self.native_energy_convention or
                self.transition.normalization.current_convention != self.native_current_convention):
            raise InteropValidationError('B06 native and reviewed energy/current phasor conventions differ')
        for sha in (self.native_epr_report_sha256, self.native_energy_export_sha256, self.field_export_sha256):
            _digest(sha)
        if (len({self.native_epr_report_sha256, self.native_energy_export_sha256,
                 self.field_export_sha256}) != 3 or
                self.field_export_sha256 != self.transition.normalization.field_export_sha256):
            raise InteropValidationError('B06 independent native energy/EPR/field exports are absent or aliased')
        known_parents = (set(self.transition.mode_identity.source_sha256) |
                         set(self.transition.material_basis.source_sha256) |
                         {self.transition.normalization.mode.source.sha256})
        if {self.native_epr_report_sha256, self.native_energy_export_sha256} & known_parents:
            raise InteropValidationError('B06 native report/energy export cannot alias prior mode/material parents')
        if any(s.field_export_sha256 != self.field_export_sha256 for s in self.samples):
            raise InteropValidationError('B06 peak currents are not tied to the reviewed field amplitude')
        if not isinstance(self.absolute_tolerance, Quantity):
            raise InteropValidationError('B06 requires dimensionless reviewed mismatch tolerance')
        self.absolute_tolerance.require(Dimension.DIMENSIONLESS, nonnegative=True)
        if self.absolute_tolerance.si().value >= 1:
            raise InteropValidationError('B06 mismatch tolerance cannot bypass energy fraction bounds')
        required = {self.native_epr_report_sha256, self.native_energy_export_sha256,
                    self.field_export_sha256, *self.transition.mode_identity.source_sha256,
                    *self.transition.material_basis.source_sha256}
        review = self.native_extraction_review
        if (not isinstance(review, EvidenceRecord) or review.kind != EvidenceKind.EXTRACTION_VALIDATION or
                review.revision != self.revision or not required <= set(review.source_artifact_sha256) or
                review.document_sha256 in required):
            raise InteropValidationError('B06 energy/EPR exports need an independent source-complete review')


@dataclass(frozen=True, slots=True)
class NativeEPRComparison:
    """Bounded reference mismatch, always scientific BLOCKED, never a PASS."""

    revision: RevisionBinding
    absolute_residuals: tuple[tuple[str, Quantity], ...]
    parent_sha256: tuple[str, ...]
    status: str = 'NUMERICAL_NATIVE_EPR_COMPARISON_ONLY_SCIENTIFIC_QUALIFICATION_BLOCKED'
    schema_version: str = 'sqe.native-epr-comparison.a12.v1'

    def __post_init__(self) -> None:
        if (self.schema_version != 'sqe.native-epr-comparison.a12.v1' or
                self.status != 'NUMERICAL_NATIVE_EPR_COMPARISON_ONLY_SCIENTIFIC_QUALIFICATION_BLOCKED'):
            raise InteropValidationError('B06 cannot promote scientific status')
        if not isinstance(self.revision, RevisionBinding) or not self.absolute_residuals:
            raise InteropValidationError('B06 needs matched revision and native residuals')
        _unique(tuple(j for j, _ in self.absolute_residuals), 'B06 junction residuals')
        for j, residual in self.absolute_residuals:
            _identifier(j, 'B06 junction ID')
            if not isinstance(residual, Quantity):
                raise InteropValidationError('B06 residual requires quantity')
            residual.require(Dimension.DIMENSIONLESS, nonnegative=True)
        _nonempty_tuple(self.parent_sha256, 'B06 provenance')
        for sha in self.parent_sha256:
            _digest(sha)
        _unique(self.parent_sha256, 'B06 provenance')


@dataclass(frozen=True, slots=True)
class IndependentScqubitsParameters:
    """B08 independent circuit input only; not an EM-derived quantum handoff.

    scqubits output/actual eigenvalues, cross-cutoff convergence and physics
    validation are the responsibility of the native A16 runner. The SHA and
    review here are *declarations*, not authenticated evidence by themselves.
    """

    model: str
    ej_over_h: Quantity
    ec_over_h: Quantity
    el_over_h: Quantity | None
    external_flux_phi0: Quantity | None
    offset_charge: Quantity | None
    basis_cutoff: int
    truncated_dim: int
    source: ArtifactRef
    independent_review: EvidenceRecord
    schema_version: str = 'sqe.independent-scqubits-input.a12.v1'

    def __post_init__(self) -> None:
        if self.schema_version != 'sqe.independent-scqubits-input.a12.v1':
            raise InteropValidationError('Unsupported B08 independent parameter schema')
        if self.model not in ('transmon', 'fluxonium'):
            raise InteropValidationError('Only explicitly selected transmon/fluxonium screens supported')
        for energy in (self.ej_over_h, self.ec_over_h):
            if not isinstance(energy, Quantity):
                raise InteropValidationError('B08 requires explicit EJ/h and EC/h')
            energy.require(Dimension.ENERGY_OVER_H, strictly_positive=True)
        if self.model == 'transmon':
            if self.el_over_h is not None or self.external_flux_phi0 is not None or self.offset_charge is None:
                raise InteropValidationError('Transmon requires ng but not guessed EL/flux')
        else:
            if self.el_over_h is None or self.external_flux_phi0 is None or self.offset_charge is not None:
                raise InteropValidationError('Fluxonium requires explicit EL and Phi/Phi0, not ng')
        if self.el_over_h is not None:
            if not isinstance(self.el_over_h, Quantity):
                raise InteropValidationError('B08 EL must carry E/h units')
            self.el_over_h.require(Dimension.ENERGY_OVER_H, strictly_positive=True)
        for val in (self.external_flux_phi0, self.offset_charge):
            if val is not None:
                if not isinstance(val, Quantity):
                    raise InteropValidationError('B08 charge/flux must be dimensionless')
                val.require(Dimension.DIMENSIONLESS)
        max_states = 2 * self.basis_cutoff + 1 if self.model == 'transmon' else self.basis_cutoff
        if (type(self.basis_cutoff) is not int or not 3 <= self.basis_cutoff <= 512 or
                type(self.truncated_dim) is not int or not 2 <= self.truncated_dim <= max_states):
            raise InteropValidationError('B08 cutoff and Hilbert truncation must be explicit valid integers')
        if (not isinstance(self.source, ArtifactRef) or self.source.artifact_type not in
                ('measurement.dataset', 'circuit.netlist') or self.source.engine != 'external'):
            raise InteropValidationError('B08 independent inputs cannot come from unverified EM extraction')
        if (not isinstance(self.independent_review, EvidenceRecord) or
                self.independent_review.kind != EvidenceKind.QUANTIZATION_DERIVATION or
                self.independent_review.revision != self.source.revision or
                self.source.sha256 not in self.independent_review.source_artifact_sha256 or
                self.independent_review.document_sha256 == self.source.sha256):
            raise InteropValidationError('B08 requires separate revision-bound independent parameter review')


@dataclass(frozen=True, slots=True)
class ScqubitsParameterScreen:
    parameters: IndependentScqubitsParameters
    status: str = 'INDEPENDENT_INPUT_ONLY_NATIVE_SPECTRUM_AND_SCIENTIFIC_QUALIFICATION_BLOCKED'
    schema_version: str = 'sqe.independent-scqubits-screen.a12.v1'

    def __post_init__(self) -> None:
        if (self.schema_version != 'sqe.independent-scqubits-screen.a12.v1' or
                self.status != 'INDEPENDENT_INPUT_ONLY_NATIVE_SPECTRUM_AND_SCIENTIFIC_QUALIFICATION_BLOCKED' or
                not isinstance(self.parameters, IndependentScqubitsParameters)):
            raise InteropValidationError('B08 cannot claim native scqubits execution or scientific PASS')
