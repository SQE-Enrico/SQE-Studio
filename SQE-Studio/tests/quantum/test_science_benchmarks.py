"""RC14.10 B04/B06/B08 *synthetic contract* checks only.

No solver exports, native scqubits, reviewer authentication or calibrated
quantum spectra are used. Every SHA below labels invented fixture declarations.
"""
from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from test_em_epr_review import REV, OTHER, art, case, q, interval
from sqe_studio.interop.models import (
    ArtifactRef, CapacitanceMatrix, CapacitanceECReviewInput, ECScreeningResult,
    EvidenceKind, EvidenceRecord, IndependentScqubitsParameters,
    NativeEPRBenchmarkInput, NativeEPRReference, NativeEPRComparison,
    ScqubitsParameterScreen,
)
from sqe_studio.interop.preflight import MissingEvidence, UnsafeMapping
from sqe_studio.interop.quantities import Dimension, InteropValidationError
from sqe_studio.interop.transformations import (
    screen_capacitance_ec, compare_native_epr, screen_independent_scqubits_parameters,
)


def cap_case():
    source = art('NativeC', 'palace.capacitance_matrix', 'b', 'sqdmetal_palace')
    values = (
        (q(120, 'fF', Dimension.CAPACITANCE), q(-100, 'fF', Dimension.CAPACITANCE), q(-20, 'fF', Dimension.CAPACITANCE)),
        (q(-100, 'fF', Dimension.CAPACITANCE), q(150, 'fF', Dimension.CAPACITANCE), q(-50, 'fF', Dimension.CAPACITANCE)),
        (q(-20, 'fF', Dimension.CAPACITANCE), q(-50, 'fF', Dimension.CAPACITANCE), q(70, 'fF', Dimension.CAPACITANCE)),
    )
    matrix = CapacitanceMatrix(('Island', 'Return', 'Guard'), values, 'maxwell', source)
    parents = (source.sha256, 'c'*64)
    extraction = EvidenceRecord('NativeCReview', EvidenceKind.EXTRACTION_VALIDATION, 'd'*64,
                                'ExpertElectrostatic', REV, parents)
    quantization = EvidenceRecord('ECReview', EvidenceKind.QUANTIZATION_DERIVATION, 'e'*64,
                                  'ExpertQuantum', REV, parents)
    return CapacitanceECReviewInput(
        matrix, REV, 'Island', 'Return', ('Return', 'Guard'), 'c'*64,
        interval(120, 115, 125, 'fF', Dimension.CAPACITANCE),
        q('0.01', 'fF', Dimension.CAPACITANCE),
        q('0.01', 'fF', Dimension.CAPACITANCE), extraction, quantization,
    )


def native_case():
    inp = case()
    transition = __import__('sqe_studio.interop.transformations', fromlist=['em_to_reviewed_epr']).em_to_reviewed_epr(**inp)
    native = NativeEPRReference('JunctionOne', 1, 'PhysicalModeAlpha',
                                'signal', 'return', 1,
                                interval('10', '9.5', '10.5', 'uA', Dimension.CURRENT),
                                interval('.25', '.24', '.26', '1', Dimension.DIMENSIONLESS), REV)
    hashes = {'c'*64, 'f'*64, inp['normalization'].field_export_sha256,
              *transition.mode_identity.source_sha256,
              *transition.material_basis.source_sha256}
    review = EvidenceRecord('NativeEPRReview', EvidenceKind.EXTRACTION_VALIDATION,
                            'd'*64, 'ExpertNativeEPR', REV, tuple(sorted(hashes)))
    return NativeEPRBenchmarkInput(transition, inp['element_mappings'], inp['samples'],
                                   (native,), 'c'*64, inp['normalization'].field_export_sha256,
                                   q('.01', '1', Dimension.DIMENSIONLESS), review, REV,
                                   inp['normalization'].magnetic_energy, 'f'*64)


def independent_scqubits_case(model='transmon'):
    source = art('IndependentParams', 'measurement.dataset', 'b', 'external')
    review = EvidenceRecord('IndependentQuantReview', EvidenceKind.QUANTIZATION_DERIVATION,
                            'c'*64, 'CircuitExpert', REV, (source.sha256,))
    return IndependentScqubitsParameters(
        model, q(15, 'GHz', Dimension.ENERGY_OVER_H), q('.25', 'GHz', Dimension.ENERGY_OVER_H),
        q('1.0', 'GHz', Dimension.ENERGY_OVER_H) if model == 'fluxonium' else None,
        q('.35', '1', Dimension.DIMENSIONLESS) if model == 'fluxonium' else None,
        None if model == 'fluxonium' else q('0', '1', Dimension.DIMENSIONLESS),
        50, 10, source, review,
    )


