"""Deterministic re-encoding only. No S<->Y<->Z physics, mesh or quantum inference."""
from __future__ import annotations

from .models import NetworkNormalization, NetworkObservation, NetworkSample, SolverPort
from .preflight import UnsafeMapping
from .quantities import Dimension, Quantity


def frequency_as(value: Quantity, unit: str = 'Hz') -> Quantity:
    return value.require(Dimension.FREQUENCY).as_unit(unit)


def capacitance_as(value: Quantity, unit: str = 'F') -> Quantity:
    return value.require(Dimension.CAPACITANCE).as_unit(unit)


def convert_network_frequency_units(observation: NetworkObservation, unit: str) -> NetworkObservation:
    """Re-encode frequencies only; preserve native complex matrix measurements."""
    if not isinstance(observation, NetworkObservation):
        raise UnsafeMapping('A typed source network observation is required')
    return NetworkObservation(
        observation.normalization,
        tuple(NetworkSample(s.frequency.as_unit(unit), s.values) for s in observation.samples),
        observation.source,
    )


def reorder_network_ports(observation: NetworkObservation, old_ports_in_new_order: tuple[int, ...]) -> NetworkObservation:
    """Explicit matrix permutation with new contiguous one-based indices.

    Ports are never guessed from geometrical order. Signals/returns and matrix
    row *and* column order are permuted together. No reference renormalization.
    """
    if not isinstance(observation, NetworkObservation):
        raise UnsafeMapping('A typed source network observation is required')
    n = len(observation.normalization.ports)
    if (not isinstance(old_ports_in_new_order, tuple) or len(old_ports_in_new_order) != n or
            set(old_ports_in_new_order) != set(range(1, n + 1)) or any(type(p) is not int for p in old_ports_in_new_order)):
        raise UnsafeMapping('Explicit complete port permutation of 1..N is required')
    old = {p.index: i for i, p in enumerate(observation.normalization.ports)}
    indices = tuple(old[p] for p in old_ports_in_new_order)
    oldnorm = observation.normalization
    newports = tuple(SolverPort(i + 1, oldnorm.ports[j].signal_boundary,
                                oldnorm.ports[j].return_boundary,
                                oldnorm.ports[j].circuit_port, oldnorm.ports[j].reference_impedance)
                     for i, j in enumerate(indices))
    newnorm = NetworkNormalization(oldnorm.kind, newports,
                                   tuple(oldnorm.reference_planes[j] for j in indices), oldnorm.convention)
    samples = tuple(NetworkSample(s.frequency, tuple(tuple(s.values[i][j] for j in indices) for i in indices))
                    for s in observation.samples)
    return NetworkObservation(newnorm, samples, observation.source)


# A12: bounded reviewed arithmetic, not an automatic solver-to-quantum edge.
# Source artifacts / review-document SHA values are DECLARED by this pure API.
# The authenticated caller must verify them against immutable stored bytes and
# reviewer authority before displaying the result as externally reviewed.
from decimal import Decimal, localcontext

from .models import (
    A11ReviewedModeIdentity, A17ReviewedMaterialBasis, CircuitNetlist, ElementGeometryMapping, ElementKind,
    EPRHandoffResult, EPRModeNormalization,
    EPRParticipation, EvidenceKind, EvidenceRecord, HamiltonianTerm,
    JunctionEPRSample, JunctionSurfaceMapping, MeshRegion,
    ReviewedEPRTransition, ReviewedHamiltonianParameter, RevisionBinding,
)
from .preflight import InteropBlocked, MissingEvidence, StaleRevision
from .quantities import InteropValidationError, QuantityInterval

