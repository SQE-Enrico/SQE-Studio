"""Pure numerical/unit regression; NO claimed Palace export or native qualification.

Fixtures are deliberately constructed declared inputs and hashed fake fixture
identities, not actual solver outputs. The reviewed transition never qualifies
these fixtures as genuine scientific evidence.
"""
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

import pytest

from sqe_studio.interop.models import (
    A11ReviewedModeIdentity, A17ReviewedMaterialBasis, A17TaggedMaterialRegion, ArtifactRef, CircuitElement, CircuitNetlist, CircuitPort, ElementGeometryMapping,
    ElementKind, EMMode, EPRModeNormalization, EvidenceKind, EvidenceRecord,
    JunctionEPRSample, JunctionSurfaceMapping, MeshRegion, RevisionBinding,
    canonical_json, content_digest,
)
from sqe_studio.interop.preflight import MissingEvidence, StaleRevision, UnsafeMapping
from sqe_studio.interop.quantities import Dimension, InteropValidationError, Quantity, QuantityInterval
from sqe_studio.interop.transformations import assess_em_to_epr, em_to_reviewed_epr


REV = RevisionBinding(str(UUID('c738d5d1-f44e-47aa-959a-5d2e1de3f76a')),
                      str(UUID('ef3d633b-5fa7-469c-b1b9-c33cfb915017')), 'f'*64)
OTHER = RevisionBinding(REV.project_id, str(UUID('02efcbd0-ce4b-45bb-8bb4-4d1e824cb345')), 'e'*64)


def q(value, unit, dim):
    return Quantity(str(value), unit, dim)


def interval(n, lo, hi, unit, dim):
    return QuantityInterval(q(n, unit, dim), q(lo, unit, dim), q(hi, unit, dim))


def art(name, kind, sha, engine, rev=REV):
    return ArtifactRef(name, kind, sha*64, rev, engine, 'fixture-not-native-v1')