def test_b04_exact_si_ec_reciprocal_bounds_and_blocked_status():
    result = screen_capacitance_ec(cap_case())
    assert isinstance(result, ECScreeningResult)
    assert result.effective_capacitance.si().nominal.value == Decimal('1.20e-13')
    with localcontext() as ctx:
        ctx.prec = 60
        independent_ec = Decimal('1.602176634e-19') ** 2 / (2 * Decimal('6.62607015e-34') * Decimal('120e-15'))
    assert result.ec_over_h.nominal.si().value == independent_ec
    assert result.ec_over_h.lower.value < result.ec_over_h.nominal.value < result.ec_over_h.upper.value
    assert len(result.parent_sha256) == 4 and result.revision == REV
    assert result.status.endswith('QUALIFICATION_BLOCKED')
    with pytest.raises(InteropValidationError, match='cannot promote'):
        replace(result, status='PASS')


def test_b04_exact_maxwell_symmetry_and_charge_balance():
    base = cap_case()
    assert screen_capacitance_ec(base).island_conductor == 'Island'
    vals = list(map(list, base.matrix.values))
    vals[1][0] = q(-99, 'fF', Dimension.CAPACITANCE)
    with pytest.raises(UnsafeMapping, match='row-charge balance|reciprocity'):
        screen_capacitance_ec(replace(base, matrix=replace(base.matrix, values=tuple(tuple(row) for row in vals))))
    vals = list(map(list, base.matrix.values))
    vals[2][2] = q(71, 'fF', Dimension.CAPACITANCE)
    with pytest.raises(UnsafeMapping, match='row-charge balance'):
        screen_capacitance_ec(replace(base, matrix=replace(base.matrix, values=tuple(tuple(row) for row in vals))))


def test_b04_disconnected_maxwell_components_are_energy_degenerate_and_blocked():
    """All rows can balance while a disconnected conductor group floats."""
    base = cap_case()
    qf = lambda value: q(value, 'fF', Dimension.CAPACITANCE)
    matrix = CapacitanceMatrix(
        ('Island', 'Return', 'Guard', 'Unused'),
        ((qf(100), qf(-100), qf(0), qf(0)),
         (qf(-100), qf(100), qf(0), qf(0)),
         (qf(0), qf(0), qf(50), qf(-50)),
         (qf(0), qf(0), qf(-50), qf(50))), 'maxwell', base.matrix.source,
    )
    changed = replace(base, matrix=matrix, grounded_conductors=('Return', 'Guard', 'Unused'),
                      island_capacitance=interval(100, 99, 101, 'fF', Dimension.CAPACITANCE))
    with pytest.raises(UnsafeMapping, match='floating disconnected conductor|nonpositive'):
        screen_capacitance_ec(changed)


@pytest.mark.parametrize('change', [
    lambda b: replace(b, grounded_conductors=('Return',)),
    lambda b: replace(b, island_conductor='Return'),
    lambda b: replace(b, return_conductor='Island'),
    lambda b: replace(b, matrix_export_sha256='b'*64),
    lambda b: replace(b, matrix=replace(b.matrix, convention='mutual')),
    lambda b: replace(b, matrix=replace(b.matrix, source=replace(b.matrix.source, revision=OTHER))),
    lambda b: replace(b, island_capacitance=interval(119, 115, 125, 'fF', Dimension.CAPACITANCE)),
    lambda b: replace(b, island_capacitance=interval(120, -1, 125, 'fF', Dimension.CAPACITANCE)),
    lambda b: replace(b, extraction_review=replace(b.extraction_review, revision=OTHER)),
    lambda b: replace(b, quantization_review=replace(b.quantization_review, document_sha256='d'*64)),
    lambda b: replace(b, symmetry_tolerance=q(1, 'nH', Dimension.INDUCTANCE)),
    lambda b: replace(b, charge_balance_tolerance=q(100, 'fF', Dimension.CAPACITANCE)),
    lambda b: replace(b, grounded_conductors=('Return', 'Return')),
])
def test_b04_negative_unreviewed_capacitance_or_boundary_fail_closed(change):
    with pytest.raises((InteropValidationError, UnsafeMapping)):
        screen_capacitance_ec(change(cap_case()))