# Exact 2019 SI h and elementary charge; pi is a 50-digit numerical constant.
# EJ/h = (Phi0/2pi)^2 / (h LJ) = h/(16 pi^2 e^2 LJ), in cyclic Hz, NOT rad/s.
_PLANCK_J_S = Decimal('6.62607015e-34')
_ELEMENTARY_CHARGE_C = Decimal('1.602176634e-19')
_PI = Decimal('3.14159265358979323846264338327950288419716939937510')
_EPR_REQUIRED_REVIEWS = {
    EvidenceKind.MODE_IDENTIFICATION,
    EvidenceKind.GEOMETRY_REVIEW,
    EvidenceKind.MATERIAL_AND_BOUNDARY_REVIEW,
    EvidenceKind.QUANTIZATION_DERIVATION,
    EvidenceKind.EXTRACTION_VALIDATION,
}


def _interval(nominal: Decimal, lower: Decimal, upper: Decimal,
              unit: str, dimension: Dimension) -> QuantityInterval:
    return QuantityInterval(Quantity(nominal, unit, dimension),
                            Quantity(lower, unit, dimension),
                            Quantity(upper, unit, dimension))


def em_to_reviewed_epr(
    *, netlist: CircuitNetlist, normalization: EPRModeNormalization,
    mesh_regions: tuple[MeshRegion, ...],
    element_mappings: tuple[ElementGeometryMapping, ...],
    junction_mappings: tuple[JunctionSurfaceMapping, ...],
    samples: tuple[JunctionEPRSample, ...],
    evidence: tuple[EvidenceRecord, ...],
    active_revision: RevisionBinding,
    mode_identity: A11ReviewedModeIdentity | None = None,
    material_basis: A17ReviewedMaterialBasis | None = None,
) -> ReviewedEPRTransition:
    """Compute *bounded* p_mj and EJ/h from fully declared, reviewed inputs.

    p_mj = (LJ * abs(I_peak)^2 / 4) / U_magnetic, where U_magnetic is
    cycle-averaged magnetic energy in J for the SAME native mode and amplitude
    normalization, LJ is H, I_peak is peak-phasor A and p is dimensionless.
    Electric and magnetic cycle-average energy bounds must overlap. All
    junction-current samples, maps and source hashes must be reviewable.
    Values are NOT complex field overlap, dressed/anharmonic quantum spectra,
    chi, g, self/cross-Kerr or a qualified scientific result. This procedure
    does not open/verify SHA-256 source bytes or authenticate reviewer identity.
    A11's existing VTK point-field diagnostic is explicitly insufficient for
    physical mode identity; only an independently reviewed native H(curl)
    common-frame overlap with a bound expert decision is accepted as input.
    A17 must additionally bind native complex H(curl) basis and both mesh
    material decks, physical-group audits and spatial epsilon/mu calibration;
    no vacuum B=mu0 H shortcut or unreviewed material name is accepted.
    The returned proposal remains scientifically BLOCKED even with that input.
    """
    if not isinstance(active_revision, RevisionBinding) or not isinstance(netlist, CircuitNetlist) or not isinstance(normalization, EPRModeNormalization):
        raise UnsafeMapping('Typed revision, netlist and EM field normalization are required')
    if not isinstance(mode_identity, A11ReviewedModeIdentity):
        raise MissingEvidence('A11 physical mode identity is unresolved: native complex H(curl) '
                              'overlap, common-frame projection and expert review are required; '
                              'frequency or solver ordinal is not a mode match')
    if (mode_identity.target_mode != normalization.mode or
            mode_identity.target_field_export_sha256 != normalization.field_export_sha256 or
            mode_identity.coordinate_frame != normalization.coordinate_frame):
        raise UnsafeMapping('A11 reviewed physical mode and EPR amplitude/coordinate frame disagree')
    if mode_identity.target_mode.source.revision != active_revision:
        raise StaleRevision()
    if not isinstance(material_basis, A17ReviewedMaterialBasis):
        raise MissingEvidence('A17 native basis, material/constitutive calibration and physical-tag audit are absent')
    if (material_basis.target_mesh != mode_identity.target_mesh or
            material_basis.reference_mesh != mode_identity.reference_mesh or
            material_basis.coordinate_frame != normalization.coordinate_frame):
        raise UnsafeMapping('A17 material/basis sources are not the A11-reviewed modes and common frame')
    if material_basis.target_mesh.revision != active_revision or material_basis.review.revision != active_revision:
        raise StaleRevision()
    mode_source = normalization.mode.source
    if mode_source.engine != 'sqdmetal_palace':
        raise UnsafeMapping('EPR input requires a native Palace mode artifact')
    if (not isinstance(mesh_regions, tuple) or not mesh_regions or
            any(not isinstance(r, MeshRegion) for r in mesh_regions)):
        raise UnsafeMapping('Real typed junction mesh regions are required')
    if any(r.source.engine != 'sqdmetal_palace' for r in mesh_regions):
        raise UnsafeMapping('EPR mesh must originate in SQDMetal/Gmsh/Palace')
    parents = (netlist.source, mode_source, *(r.source for r in mesh_regions))
    if any(parent.revision != active_revision for parent in parents):
        raise StaleRevision()
    if any(r.source != mode_identity.target_mesh for r in mesh_regions):
        raise UnsafeMapping('A11-reviewed physical mode mesh does not match JJ mesh surfaces')
    mesh_sources = {(r.source.artifact_id, r.source.sha256) for r in mesh_regions}
    if len(mesh_sources) != 1:
        raise UnsafeMapping('EPR junction surfaces must share the same revisioned mesh artifact')
    base_hashes = tuple(dict.fromkeys(p.sha256 for p in parents))
    parent_set = set(base_hashes) | {normalization.field_export_sha256}
    if len(parent_set) != len(base_hashes) + 1:
        raise UnsafeMapping('Field export digest must distinguish itself from parent artifacts')
    # The overlap evidence is not an EM solver observable and must not be
    # mistaken for one. Its digest travels with, but never qualifies, output.
    reviewable_hashes = parent_set | set(mode_identity.source_sha256) | set(material_basis.source_sha256)
    source_hashes = tuple(dict.fromkeys((*base_hashes, normalization.field_export_sha256,
                                         *mode_identity.source_sha256, *material_basis.source_sha256)))

    if (not isinstance(element_mappings, tuple) or
            any(not isinstance(m, ElementGeometryMapping) for m in element_mappings) or
            not isinstance(junction_mappings, tuple) or not junction_mappings or
            any(not isinstance(m, JunctionSurfaceMapping) for m in junction_mappings) or
            not isinstance(samples, tuple) or not samples or
            any(not isinstance(s, JunctionEPRSample) for s in samples)):
        raise UnsafeMapping('Typed, complete Josephson element/surface/current declarations are required')
    elems = {e.element_id: e for e in netlist.elements}
    jj_ids = {e.element_id for e in netlist.elements if e.kind == ElementKind.JOSEPHSON_JUNCTION}
    if not jj_ids:
        raise UnsafeMapping('EPR quantization needs at least one declared Josephson element')
    if len(element_mappings) != len(elems) or {m.element_id for m in element_mappings} != set(elems):
        raise UnsafeMapping('Every netlist element requires a geometry declaration')
    geometry = {m.element_id: m for m in element_mappings}
    if len(geometry) != len(element_mappings) or len({m.geometry_id for m in element_mappings}) != len(element_mappings):
        raise UnsafeMapping('Duplicate circuit or physical geometry identifiers')
    for m in element_mappings:
        e = elems[m.element_id]
        if (m.represented_kind, m.positive_node, m.negative_node) != (e.kind, e.positive_node, e.negative_node):
            raise UnsafeMapping('Element geometry kind or signed junction terminals mismatch')

    mapping_ids = [m.element_id for m in junction_mappings]
    j_ids = [m.junction_id for m in junction_mappings]
    if (len(set(mapping_ids)) != len(mapping_ids) or set(mapping_ids) != jj_ids or
            len(set(j_ids)) != len(j_ids) or
            len({m.geometry_id for m in junction_mappings}) != len(junction_mappings) or
            len({m.physical_group for m in junction_mappings}) != len(junction_mappings) or
            len({m.mesh_region_id for m in junction_mappings}) != len(junction_mappings)):
        raise UnsafeMapping('Each circuit Josephson junction requires a unique surface and geometry')
    regions = {r.region_id: r for r in mesh_regions}
    if len(regions) != len(mesh_regions) or len({r.physical_group for r in mesh_regions}) != len(mesh_regions):
        raise UnsafeMapping('Ambiguous or duplicate mesh region / physical group')
    for m in junction_mappings:
        region = regions.get(m.mesh_region_id)
        if (geometry[m.element_id].geometry_id != m.geometry_id or region is None or
                region.role != 'junction' or region.physical_group != m.physical_group):
            raise UnsafeMapping('Unverified JJ geometry to tagged native junction mesh surface')
    # A17 supplies independently reviewed native Gmsh tag membership and
    # spatial constitutive calibration. A material name alone is not proof.
    audited_regions = {r.region_id: r for r in material_basis.regions}
    if set(audited_regions) != set(regions):
        raise UnsafeMapping('A17 material audit does not cover exactly the native EPR mesh regions')
    for region in mesh_regions:
        audited = audited_regions[region.region_id]
        if (audited.physical_group != region.physical_group or
                audited.material_id != region.material_id):
            raise UnsafeMapping('A17 physical tag or material identity mismatches native EPR mesh')

    currents = {s.junction_id: s for s in samples}
    if len(currents) != len(samples) or set(currents) != set(j_ids):
        raise UnsafeMapping('EPR currents and inductances must cover each mapped junction once')
    if any(sample.revision != active_revision for sample in samples):
        raise StaleRevision()
    if any(sample.field_export_sha256 != normalization.field_export_sha256 for sample in samples):
        raise UnsafeMapping('JJ peak currents use an unrelated modal amplitude normalization')
    if (not isinstance(evidence, tuple) or not evidence or
            any(not isinstance(e, EvidenceRecord) for e in evidence)):
        raise MissingEvidence('A12 EPR requires actual separately recorded reviewer declarations')
    if any(e.revision != active_revision for e in evidence):
        raise StaleRevision()
    if len({e.evidence_id for e in evidence}) != len(evidence):
        raise MissingEvidence('Review identity must not be duplicated')
    if mode_identity.review not in evidence:
        raise MissingEvidence('The A11 mode-identity review must be in the EPR review bundle')
    if material_basis.review not in evidence:
        raise MissingEvidence('The A17 native basis/material-tag review must be in the EPR review bundle')
    if any(not set(e.source_artifact_sha256) <= reviewable_hashes for e in evidence):
        raise UnsafeMapping('Review references unrelated or stale EPR data')
    kind_parents = {
        EvidenceKind.MODE_IDENTIFICATION: set(mode_identity.source_sha256),
        EvidenceKind.GEOMETRY_REVIEW: {netlist.source.sha256, next(iter(mesh_sources))[1]},
        EvidenceKind.MATERIAL_AND_BOUNDARY_REVIEW: {next(iter(mesh_sources))[1], normalization.field_export_sha256}
                                                   | set(material_basis.source_sha256),
        EvidenceKind.QUANTIZATION_DERIVATION: parent_set | {mode_identity.native_overlap_report_sha256}
                                                | set(material_basis.source_sha256),
        EvidenceKind.EXTRACTION_VALIDATION: parent_set | {mode_identity.native_overlap_report_sha256}
                                             | set(material_basis.source_sha256),
    }
    for kind in _EPR_REQUIRED_REVIEWS:
        if not any(e.kind == kind and kind_parents[kind] <= set(e.source_artifact_sha256) for e in evidence):
            raise MissingEvidence(f'{kind.value} needs explicit revision-bound review of its source data')
    # The extraction review must cover every junction's actual calibration
    # document, not merely a token generic 'extraction reviewed' assertion.
    for sample in samples:
        if not any(e.kind == EvidenceKind.EXTRACTION_VALIDATION and
                   e.document_sha256 == sample.calibration_review_sha256 and
                   kind_parents[EvidenceKind.EXTRACTION_VALIDATION] <= set(e.source_artifact_sha256)
                   for e in evidence):
            raise MissingEvidence('Each junction current/LJ calibration needs a source-bound extraction review')

    mag, elec = normalization.magnetic_energy.si(), normalization.electric_energy.si()
    if mag.lower.value > elec.upper.value or elec.lower.value > mag.upper.value:
        raise UnsafeMapping('Electric/magnetic cycle-averaged energies disagree outside declared uncertainty')

    with localcontext() as context:
        context.prec = 60
        ej_constant = _PLANCK_J_S / (Decimal(16) * _PI * _PI * _ELEMENTARY_CHARGE_C ** 2)
        fractions = []
        parameters = []
        total_upper = Decimal(0)
        for mapping in junction_mappings:
            sample = currents[mapping.junction_id]
            inductance, current = sample.inductance.si(), sample.peak_current.si()
            # Monotone interval arithmetic for L>=0, I>=0, magnetic energy>0.
            nom = inductance.nominal.value * current.nominal.value ** 2 / (4 * mag.nominal.value)
            lo = inductance.lower.value * current.lower.value ** 2 / (4 * mag.upper.value)
            hi = inductance.upper.value * current.upper.value ** 2 / (4 * mag.lower.value)
            if hi > 1:
                raise UnsafeMapping('Junction participation exceeds magnetic energy within declared bounds')
            total_upper += hi
            fraction = _interval(nom, lo, hi, '1', Dimension.DIMENSIONLESS)
            fractions.append(EPRParticipation(normalization.mode.index, normalization.mode.label,
                                              mapping.junction_id, fraction, active_revision,
                                              source_hashes))
            # Exact SI h/e, numerical pi; reciprocal H interval is asymmetric.
            ej_nom = ej_constant / inductance.nominal.value
            ej_low = ej_constant / inductance.upper.value
            ej_high = ej_constant / inductance.lower.value
            ej_interval = _interval(ej_nom, ej_low, ej_high, 'Hz', Dimension.ENERGY_OVER_H)
            elem = elems[mapping.element_id]
            if not ej_low <= elem.value.si().value <= ej_high:
                raise UnsafeMapping('Schematic JJ EJ/h disagrees with independently declared LJ bounds')
            term = HamiltonianTerm('EJ', ej_interval.nominal, mapping.junction_id,
                                   'reviewed_circuit_quantization',
                                   source_hashes)
            parameters.append(ReviewedHamiltonianParameter(mapping.junction_id, term, ej_interval,
                                                            active_revision))
        if total_upper > 1:
            raise UnsafeMapping('Sum of JJ participation upper bounds exceeds total magnetic energy')
    return ReviewedEPRTransition(normalization, junction_mappings, tuple(fractions),
                                  tuple(parameters), evidence, active_revision, mode_identity,
                                  material_basis)