def case():
    net_art = art('Net', 'circuit.netlist', '1', 'external')
    em_art = art('Modes', 'palace.eigenmodes', '2', 'sqdmetal_palace')
    mesh_art = art('Mesh', 'gmsh.mesh', '3', 'sqdmetal_palace')
    export_hash = '4'*64
    netlist = CircuitNetlist(
        ('signal', 'return'),
        (CircuitElement('J1', ElementKind.JOSEPHSON_JUNCTION, 'signal', 'return',
                        q('16.3', 'GHz', Dimension.ENERGY_OVER_H)),),
        (CircuitPort(1, 'signal', 'return'),), net_art,
    )
    norm = EPRModeNormalization(
        EMMode(1, q(6, 'GHz', Dimension.FREQUENCY), em_art, 'ModeInThisArtifact'),
        interval(1, '0.95', '1.05', 'aJ', Dimension.ENERGY),
        interval(1, '0.98', '1.02', 'aJ', Dimension.ENERGY),
        export_hash, 'NativeCoordinates',
    )
    mesh_regions = (MeshRegion('JSurface', 7, 'Aluminum', 'junction', mesh_art),)
    maps = (JunctionSurfaceMapping('JunctionOne', 'J1', 'JGeometry', 'JSurface', 7),)
    geometry = (ElementGeometryMapping('J1', 'QubitCell', 'JGeometry', 'signal', 'return',
                                       ElementKind.JOSEPHSON_JUNCTION),)
    samples = (JunctionEPRSample('JunctionOne',
                                 interval(10, '9.5', '10.5', 'nH', Dimension.INDUCTANCE),
                                 interval(10, '9.5', '10.5', 'uA', Dimension.CURRENT),
                                 REV, export_hash, 'a'*64),)
    # These independent-mode artifacts are synthetic contract fixtures, never
    # A11-native H(curl) evidence. Production has no accepted A11 attestation.
    reference_mode = EMMode(2, q('6.1', 'GHz', Dimension.FREQUENCY),
                            art('ReferenceModes', 'palace.eigenmodes', '5', 'sqdmetal_palace'),
                            'IndependentNativeMode')
    reference_mesh = art('ReferenceMesh', 'gmsh.mesh', '6', 'sqdmetal_palace')
    identity_sources = (em_art.sha256, reference_mode.source.sha256, mesh_art.sha256,
                        reference_mesh.sha256, export_hash, '7'*64, '8'*64)
    identity_review = EvidenceRecord('ReviewModeIdentity', EvidenceKind.MODE_IDENTIFICATION,
                                     '9'*64, 'ExpertOne', REV, identity_sources)
    identity = A11ReviewedModeIdentity(
        norm.mode, reference_mode, mesh_art, reference_mesh, export_hash, '7'*64, '8'*64,
        'PhysicalModeAlpha', 'NativeCoordinates',
        interval('0.95', '0.90', '0.98', '1', Dimension.DIMENSIONLESS),
        q('0.85', '1', Dimension.DIMENSIONLESS), identity_review,
    )
    # A17 declarations are synthetic, separately sourced, and never accepted
    # as real mesh, B->H conversion, verified material or foundry evidence.
    a17_hashes = tuple(sha256(('synthetic-a17-%d' % n).encode()).hexdigest() for n in range(8))
    region_material = A17TaggedMaterialRegion(
        'JSurface', 7, 'Aluminum',
        interval('10', '9', '11', '1', Dimension.DIMENSIONLESS),
        interval('1.26', '1.20', '1.32', 'uH/m', Dimension.PERMEABILITY),
        a17_hashes[7],
    )
    material_source_hashes = (mesh_art.sha256, reference_mesh.sha256, *a17_hashes)
    material_review = EvidenceRecord('ReviewA17Basis', EvidenceKind.MATERIAL_AND_BOUNDARY_REVIEW,
                                     sha256(b'synthetic-a17-review-document').hexdigest(),
                                     'ExpertTwo', REV, material_source_hashes)
    material_basis = A17ReviewedMaterialBasis(
        mesh_art, reference_mesh, *a17_hashes[:7], 'NativeCoordinates',
        (region_material,), material_review,
    )
    all_digests = (net_art.sha256, em_art.sha256, mesh_art.sha256, export_hash)
    evidence = (identity_review, material_review, *tuple(
        EvidenceRecord('Review' + k.name, k, 'a'*64, 'ExpertOne', REV,
                       tuple(dict.fromkeys(all_digests + (('8'*64,) if k in (
                           EvidenceKind.QUANTIZATION_DERIVATION,
                           EvidenceKind.EXTRACTION_VALIDATION) else ()) +
                       (material_basis.source_sha256 if k in (
                           EvidenceKind.MATERIAL_AND_BOUNDARY_REVIEW,
                           EvidenceKind.QUANTIZATION_DERIVATION,
                           EvidenceKind.EXTRACTION_VALIDATION) else ()))))
        for k in (EvidenceKind.GEOMETRY_REVIEW, EvidenceKind.MATERIAL_AND_BOUNDARY_REVIEW,
                  EvidenceKind.QUANTIZATION_DERIVATION, EvidenceKind.EXTRACTION_VALIDATION)))
    return dict(netlist=netlist, normalization=norm, mesh_regions=mesh_regions,
                element_mappings=geometry, junction_mappings=maps, samples=samples,
                evidence=evidence, active_revision=REV, mode_identity=identity,
                material_basis=material_basis)


def test_peak_phasor_magnetic_energy_and_ej_over_h_checked_si():
    output = em_to_reviewed_epr(**case())
    p = output.participations[0]
    assert p.mode_index == 1 and p.junction_id == 'JunctionOne'
    assert p.fraction.nominal.value == Decimal('0.25')
    assert abs(p.fraction.lower.value - Decimal('0.2041369047619047619')) < Decimal('1e-18')
    assert Decimal('0.30') < p.fraction.upper.value < Decimal('0.31')
    ej = output.ej_parameters[0]
    assert ej.term.parameter == 'EJ' and ej.term.method == 'reviewed_circuit_quantization'
    # Independent physical-scale check: 10 nH corresponds to EJ/h ~=16.345 GHz.
    assert abs(ej.interval.nominal.as_unit('GHz').value - Decimal('16.346')) < Decimal('0.03')
    assert ej.interval.lower.value < ej.interval.nominal.value < ej.interval.upper.value
    assert ej.revision == REV
    assert ej.interval.nominal.as_unit('GHz').as_unit('Hz') == ej.interval.nominal
    assert set(output.material_basis.source_sha256) <= set(ej.term.source_artifact_sha256)
    assert set(output.mode_identity.source_sha256) <= set(ej.term.source_artifact_sha256)
    assert 'QUALIFICATION_BLOCKED' in output.status
    assert content_digest(output) == content_digest(output)
    assert 'sqe.em-epr-hamiltonian.a12.v3' in canonical_json(output)