def test_b04_rejects_legacy_or_missing_object_and_fabricated_value():
    with pytest.raises(MissingEvidence):
        screen_capacitance_ec(None)
    with pytest.raises(UnsafeMapping, match='Csum'):
        screen_capacitance_ec(replace(cap_case(), island_capacitance=interval(100, 95, 105, 'fF', Dimension.CAPACITANCE)))


def test_b06_native_signed_oriented_review_and_numerical_only_result():
    inp = native_case()
    out = compare_native_epr(inp)
    assert isinstance(out, NativeEPRComparison)
    assert out.absolute_residuals[0][1].value == 0
    assert out.revision == REV and out.status.endswith('QUALIFICATION_BLOCKED')
    with pytest.raises(InteropValidationError):
        replace(out, status='PASS')
    # Signed orientation may be reversed only with reversed *actual* terminals.
    native = replace(inp.references[0], positive_node='return', negative_node='signal', current_orientation=-1)
    assert compare_native_epr(replace(inp, references=(native,))).absolute_residuals[0][1].value == 0


def test_b06_native_energy_must_be_independently_reported_and_source_complete():
    base = native_case()
    assert base.native_magnetic_energy.si().nominal.value == Decimal('1e-18')
    assert base.native_energy_export_sha256 in compare_native_epr(base).parent_sha256
    with pytest.raises(InteropValidationError, match='native magnetic-energy'):
        replace(base, native_magnetic_energy=None)
    with pytest.raises(InteropValidationError, match='energy/EPR/field exports'):
        replace(base, native_energy_export_sha256=base.field_export_sha256)
    with pytest.raises(InteropValidationError, match='energy/EPR exports'):
        replace(base, native_extraction_review=replace(
            base.native_extraction_review,
            source_artifact_sha256=tuple(x for x in base.native_extraction_review.source_artifact_sha256
                                         if x != base.native_energy_export_sha256)))
    with pytest.raises(InteropValidationError, match='phasor conventions'):
        replace(base, native_current_convention='rms_amperes')
    with pytest.raises(InteropValidationError, match='native-energy benchmark'):
        replace(base, schema_version='sqe.native-epr-benchmark.a12.v1')


def test_b06_independent_magnetic_energy_and_jj_current_normalization_fail_closed():
    base = native_case()
    with pytest.raises(UnsafeMapping, match='magnetic energies'):
        compare_native_epr(replace(base, native_magnetic_energy=interval(3, '2.9', '3.1', 'aJ', Dimension.ENERGY)))
    # Current magnitudes overlap with the reviewed sample; but its implied
    # native L*I^2 / (4U) does NOT agree with the claimed native participation.
    # A simple native-vs-review participation comparison would miss this.
    wrong = replace(base.references[0], energy_fraction=interval('.19', '.18', '.20', '1', Dimension.DIMENSIONLESS))
    with pytest.raises(UnsafeMapping, match='independently normalized'):
        compare_native_epr(replace(base, references=(wrong,)))


def test_b06_multiple_native_junctions_cannot_exceed_one_mode_energy():
    """Hard upper-bound conservation check applies across every native junction."""
    base = native_case()
    from sqe_studio.interop.models import JunctionSurfaceMapping, EPRParticipation
    original_map = base.transition.mappings[0]
    original_fraction = base.transition.participations[0]
    other_map = replace(original_map, junction_id='JunctionTwo', element_id='J2', geometry_id='GeoTwo',
                        mesh_region_id='MeshTwo', physical_group=17)
    other_fraction = replace(original_fraction, junction_id='JunctionTwo')
    other_current = replace(base.samples[0], junction_id='JunctionTwo')
    other_ref = replace(base.references[0], junction_id='JunctionTwo', energy_fraction=interval('.8', '.79', '.81', '1', Dimension.DIMENSIONLESS))
    other_geom = replace(base.element_mappings[0], element_id='J2', geometry_id='GeoTwo')
    # This is a deliberately forged transition, to prove a gate catches it
    # BEFORE it can propagate; a correctly validated transition may have only
    # physically admissible fractions of course.
    forged = replace(base.transition, mappings=(original_map, other_map),
                     participations=(original_fraction, other_fraction),
                     ej_parameters=(base.transition.ej_parameters[0],
                                    replace(base.transition.ej_parameters[0], junction_id='JunctionTwo',
                                            term=replace(base.transition.ej_parameters[0].term, model='JunctionTwo'))))
    with pytest.raises(UnsafeMapping, match='upper bounds exceed magnetic energy'):
        compare_native_epr(replace(base, transition=forged,
            references=(base.references[0], other_ref), samples=(base.samples[0], other_current),
            element_mappings=(base.element_mappings[0], other_geom)))