def assess_em_to_epr(
    *, netlist: CircuitNetlist, normalization: EPRModeNormalization,
    mesh_regions: tuple[MeshRegion, ...],
    element_mappings: tuple[ElementGeometryMapping, ...],
    junction_mappings: tuple[JunctionSurfaceMapping, ...],
    samples: tuple[JunctionEPRSample, ...], evidence: tuple[EvidenceRecord, ...],
    active_revision: RevisionBinding,
    mode_identity: A11ReviewedModeIdentity | None = None,
    material_basis: A17ReviewedMaterialBasis | None = None,
) -> EPRHandoffResult:
    """GUI-relevant, fail-closed EPR status; BLOCKED has zero usable terms.

    Unlike the strict arithmetic function, this wraps known review/physical
    input problems into an immutable typed decision. Unexpected programming
    errors are not swallowed; they must fail the test instead of being masked.
    """
    if not isinstance(active_revision, RevisionBinding):
        raise UnsafeMapping('A typed active revision is required for an EPR decision')
    if not isinstance(mode_identity, A11ReviewedModeIdentity):
        return EPRHandoffResult(
            active_revision, 'BLOCKED_A11_MODE_IDENTITY',
            'EM to EPR/Hamiltonian unavailable: A11 has not delivered a reviewed, '
            'SHA-bound native complex H(curl) mode match. Diagnostic VTK overlap, '
            'frequency proximity and solver indices do not qualify a physical mode.',
        )
    if not isinstance(material_basis, A17ReviewedMaterialBasis):
        return EPRHandoffResult(
            active_revision, 'BLOCKED_A17_MATERIAL_BASIS',
            'EM to EPR/Hamiltonian unavailable: A17 native H(curl) edge basis, '
            'Gmsh physical tags, reviewed epsilon/mu and B-to-H constitutive '
            'calibration are missing. VTK arrays or material names are not proof.',
        )
    try:
        transition = em_to_reviewed_epr(
            netlist=netlist, normalization=normalization, mesh_regions=mesh_regions,
            element_mappings=element_mappings, junction_mappings=junction_mappings,
            samples=samples, evidence=evidence, active_revision=active_revision,
            mode_identity=mode_identity, material_basis=material_basis,
        )
    except StaleRevision as exc:
        return EPRHandoffResult(active_revision, 'BLOCKED_STALE_REVISION', str(exc))
    except (InteropBlocked, InteropValidationError) as exc:
        return EPRHandoffResult(active_revision, 'BLOCKED_EPR_REVIEW_OR_UNITS', str(exc))
    return EPRHandoffResult(
        active_revision, transition.status,
        'Bounded JJ participation and EJ/h numerical proposal only. Native EPR, '
        'source-hash authentication, calibration, scientific validation and '
        'fabrication signoff remain BLOCKED.', transition,
    )