def test_si_prefix_rescaling_and_higher_mode_label_does_not_infer_identity():
    values = case()
    s = values['samples'][0]
    n = values['normalization']
    values['samples'] = (replace(s, inductance=s.inductance.as_unit('H'),
                                 peak_current=s.peak_current.as_unit('A')),)
    values['normalization'] = replace(n, magnetic_energy=n.magnetic_energy.as_unit('J'),
                                      electric_energy=n.electric_energy.as_unit('J'))
    p = em_to_reviewed_epr(**values).participations[0]
    assert p.fraction.nominal.value == Decimal('0.25')
    # Mode ordinal is only a label of THIS artifact, not cross-run field overlap.
    values['normalization'] = replace(values['normalization'],
        mode=EMMode(2, q(9, 'GHz', Dimension.FREQUENCY), n.mode.source, 'AnotherMode'))
    # A new ordinal by itself is not a reviewed cross-run mode identity.
    with pytest.raises(UnsafeMapping, match='physical mode'):
        em_to_reviewed_epr(**values)
    values['mode_identity'] = replace(values['mode_identity'], target_mode=values['normalization'].mode)
    assert em_to_reviewed_epr(**values).participations[0].mode_index == 2


@pytest.mark.parametrize('bad', [
    lambda inp: inp.update(evidence=()),
    lambda inp: inp.update(evidence=inp['evidence'][:3]),
    lambda inp: inp.update(evidence=tuple(replace(e, source_artifact_sha256=('1'*64,))
                                         for e in inp['evidence'])),
    lambda inp: inp.update(evidence=(replace(inp['evidence'][0], document_sha256='b'*64),
                                          *inp['evidence'][1:3], inp['evidence'][3], inp['evidence'][3])),
])
def test_missing_or_token_review_rejected(bad):
    inp = case()
    bad(inp)
    with pytest.raises((MissingEvidence, UnsafeMapping)):
        em_to_reviewed_epr(**inp)


def test_stale_revision_on_any_parent_or_review_rejected():
    inp = case()
    inp['active_revision'] = OTHER
    with pytest.raises(StaleRevision):
        em_to_reviewed_epr(**inp)
    inp = case()
    inp['evidence'] = (replace(inp['evidence'][0], revision=OTHER), *inp['evidence'][1:])
    with pytest.raises(StaleRevision):
        em_to_reviewed_epr(**inp)
    inp = case()
    inp['mesh_regions'] = (replace(inp['mesh_regions'][0],
                                   source=replace(inp['mesh_regions'][0].source, revision=OTHER)),)
    with pytest.raises(StaleRevision):
        em_to_reviewed_epr(**inp)


@pytest.mark.parametrize('change', [
    lambda inp: inp.update(junction_mappings=()),
    lambda inp: inp.update(samples=()),
    lambda inp: inp.update(samples=(replace(inp['samples'][0], junction_id='Wrong'),)),
    lambda inp: inp.update(junction_mappings=(replace(inp['junction_mappings'][0], physical_group=8),)),
    lambda inp: inp.update(element_mappings=(replace(inp['element_mappings'][0], positive_node='return',
                                                    negative_node='signal'),)),
    lambda inp: inp.update(mesh_regions=(replace(inp['mesh_regions'][0], role='conductor'),)),
    lambda inp: inp.update(samples=inp['samples'] + inp['samples']),
])
def test_missing_or_ambiguous_junction_mapping_rejected(change):
    inp = case()
    change(inp)
    with pytest.raises(UnsafeMapping):
        em_to_reviewed_epr(**inp)