@pytest.mark.parametrize('change', [
    lambda b: replace(b, references=()),
    lambda b: replace(b, references=(replace(b.references[0], revision=OTHER),)),
    lambda b: replace(b, references=(replace(b.references[0], mode_index=2),)),
    lambda b: replace(b, references=(replace(b.references[0], physical_mode_id='DifferentMode'),)),
    lambda b: replace(b, references=(replace(b.references[0], current_orientation=-1),)),
    lambda b: replace(b, references=(replace(b.references[0], positive_node='other'),)),
    lambda b: replace(b, references=(replace(b.references[0], peak_current=interval(4, 3, 5, 'uA', Dimension.CURRENT)),)),
    lambda b: replace(b, references=(replace(b.references[0], energy_fraction=interval('.80', '.79', '.81', '1', Dimension.DIMENSIONLESS)),)),
    lambda b: replace(b, native_epr_report_sha256=b.transition.mode_identity.target_mesh.sha256),
    lambda b: replace(b, field_export_sha256='f'*64),
    lambda b: replace(b, native_extraction_review=replace(b.native_extraction_review, revision=OTHER)),
    lambda b: replace(b, absolute_tolerance=q('1', '1', Dimension.DIMENSIONLESS)),
])
def test_b06_invalid_native_source_or_mode_or_sign_is_blocked(change):
    with pytest.raises((InteropValidationError, UnsafeMapping)):
        compare_native_epr(change(native_case()))


def test_b06_missing_native_report_no_autopromotion():
    with pytest.raises(MissingEvidence):
        compare_native_epr(None)
    with pytest.raises(InteropValidationError, match='energy fraction'):
        replace(native_case().references[0], energy_fraction=interval(1, 0, '1.1', '1', Dimension.DIMENSIONLESS))


@pytest.mark.parametrize('model', ['transmon', 'fluxonium'])
def test_b08_scqubits_independent_parameter_schema_only(model):
    inp = independent_scqubits_case(model)
    result = screen_independent_scqubits_parameters(inp)
    assert isinstance(result, ScqubitsParameterScreen)
    assert result.status.endswith('QUALIFICATION_BLOCKED')
    assert result.parameters.ej_over_h.dimension == Dimension.ENERGY_OVER_H
    if model == 'transmon':
        assert screen_independent_scqubits_parameters(replace(inp, truncated_dim=101)).parameters.truncated_dim == 101
    with pytest.raises(InteropValidationError):
        replace(result, status='NATIVE_PASS')


@pytest.mark.parametrize('change', [
    lambda p: replace(p, ej_over_h=q(6, 'GHz', Dimension.FREQUENCY)),
    lambda p: replace(p, ec_over_h=q(0, 'GHz', Dimension.ENERGY_OVER_H)),
    lambda p: replace(p, ec_over_h=q(-1, 'GHz', Dimension.ENERGY_OVER_H)),
    lambda p: replace(p, basis_cutoff=True),
    lambda p: replace(p, truncated_dim=102),
    lambda p: replace(p, source=art('SourceMode', 'palace.eigenmodes', 'b', 'sqdmetal_palace')),
    lambda p: replace(p, independent_review=replace(p.independent_review, revision=OTHER)),
    lambda p: replace(p, el_over_h=q(1, 'GHz', Dimension.ENERGY_OVER_H)),
    lambda p: replace(p, offset_charge=None),
])
def test_b08_independent_transmon_rejects_units_bounds_em_or_missing_review(change):
    with pytest.raises(InteropValidationError):
        change(independent_scqubits_case())


@pytest.mark.parametrize('change', [
    lambda p: replace(p, el_over_h=None),
    lambda p: replace(p, external_flux_phi0=q('.5', 'GHz', Dimension.FREQUENCY)),
    lambda p: replace(p, offset_charge=q('.2', '1', Dimension.DIMENSIONLESS)),
])
def test_b08_fluxonium_requires_explicit_flux_el_and_no_ng(change):
    with pytest.raises(InteropValidationError):
        change(independent_scqubits_case('fluxonium'))


def test_b08_cannot_screen_epr_output_as_native_spectrum_or_independent_parameters():
    from sqe_studio.interop.transformations import em_to_reviewed_epr
    with pytest.raises(MissingEvidence):
        screen_independent_scqubits_parameters(em_to_reviewed_epr(**case()))
    with pytest.raises(MissingEvidence):
        screen_independent_scqubits_parameters(None)