# RC14.10 benchmark-facing contracts. No file I/O, trust escalation, solver
# invocation, or automated transfer of proposals to an active Hamiltonian.
from .models import (
    CapacitanceECReviewInput, ECScreeningResult, NativeEPRBenchmarkInput,
    NativeEPRComparison, IndependentScqubitsParameters, ScqubitsParameterScreen,
)


def screen_capacitance_ec(reviewed: CapacitanceECReviewInput) -> ECScreeningResult:
    """B04 reviewed *grounded-all-other-conductors* Maxwell Cii -> EC/h.

    C_sigma = C_ii only under the explicitly reviewed constant-potential
    boundary assumptions. Check native Maxwell symmetry, conservation and
    diagonal dominance and anchored positive electrostatic energy in SI F. Never reinterpret
    mutual matrices, infer floating electrodes or construct active EC terms.
    """
    if not isinstance(reviewed, CapacitanceECReviewInput):
        raise MissingEvidence('B04 native electrostatic conductor review is required')
    matrix = reviewed.matrix
    order = matrix.conductors
    n = len(order)
    with localcontext() as ctx:
        ctx.prec = 60
        vals = tuple(tuple(v.si().value for v in row) for row in matrix.values)
        sym_tol = reviewed.symmetry_tolerance.si().value
        balance_tol = reviewed.charge_balance_tolerance.si().value
        for i in range(n):
            if abs(sum(vals[i], Decimal(0))) > balance_tol:
                raise UnsafeMapping('B04 incomplete conductor closure or Maxwell row-charge balance')
            if vals[i][i] + balance_tol < sum((-vals[i][j] for j in range(n) if j != i), Decimal(0)):
                raise UnsafeMapping('B04 Maxwell matrix fails diagonal dominance/charge closure')
            for j in range(i + 1, n):
                if abs(vals[i][j] - vals[j][i]) > sym_tol:
                    raise UnsafeMapping('B04 native reciprocity/symmetry residual exceeds declared tolerance')
        # C_ii alone can be positive even for an indefinite electrostatic
        # matrix. With all conductors included and row closure checked, the
        # global common-potential mode is a gauge zero. Fix the explicit
        # return conductor and require a strictly positive anchored quadratic
        # energy for every nonzero independent potential (symmetric LDL^T).
        # Antisymmetric solver roundoff is symmetrized only after reciprocity
        # is checked above; negative pivots are NEVER clipped to zero.
        anchor = order.index(reviewed.return_conductor)
        other = [i for i in range(n) if i != anchor]
        schur = [[(vals[i][j] + vals[j][i]) / 2 for j in other] for i in other]
        for k in range(len(other)):
            pivot = schur[k][k]
            if pivot <= 0:
                raise UnsafeMapping('B04 electrostatic energy is nonpositive or has a floating disconnected conductor')
            for i in range(k + 1, len(other)):
                for j in range(i, len(other)):
                    reduced = schur[j][i] - schur[i][k] * schur[j][k] / pivot
                    schur[j][i] = reduced
                    schur[i][j] = reduced
        idx = order.index(reviewed.island_conductor)
        c = reviewed.island_capacitance.si()
        if c.nominal.value != vals[idx][idx]:
            raise UnsafeMapping('B04 reviewed island Csum does not equal native Maxwell C_ii')
        # No selected-excitation reduction without a separately qualified model.
        ec_factor = _ELEMENTARY_CHARGE_C ** 2 / (Decimal(2) * _PLANCK_J_S)
        ec = _interval(ec_factor / c.nominal.value,
                       ec_factor / c.upper.value, ec_factor / c.lower.value,
                       'Hz', Dimension.ENERGY_OVER_H)
        parents = (matrix.source.sha256, reviewed.matrix_export_sha256,
                   reviewed.extraction_review.document_sha256,
                   reviewed.quantization_review.document_sha256)
    return ECScreeningResult(reviewed.revision, reviewed.island_conductor,
                             c, ec, parents)