@pytest.mark.parametrize('update', [
    lambda inp: inp.update(normalization=replace(inp['normalization'],
        electric_energy=interval(2, 1.9, 2.1, 'aJ', Dimension.ENERGY))),
    lambda inp: inp.update(samples=(replace(inp['samples'][0],
        peak_current=interval(30, 29, 31, 'uA', Dimension.CURRENT)),)),
    lambda inp: inp.update(samples=(replace(inp['samples'][0],
        peak_current=interval(20, 19, 21, 'uA', Dimension.CURRENT)),)),
    lambda inp: inp.update(netlist=replace(inp['netlist'],
        elements=(replace(inp['netlist'].elements[0], value=q(5, 'GHz', Dimension.ENERGY_OVER_H)),))),
])
def test_nonphysical_energy_and_unmatched_junction_ej_rejected(update):
    inp = case()
    update(inp)
    with pytest.raises(UnsafeMapping):
        em_to_reviewed_epr(**inp)


def test_no_untested_rms_or_frequency_as_energy_and_bounds_gates():
    inp = case()
    n = inp['normalization']
    with pytest.raises(InteropValidationError, match='normalization convention'):
        replace(n, current_convention='rms_amperes')
    with pytest.raises(InteropValidationError):
        replace(n, magnetic_energy=interval(0, -1, 1, 'aJ', Dimension.ENERGY))
    with pytest.raises(InteropValidationError):
        replace(n, magnetic_energy=interval(1, 1, 1, 'GHz', Dimension.FREQUENCY))
    with pytest.raises(InteropValidationError):
        interval(1, 2, 3, 'nH', Dimension.INDUCTANCE)
    with pytest.raises(InteropValidationError):
        interval(1, 0, 2, 'Hz', Dimension.FREQUENCY).require(Dimension.FREQUENCY, strictly_positive=True)
    with pytest.raises(InteropValidationError):
        replace(inp['samples'][0], inductance=interval(1, 0, 2, 'nH', Dimension.INDUCTANCE))


def test_declared_hash_and_engine_gates_not_native_verification():
    inp = case()
    n = inp['normalization']
    with pytest.raises(InteropValidationError):
        replace(n, field_export_sha256='notsha')
    inp['normalization'] = replace(n, field_export_sha256='1'*64)
    with pytest.raises(UnsafeMapping):
        em_to_reviewed_epr(**inp)
    inp = case()
    inp['normalization'] = replace(n, mode=replace(n.mode,
        source=replace(n.mode.source, engine='external')))
    with pytest.raises(UnsafeMapping):
        em_to_reviewed_epr(**inp)


def test_zero_current_accepted_as_zero_participation_not_fabricated_coupling():
    inp = case()
    inp['samples'] = (replace(inp['samples'][0],
        peak_current=interval(0, 0, 0, 'A', Dimension.CURRENT)),)
    out = em_to_reviewed_epr(**inp)
    assert out.participations[0].fraction.upper.value == 0
    assert not any(p.term.parameter in ('g', 'chi', 'EC', 'omega') for p in out.ej_parameters)


def test_high_precision_quantity_interval_survives_exact_prefix_conversions():
    number = '1.2345678901234567890123456789012345678901234567890123'
    original = q(number, 'GHz', Dimension.ENERGY_OVER_H)
    assert original.as_unit('Hz').as_unit('GHz') == original
    assert interval(number, number, number, 'GHz', Dimension.ENERGY_OVER_H).si().nominal.value == original.si().value


def test_multi_junction_conservative_energy_sum_blocks_fabricated_participation():
    inp = case()
    circuit = inp['netlist']
    second = CircuitElement('J2', ElementKind.JOSEPHSON_JUNCTION, 'signal', 'return',
                            q('16.3', 'GHz', Dimension.ENERGY_OVER_H))
    inp['netlist'] = replace(circuit, elements=(*circuit.elements, second))
    region = inp['mesh_regions'][0]
    inp['mesh_regions'] = (*inp['mesh_regions'], replace(region, region_id='J2Region',
                                                         physical_group=8))
    inp['junction_mappings'] = (*inp['junction_mappings'],
        JunctionSurfaceMapping('JunctionTwo', 'J2', 'J2Geometry', 'J2Region', 8))
    inp['element_mappings'] = (*inp['element_mappings'],
        ElementGeometryMapping('J2', 'QubitCell', 'J2Geometry', 'signal', 'return',
                               ElementKind.JOSEPHSON_JUNCTION))
    sample = inp['samples'][0]
    inp['samples'] = (*inp['samples'], replace(sample, junction_id='JunctionTwo'))
    # Merely adding a second JJ must NOT pass without an A17 tag/material audit.
    assert assess_em_to_epr(**inp).status == 'BLOCKED_EPR_REVIEW_OR_UNITS'
    existing_basis = inp['material_basis']
    extra_source = sha256(b'synthetic-JJ2-calibration').hexdigest()
    new_region = replace(existing_basis.regions[0], region_id='J2Region', physical_group=8,
                         calibration_source_sha256=extra_source)
    new_review = replace(existing_basis.review,
                         source_artifact_sha256=(*existing_basis.review.source_artifact_sha256, extra_source))
    inp['material_basis'] = replace(existing_basis, regions=(*existing_basis.regions, new_region),
                                    review=new_review)
    inp['evidence'] = tuple(
        new_review if e == existing_basis.review else
        replace(e, source_artifact_sha256=(*e.source_artifact_sha256, extra_source))
        if e.kind in (EvidenceKind.MATERIAL_AND_BOUNDARY_REVIEW,
                      EvidenceKind.QUANTIZATION_DERIVATION,
                      EvidenceKind.EXTRACTION_VALIDATION) else e
        for e in inp['evidence'])
    output = em_to_reviewed_epr(**inp)
    assert len(output.participations) == len(output.ej_parameters) == 2
    assert sum(p.fraction.nominal.value for p in output.participations) == Decimal('0.5')
    # Each individual interval is physical, but their summed upper bounds are not.
    altered = replace(sample, junction_id='JunctionTwo',
        peak_current=interval(16, 15, 17, 'uA', Dimension.CURRENT))
    inp['samples'] = (sample, altered)
    with pytest.raises(UnsafeMapping, match='Sum of JJ participation'):
        em_to_reviewed_epr(**inp)


# RC14.8: the baseline A11 native_field.compare_same_mesh_fields result is
# DIAGNOSTIC_ONLY_NOT_PHYSICAL_MODE_MATCH. Its point-sampled VTK L2 magnitude
# cannot be promoted to this native H(curl) review by a scalar threshold.
def test_unresolved_a11_mode_yields_typed_gui_block_without_any_hamiltonian():
    inp = case()
    inp['mode_identity'] = None
    with pytest.raises(MissingEvidence, match='A11 physical mode identity'):
        em_to_reviewed_epr(**inp)
    result = assess_em_to_epr(**inp)
    assert result.status == 'BLOCKED_A11_MODE_IDENTITY'
    assert 'H(curl)' in result.explanation
    assert 'Diagnostic VTK overlap' in result.explanation
    assert result.transition is None
    assert 'ej_parameters' not in canonical_json(result)
    assert content_digest(result) == content_digest(result)


def test_diagnostic_overlap_dict_and_scalar_frequency_not_accepted_as_a11_review():
    inp = case()
    inp['mode_identity'] = {'schema': 'sqe.complex-field-overlap-screen.v1',
                            'status': 'DIAGNOSTIC_ONLY_NOT_PHYSICAL_MODE_MATCH',
                            'phase_invariant_overlap_magnitude': 0.99,
                            'mode_identity': 'UNRESOLVED_REQUIRES_EXPERT_SCIENTIFIC_REVIEW'}
    assert assess_em_to_epr(**inp).status == 'BLOCKED_A11_MODE_IDENTITY'
    with pytest.raises(MissingEvidence):
        em_to_reviewed_epr(**inp)


def test_a11_fixture_acceptance_is_still_not_a_scientific_pass():
    out = assess_em_to_epr(**case())
    assert out.transition is not None
    assert out.status == 'NUMERICAL_REVIEW_ONLY_NATIVE_AND_SCIENTIFIC_QUALIFICATION_BLOCKED'
    assert all(p.term.parameter == 'EJ' for p in out.transition.ej_parameters)
    assert out.transition.mode_identity.review.kind == EvidenceKind.MODE_IDENTIFICATION
    assert 'native_overlap_report_sha256' in canonical_json(out)
    assert 'BLOCKED' in out.explanation
    with pytest.raises(InteropValidationError, match='Blocked EPR result'):
        replace(out, status='BLOCKED_A11_MODE_IDENTITY')
    with pytest.raises(InteropValidationError, match='Unrecognized EPR scientific state'):
        replace(out, status='SCIENTIFIC_PASS')
    with pytest.raises(InteropValidationError, match='qualif'):
        replace(out.transition, status='SCIENTIFIC_PASS')