def compare_native_epr(benchmark: NativeEPRBenchmarkInput) -> NativeEPRComparison:
    """B06 cross-check independently reported EPR magnitudes and signed JJ frame.

    A signed JJ current direction is explicit, not derived from the positive
    magnetic participation. Native report bytes/authorship remain externally
    unverified; a numerical agreement is NOT solver/scientific qualification.
    """
    if not isinstance(benchmark, NativeEPRBenchmarkInput):
        raise MissingEvidence('B06 needs independently reviewed native EPR report')
    transition = benchmark.transition
    by_element = {m.element_id: m for m in benchmark.element_mappings}
    by_mapping = {m.junction_id: m for m in transition.mappings}
    by_participation = {p.junction_id: p for p in transition.participations}
    by_sample = {s.junction_id: s for s in benchmark.samples}
    if (len(by_element) != len(benchmark.element_mappings) or
            {m.element_id for m in transition.mappings} - set(by_element)):
        raise UnsafeMapping('B06 signed terminal map is incomplete or ambiguous')
    residuals = []
    with localcontext() as ctx:
        ctx.prec = 60
        native_energy = benchmark.native_magnetic_energy.si()
        reviewed_energy = transition.normalization.magnetic_energy.si()
        if (native_energy.lower.value > reviewed_energy.upper.value or
                reviewed_energy.lower.value > native_energy.upper.value):
            raise UnsafeMapping('B06 independent native/reviewed magnetic energies have disjoint bounds')
        # Native reference participations are simultaneously bounded energy
        # fractions of ONE mode, not independent measurements whose sum may
        # exceed total stored magnetic energy. Uncertainty is worst-case.
        if sum((r.energy_fraction.si().upper.value for r in benchmark.references), Decimal(0)) > 1:
            raise UnsafeMapping('B06 native junction participation upper bounds exceed magnetic energy')
    for native in benchmark.references:
        mapping = by_mapping[native.junction_id]
        terminals = by_element[mapping.element_id]
        if terminals.represented_kind != ElementKind.JOSEPHSON_JUNCTION or terminals.geometry_id != mapping.geometry_id:
            raise UnsafeMapping('B06 native JJ terminal geometry mismatches circuit map')
        same = (native.positive_node, native.negative_node) == (terminals.positive_node, terminals.negative_node)
        reverse = (native.positive_node, native.negative_node) == (terminals.negative_node, terminals.positive_node)
        if not ((same and native.current_orientation == 1) or (reverse and native.current_orientation == -1)):
            raise UnsafeMapping('B06 signed JJ current direction is inconsistent with mapped terminals')
        if (native.mode_index != transition.normalization.mode.index or
                native.physical_mode_id != transition.mode_identity.physical_mode_id):
            raise UnsafeMapping('B06 native source does not match reviewed physical mode identity')
        declared_current = by_sample[native.junction_id].peak_current.si()
        actual_current = native.peak_current.si()
        if actual_current.upper.value < declared_current.lower.value or declared_current.upper.value < actual_current.lower.value:
            raise UnsafeMapping('B06 native current amplitude normalization disagrees with EPR sample')
        numeric = by_participation[native.junction_id].fraction.si()
        direct = native.energy_fraction.si()
        with localcontext() as ctx:
            ctx.prec = 60
            # Independent check from native report amplitude/energy and the
            # separately reviewed per-JJ LJ interval, using peak-phasor I.
            # p_j = LJ |I_peak|^2 / (4 <U_magnetic>) with worst-case bounds.
            native_energy = benchmark.native_magnetic_energy.si()
            lj = by_sample[native.junction_id].inductance.si()
            calculated_lo = (lj.lower.value * actual_current.lower.value ** 2 /
                             (4 * native_energy.upper.value))
            calculated_hi = (lj.upper.value * actual_current.upper.value ** 2 /
                             (4 * native_energy.lower.value))
            if (direct.lower.value > calculated_hi or direct.upper.value < calculated_lo):
                raise UnsafeMapping('B06 native EPR is incompatible with independently normalized JJ magnetic energy')
            if calculated_hi > 1:
                raise UnsafeMapping('B06 native JJ energy uncertainty exceeds total magnetic energy')
            residual = abs(numeric.nominal.value - direct.nominal.value)
        # Bounds may represent numerical uncertainty; if their separation is
        # greater than an expert-allowed absolute tolerance, stop the transfer.
        separation = max(Decimal(0), direct.lower.value - numeric.upper.value,
                         numeric.lower.value - direct.upper.value)
        if separation > benchmark.absolute_tolerance.si().value:
            raise UnsafeMapping('B06 native EPR fraction disagrees beyond reviewed absolute tolerance')
        residuals.append((native.junction_id, Quantity(residual, '1', Dimension.DIMENSIONLESS)))
    parents = (benchmark.native_epr_report_sha256,
               benchmark.native_energy_export_sha256,
               benchmark.native_extraction_review.document_sha256,
               benchmark.field_export_sha256,
               *transition.mode_identity.source_sha256,
               *transition.material_basis.source_sha256)
    return NativeEPRComparison(benchmark.revision, tuple(residuals), tuple(dict.fromkeys(parents)))


def screen_independent_scqubits_parameters(parameters: IndependentScqubitsParameters) -> ScqubitsParameterScreen:
    """B08 strict independently reviewed input screen; does not run scqubits."""
    if not isinstance(parameters, IndependentScqubitsParameters):
        raise MissingEvidence('B08 requires independent reviewed EJ/EC/EL rather than EPR proposal')
    return ScqubitsParameterScreen(parameters)