@pytest.mark.parametrize('modify', [
    lambda m: replace(m, overlap_method='paraview_l2_point_sample_overlap'),
    lambda m: replace(m, phase_convention='unregistered_phase'),
    lambda m: replace(m, expert_minimum_overlap=q('0.99', '1', Dimension.DIMENSIONLESS)),
    lambda m: replace(m, expert_minimum_overlap=q(0, '1', Dimension.DIMENSIONLESS)),
    lambda m: replace(m, overlap_magnitude=interval('1.1', '0.9', '1.2', '1', Dimension.DIMENSIONLESS)),
    lambda m: replace(m, overlap_magnitude=interval(0.5, 0.3, 0.8, '1', Dimension.DIMENSIONLESS)),
    lambda m: replace(m, overlap_magnitude=interval(0.95, 0.9, 0.98, 'Hz', Dimension.FREQUENCY)),
    lambda m: replace(m, target_field_export_sha256=m.reference_field_export_sha256),
    lambda m: replace(m, native_overlap_report_sha256=m.target_mesh.sha256),
    lambda m: replace(m, reference_mode=m.target_mode),
    lambda m: replace(m, reference_mesh=replace(m.reference_mesh, revision=OTHER)),
    lambda m: replace(m, review=replace(m.review, kind=EvidenceKind.COUPLING_REVIEW)),
    lambda m: replace(m, review=replace(m.review, source_artifact_sha256=(m.target_mode.source.sha256,))),
    lambda m: replace(m, review=replace(m.review, revision=OTHER)),
    lambda m: replace(m, review=replace(m.review, document_sha256=m.native_overlap_report_sha256)),
])
def test_a11_mode_review_requires_native_source_bound_complex_overlap_and_expert_floor(modify):
    with pytest.raises(InteropValidationError):
        modify(case()['mode_identity'])


@pytest.mark.parametrize('modify', [
    lambda inp: inp.update(mode_identity=replace(inp['mode_identity'], coordinate_frame='AnotherFrame')),
    lambda inp: inp.update(mode_identity=replace(inp['mode_identity'], physical_mode_id='AnotherID'))
                or inp.update(evidence=inp['evidence'][1:]),
    lambda inp: inp.update(evidence=(replace(inp['evidence'][0], document_sha256='b'*64),
                                          *inp['evidence'][1:])),
    lambda inp: inp.update(mesh_regions=(replace(inp['mesh_regions'][0], source=
                        replace(inp['mesh_regions'][0].source, sha256='b'*64)),)),
    lambda inp: inp.update(mode_identity=replace(inp['mode_identity'], target_mode=
                        replace(inp['mode_identity'].target_mode, frequency=
                            q('6.2', 'GHz', Dimension.FREQUENCY)))),
])
def test_mode_identity_cannot_be_detached_from_epr_source_or_review(modify):
    inp = case()
    modify(inp)
    with pytest.raises((MissingEvidence, UnsafeMapping)):
        em_to_reviewed_epr(**inp)
    decision = assess_em_to_epr(**inp)
    assert decision.status == 'BLOCKED_EPR_REVIEW_OR_UNITS'
    assert decision.transition is None


@pytest.mark.parametrize('modify', [
    lambda inp: inp.update(samples=(replace(inp['samples'][0], field_export_sha256='b'*64),)),
    lambda inp: inp.update(samples=(replace(inp['samples'][0], calibration_review_sha256='b'*64),)),
    lambda inp: inp.update(evidence=tuple(replace(e, document_sha256='b'*64)
                                            if e.kind == EvidenceKind.EXTRACTION_VALIDATION else e
                                            for e in inp['evidence'])),
])
def test_each_current_and_lj_calibration_must_match_field_and_review(modify):
    inp = case()
    modify(inp)
    with pytest.raises((MissingEvidence, UnsafeMapping)):
        em_to_reviewed_epr(**inp)
    assert assess_em_to_epr(**inp).transition is None


def test_stale_junction_sample_is_revision_blocked_without_numerical_terms():
    inp = case()
    inp['samples'] = (replace(inp['samples'][0], revision=OTHER),)
    with pytest.raises(StaleRevision):
        em_to_reviewed_epr(**inp)
    decision = assess_em_to_epr(**inp)
    assert decision.status == 'BLOCKED_STALE_REVISION'
    assert decision.transition is None


def test_distinct_calibration_review_digest_and_explicit_uncertainty_are_required():
    inp = case()
    with pytest.raises(InteropValidationError, match='independent field export'):
        replace(inp['samples'][0], calibration_review_sha256=inp['normalization'].field_export_sha256)
    with pytest.raises(InteropValidationError, match='sample schema'):
        replace(inp['samples'][0], schema_version='sqe.junction-epr-sample.a12.v1')
    with pytest.raises(InteropValidationError, match='mode identity contract'):
        replace(inp['mode_identity'], schema_version='sqe.a11-reviewed-mode-identity.a12.v0')


# RC14.9 A17 material/basis handoff: all tests below use synthetic byte-hash
# markers and declarations, NEVER native verified mu/epsilon or H(curl) proof.
def test_a17_absence_blocks_even_with_a11_declaration_and_zero_terms():
    inp = case()
    inp['material_basis'] = None
    with pytest.raises(MissingEvidence, match='A17 native basis'):
        em_to_reviewed_epr(**inp)
    decision = assess_em_to_epr(**inp)
    assert decision.status == 'BLOCKED_A17_MATERIAL_BASIS'
    assert decision.transition is None
    assert 'H(curl)' in decision.explanation
    assert 'ej_parameters' not in canonical_json(decision)
    with pytest.raises(InteropValidationError, match='Blocked EPR result'):
        replace(assess_em_to_epr(**case()), status='BLOCKED_A17_MATERIAL_BASIS')


def test_a17_vtk_diagnostics_and_raw_material_dict_cannot_be_promoted():
    inp = case()
    inp['material_basis'] = {
        'schema': 'sqe.palace-local-field-diagnostic.v1',
        'H_field_status': 'BLOCKED_REQUIRES_REVIEWED_CONSTITUTIVE_MU',
        'surface_tag_status': 'BLOCKED_NO_VERIFIED_VTK_TO_GMSH_SURFACE_REGISTRATION',
        'material': 'Aluminum', 'mode_identity': 'UNRESOLVED',
    }
    assert assess_em_to_epr(**inp).status == 'BLOCKED_A17_MATERIAL_BASIS'
    with pytest.raises(MissingEvidence):
        em_to_reviewed_epr(**inp)


@pytest.mark.parametrize('modify', [
    lambda m: replace(m, basis_method='vtk_point_samples'),
    lambda m: replace(m, magnetic_field_method='B_equals_H'),
    lambda m: replace(m, reference_mesh=m.target_mesh),
    lambda m: replace(m, coordinate_frame='OtherFrame'),
    lambda m: replace(m, target_basis_sha256=m.reference_basis_sha256),
    lambda m: replace(m, reference_surface_tags_sha256=m.target_surface_tags_sha256),
    lambda m: replace(m, target_material_deck_sha256=m.reference_mesh.sha256),
    lambda m: replace(m, constitutive_review_report_sha256='invalid'),
    lambda m: replace(m, regions=()),
    lambda m: replace(m, regions=m.regions + m.regions),
    lambda m: replace(m, review=replace(m.review, kind=EvidenceKind.MODE_IDENTIFICATION)),
    lambda m: replace(m, review=replace(m.review, source_artifact_sha256=(m.target_mesh.sha256,))),
    lambda m: replace(m, review=replace(m.review, revision=OTHER)),
    lambda m: replace(m, review=replace(m.review, document_sha256=m.target_basis_sha256)),
])
def test_a17_material_provenance_must_be_independent_native_and_reviewed(modify):
    basis = case()['material_basis']
    # Common-frame mismatch is caught when connecting to the specific A11 mode,
    # while the other changes are intrinsically invalid A17 declarations.
    if modify.__code__.co_consts and 'OtherFrame' in modify.__code__.co_consts:
        inp = case()
        inp['material_basis'] = modify(inp['material_basis'])
        with pytest.raises(UnsafeMapping, match='A17 material/basis'):
            em_to_reviewed_epr(**inp)
    else:
        with pytest.raises(InteropValidationError):
            modify(basis)


@pytest.mark.parametrize('modify', [
    lambda r: replace(r, permeability=interval(1, 0, 2, 'H/m', Dimension.PERMEABILITY)),
    lambda r: replace(r, permeability=interval(1, 0.9, 1.1, 'H', Dimension.INDUCTANCE)),
    lambda r: replace(r, relative_permittivity=interval(1, 0, 2, '1', Dimension.DIMENSIONLESS)),
    lambda r: replace(r, relative_permittivity=interval(5, 4, 6, 'GHz', Dimension.FREQUENCY)),
    lambda r: replace(r, calibration_source_sha256='bad'),
    lambda r: replace(r, physical_group=0),
])
def test_a17_material_units_and_positive_interval_requirements(modify):
    with pytest.raises(InteropValidationError):
        modify(case()['material_basis'].regions[0])
    mu = case()['material_basis'].regions[0].permeability
    assert mu.si().nominal.value == Decimal('0.00000126')
    assert mu.as_unit('H/m').as_unit('uH/m') == mu


@pytest.mark.parametrize('modify', [
    lambda inp: inp.update(material_basis=replace(inp['material_basis'],
        target_mesh=inp['mode_identity'].reference_mesh, reference_mesh=inp['mode_identity'].target_mesh)),
    lambda inp: inp.update(material_basis=replace(inp['material_basis'],
        regions=(replace(inp['material_basis'].regions[0], physical_group=17),))),
    lambda inp: inp.update(material_basis=replace(inp['material_basis'],
        regions=(replace(inp['material_basis'].regions[0], material_id='Si'),))),
    lambda inp: inp.update(evidence=tuple(e for e in inp['evidence'] if e != inp['material_basis'].review)),
    lambda inp: inp.update(evidence=tuple(
        replace(e, source_artifact_sha256=tuple(x for x in e.source_artifact_sha256
               if x != inp['material_basis'].target_basis_sha256))
        if e.kind == EvidenceKind.QUANTIZATION_DERIVATION else e for e in inp['evidence'])),
])
def test_a17_basis_tag_or_review_cannot_be_decoupled_from_epr(modify):
    inp = case()
    modify(inp)
    with pytest.raises((UnsafeMapping, MissingEvidence)):
        em_to_reviewed_epr(**inp)
    decision = assess_em_to_epr(**inp)
    assert decision.status == 'BLOCKED_EPR_REVIEW_OR_UNITS'
    assert decision.transition is None


def test_material_revision_rejected_and_no_scalar_shortcut():
    inp = case()
    b = inp['material_basis']
    changed_mesh = replace(b.target_mesh, revision=OTHER)
    with pytest.raises(InteropValidationError, match='revision-bound'):
        replace(b, target_mesh=changed_mesh)
    with pytest.raises(InteropValidationError, match='material-basis schema'):
        replace(b, schema_version='sqe.a17-reviewed-material-basis.a12.v0')
    assert 'NUMERICAL_REVIEW_ONLY' in em_to_reviewed_epr(**inp).status


def test_numerical_only_transition_cannot_drop_native_material_provenance_or_jjs():
    out = em_to_reviewed_epr(**case())
    with pytest.raises(InteropValidationError, match='native mode/material provenance'):
        replace(out, participations=(replace(out.participations[0], source_artifact_sha256=('1'*64,)),))
    with pytest.raises(InteropValidationError, match='JJ or material provenance'):
        replace(out, ej_parameters=(replace(out.ej_parameters[0],
            term=replace(out.ej_parameters[0].term, source_artifact_sha256=('1'*64,))),))
    with pytest.raises(InteropValidationError, match='unique JJ'):
        replace(out, mappings=out.mappings + out.mappings)
    with pytest.raises(InteropValidationError, match='unique JJ'):
        replace(out, ej_parameters=out.ej_parameters + out.ej_parameters)
