"""No fabricated solver data: values below are schema-only fixtures, not EM results."""
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from sqe_studio.interop import (
    ArtifactRef, CapacitanceMatrix, CircuitElement, CircuitNetlist, CircuitPort,
    ComplexQuantity, Dimension, EMMode, ElementGeometryMapping, ElementKind, EvidenceKind, EvidenceRecord,
    HamiltonianTerm, InteropValidationError, MeshRegion, MissingEvidence,
    NetworkKind, NetworkNormalization, NetworkObservation, NetworkSample,
    Point2D, PortPinMapping, ProvenanceEdge, QGeometryPin, Quantity, RevisionBinding,
    SolverPort, StaleRevision, UnsafeMapping, canonical_json, capacitance_as,
    compatibility_for, content_digest, convert_network_frequency_units,
    frequency_as, preflight_design_to_qdesign, preflight_em_to_quantum,
    reorder_network_ports, require_active_revision, reviewed_edge,
)

REV = RevisionBinding('4b64d2b4-2a11-48ba-9fe1-e38230ad0061',
                      '5500f3ef-f944-45cd-9ad9-52fd2f1d774d', 'a' * 64)
OLD = RevisionBinding(REV.project_id, '4563e15e-a509-4b1b-994a-de4c86623c15', 'c' * 64)


def artifact(name, kind, digest='1', rev=REV, engine='external'):
    return ArtifactRef(name, kind, digest * 64, rev, engine, 'fixture-v1')


def evidence(kind, digests, rev=REV):
    return EvidenceRecord('Review' + kind.name, kind, 'd' * 64,
                          'ReviewPerson', rev, tuple(digests))


def q(value, unit, dimension):
    return Quantity(value, unit, dimension)


def netlist(rev=REV):
    source = artifact('NetlistOne', 'circuit.netlist', rev=rev)
    return CircuitNetlist(
        ('signal', 'return'),
        (CircuitElement('J1', ElementKind.JOSEPHSON_JUNCTION, 'signal', 'return',
                        q(12, 'GHz', Dimension.ENERGY_OVER_H)),),
        (CircuitPort(1, 'signal', 'return'),), source)


def point(x, y):
    return Point2D(q(x, 'mm', Dimension.LENGTH), q(y, 'mm', Dimension.LENGTH))


def pins():
    return (
        QGeometryPin('PinSignal', 'Q1', 'Signal', point(0, 0), point(0, 1), q(1, 'um', Dimension.LENGTH)),
        QGeometryPin('PinReturn', 'Q1', 'Return', point(2, 0), point(2, 1), q(1, 'um', Dimension.LENGTH)),
    )


def design_inputs():
    net = netlist()
    rec = artifact('RecipeOne', 'quantum_metal.qdesign_recipe', '2', engine='quantum_metal')
    bundle = (
        evidence(EvidenceKind.NETLIST_REVIEW, (net.source.sha256,)),
        evidence(EvidenceKind.GEOMETRY_REVIEW, (rec.sha256,)),
        evidence(EvidenceKind.PORT_CORRESPONDENCE, (net.source.sha256, rec.sha256)),
    )
    return dict(netlist=net, recipe=rec, declared_component_ids=('Q1',), declared_pins=pins(),
                port_mappings=(PortPinMapping(1, 'PinSignal', 'PinReturn'),),
                element_mappings=(ElementGeometryMapping('J1', 'Q1', 'JunctionGeometry',
                                                         'signal', 'return', ElementKind.JOSEPHSON_JUNCTION),),
                evidence=bundle, active_revision=REV)


def em_inputs():
    mode_source = artifact('ModesOne', 'palace.eigenmodes', '3', engine='sqdmetal_palace')
    cap_source = artifact('CapOne', 'palace.capacitance_matrix', '4', engine='sqdmetal_palace')
    mode = EMMode(1, q('6.2', 'GHz', Dimension.FREQUENCY), mode_source, 'ModeOne')
    cap = CapacitanceMatrix(('a', 'b'),
                            ((q(80, 'fF', Dimension.CAPACITANCE), q(-5, 'fF', Dimension.CAPACITANCE)),
                             (q(-5, 'fF', Dimension.CAPACITANCE), q(80, 'fF', Dimension.CAPACITANCE))),
                            'maxwell', cap_source)
    hashes = (mode_source.sha256, cap_source.sha256)
    terms = (HamiltonianTerm('EC', q('0.23', 'GHz', Dimension.ENERGY_OVER_H), 'Transmon',
                             'reviewed_circuit_quantization', hashes),)
    bundle = tuple(evidence(kind, hashes) for kind in (
        EvidenceKind.MODE_IDENTIFICATION, EvidenceKind.QUANTIZATION_DERIVATION,
        EvidenceKind.COUPLING_REVIEW, EvidenceKind.EXTRACTION_VALIDATION))
    return dict(modes=(mode,), capacitance=cap, reviewed_terms=terms,
                evidence=bundle, active_revision=REV)


def network():
    ports = (SolverPort(1, 11, 12, 2, q(50, 'ohm', Dimension.RESISTANCE)),
             SolverPort(2, 21, 22, 1, q(75, 'ohm', Dimension.RESISTANCE)))
    norm = NetworkNormalization(NetworkKind.S, ports, ('PlaneOne', 'PlaneTwo'), 'power_wave')
    def c(i):
        return ComplexQuantity(q(i, '1', Dimension.DIMENSIONLESS),
                               q(0, '1', Dimension.DIMENSIONLESS))
    values = ((c(1), c(2)), (c(3), c(4)))
    return NetworkObservation(norm, (NetworkSample(q(5, 'GHz', Dimension.FREQUENCY), values),),
                              artifact('SParameters', 'palace.sparameters', '6', engine='sqdmetal_palace'))


def test_exact_frequency_prefix_conversion_and_no_energy_inference():
    value = q('6.125', 'GHz', Dimension.FREQUENCY)
    assert frequency_as(value).value == Decimal('6125000000')
    assert value.as_unit('Hz').as_unit('GHz').value == value.value
    with pytest.raises(InteropValidationError):
        frequency_as(q('6.125', 'GHz', Dimension.ENERGY_OVER_H))
    with pytest.raises(InteropValidationError):
        q(1, 'GHz', Dimension.FREQUENCY).as_unit('rad/s')


def test_exact_capacitance_prefix_conversion_and_sign():
    assert capacitance_as(q('123.45', 'fF', Dimension.CAPACITANCE)).value == Decimal('1.2345e-13')
    assert capacitance_as(q('1e-15', 'F', Dimension.CAPACITANCE), 'fF').value == Decimal('1')
    with pytest.raises(InteropValidationError):
        capacitance_as(q(5, 'GHz', Dimension.FREQUENCY))
    with pytest.raises(InteropValidationError):
        CircuitElement('Bad', ElementKind.CAPACITOR, 'a', 'b', q(-5, 'fF', Dimension.CAPACITANCE))


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), '-Infinity', True, object()])
def test_nonfinite_and_untyped_values_rejected(bad):
    with pytest.raises(InteropValidationError):
        q(bad, 'Hz', Dimension.FREQUENCY)


def test_explicit_circuit_polarity_and_wire_no_implicit_ground():
    with pytest.raises(InteropValidationError):
        CircuitPort(1, 'a', 'a')
    with pytest.raises(InteropValidationError):
        CircuitElement('R1', ElementKind.RESISTOR, 'a', 'a', q(50, 'ohm', Dimension.RESISTANCE))
    with pytest.raises(InteropValidationError):
        CircuitElement('W1', ElementKind.WIRE, 'a', 'b', q(0, 'ohm', Dimension.RESISTANCE))
    assert netlist().ports[0].return_node == 'return'


def test_ports_must_be_one_based_unique_and_contiguous():
    for invalid in (0, -1, True, 1.25):
        with pytest.raises(InteropValidationError):
            CircuitPort(invalid, 'a', 'b')
    s1 = SolverPort(1, 1, 2, 1, q(50, 'ohm', Dimension.RESISTANCE))
    s3 = SolverPort(3, 3, 4, 3, q(50, 'ohm', Dimension.RESISTANCE))
    with pytest.raises(InteropValidationError):
        NetworkNormalization(NetworkKind.S, (s1, s3), ('A', 'B'), 'power_wave')


def test_network_port_matrix_permutation_preserves_physical_identity():
    original = network()
    transformed = reorder_network_ports(original, (2, 1))
    assert transformed.samples[0].values[0][0].real.value == 4
    assert transformed.samples[0].values[0][1].real.value == 3
    assert transformed.samples[0].values[1][0].real.value == 2
    assert transformed.samples[0].values[1][1].real.value == 1
    assert transformed.normalization.reference_planes == ('PlaneTwo', 'PlaneOne')
    assert tuple(p.signal_boundary for p in transformed.normalization.ports) == (21, 11)
    # Circuit port identity is not solver port indexing; preserve explicit mapping.
    assert tuple(p.circuit_port for p in transformed.normalization.ports) == (1, 2)
    assert convert_network_frequency_units(transformed, 'Hz').samples[0].frequency.value == 5_000_000_000
    with pytest.raises(UnsafeMapping):
        reorder_network_ports(original, (1, 1))


def test_network_normalization_and_shape_rejections():
    original = network()
    with pytest.raises(InteropValidationError):
        NetworkNormalization(NetworkKind.S, original.normalization.ports,
                             ('PlaneOne', 'PlaneTwo'), 'voltage_current')
    with pytest.raises(InteropValidationError):
        NetworkNormalization(NetworkKind.Z, original.normalization.ports,
                             ('PlaneOne', 'PlaneTwo'), 'power_wave')
    with pytest.raises(InteropValidationError):
        NetworkObservation(original.normalization, (NetworkSample(
            q(5, 'GHz', Dimension.FREQUENCY), ((ComplexQuantity(q(1, 'ohm', Dimension.RESISTANCE),
            q(0, 'ohm', Dimension.RESISTANCE)),) ,)),), original.source)


def test_native_yz_blocked_until_versioned_contract_migration():
    original = network()
    norm = NetworkNormalization(NetworkKind.Z, original.normalization.ports,
                                original.normalization.reference_planes, 'voltage_current')
    def z():
        return ComplexQuantity(q(50, 'ohm', Dimension.RESISTANCE), q(0, 'ohm', Dimension.RESISTANCE))
    sample = NetworkSample(q(1, 'GHz', Dimension.FREQUENCY), ((z(), z()), (z(), z())))
    with pytest.raises(InteropValidationError, match='contract migration'):
        NetworkObservation(norm, (sample,), original.source)
    measured = artifact('MeasuredOne', 'measurement.dataset', '7')
    assert NetworkObservation(norm, (sample,), measured).normalization.kind == NetworkKind.Z


def test_capacitance_convention_sign_and_native_source_required():
    data = em_inputs()['capacitance']
    assert data.values[0][1].value < 0
    with pytest.raises(InteropValidationError, match='Maxwell'):
        CapacitanceMatrix(data.conductors,
                          ((data.values[0][0], q(+5, 'fF', Dimension.CAPACITANCE)), data.values[1]),
                          'maxwell', data.source)
    with pytest.raises(InteropValidationError, match='Mutual'):
        CapacitanceMatrix(data.conductors, data.values, 'mutual', data.source)


def test_mesh_region_provenance_and_boundaries():
    mesh = artifact('MeshOne', 'gmsh.mesh', '8', engine='sqdmetal_palace')
    assert MeshRegion('Substrate', 11, 'Silicon', 'dielectric', mesh).physical_group == 11
    with pytest.raises(InteropValidationError):
        MeshRegion('Substrate', 0, 'Silicon', 'dielectric', mesh)
    with pytest.raises(InteropValidationError):
        SolverPort(1, 10, 10, 1, q(50, 'ohm', Dimension.RESISTANCE))


def test_preflight_design_to_qdesign_success_is_not_native_execution():
    result = preflight_design_to_qdesign(**design_inputs())
    assert result.status == 'PREFLIGHT_ONLY_NOT_NATIVE_EXECUTION'
    assert result.netlist_sha256 == '1' * 64


def test_preflight_design_blocks_missing_pins_and_ground_assumptions():
    inp = design_inputs()
    inp['declared_pins'] = inp['declared_pins'][:1]
    with pytest.raises(UnsafeMapping, match='cover all declared pins'):
        preflight_design_to_qdesign(**inp)
    inp = design_inputs()
    inp['port_mappings'] = ()
    with pytest.raises(UnsafeMapping):
        preflight_design_to_qdesign(**inp)
    inp = design_inputs()
    inp['evidence'] = ()
    with pytest.raises(MissingEvidence):
        preflight_design_to_qdesign(**inp)


def test_preflight_design_blocks_hidden_netlist_element_mapping():
    inp = design_inputs()
    inp['element_mappings'] = ()
    with pytest.raises(UnsafeMapping, match='Every circuit element'):
        preflight_design_to_qdesign(**inp)
    inp = design_inputs()
    inp['element_mappings'] = (ElementGeometryMapping('J1', 'Q1', 'JunctionGeometry',
                                                     'return', 'signal', ElementKind.JOSEPHSON_JUNCTION),)
    with pytest.raises(UnsafeMapping, match='signed terminals'):
        preflight_design_to_qdesign(**inp)
    inp = design_inputs()
    inp['declared_component_ids'] = ('Q2',)
    with pytest.raises(UnsafeMapping, match='component absent'):
        preflight_design_to_qdesign(**inp)


def test_preflight_design_blocks_unreviewed_netlist_geometry_correspondence():
    inp = design_inputs()
    inp['evidence'] = tuple(e for e in inp['evidence'] if e.kind != EvidenceKind.PORT_CORRESPONDENCE)
    with pytest.raises(MissingEvidence, match='port_correspondence'):
        preflight_design_to_qdesign(**inp)
    inp = design_inputs()
    inp['evidence'] = (inp['evidence'][0], inp['evidence'][1], evidence(
        EvidenceKind.PORT_CORRESPONDENCE, (inp['netlist'].source.sha256,)))
    with pytest.raises(MissingEvidence, match='exact input artifact'):
        preflight_design_to_qdesign(**inp)


def test_stale_revision_blocks_design_even_with_reviews():
    inp = design_inputs()
    inp['active_revision'] = OLD
    with pytest.raises(StaleRevision):
        preflight_design_to_qdesign(**inp)
    with pytest.raises(StaleRevision):
        require_active_revision(OLD, inp['recipe'])


def test_em_to_quantum_explicit_reviewed_terms_only():
    result = preflight_em_to_quantum(**em_inputs())
    assert result.status == 'PREFLIGHT_ONLY_NO_INFERRED_HAMILTONIAN'
    assert result.terms[0].value.dimension == Dimension.ENERGY_OVER_H


def test_em_mode_frequency_cannot_become_hamiltonian_by_inference():
    inputs = em_inputs()
    inputs['reviewed_terms'] = ()
    with pytest.raises(MissingEvidence, match='raw EM frequency'):
        preflight_em_to_quantum(**inputs)
    with pytest.raises(InteropValidationError):
        HamiltonianTerm('EC', q(5, 'GHz', Dimension.FREQUENCY), 'Transmon',
                        'reviewed_epr', ('3' * 64,))
    with pytest.raises(InteropValidationError):
        HamiltonianTerm('EJ', q(5, 'GHz', Dimension.ENERGY_OVER_H), 'Transmon',
                        'inferred_from_frequency', ('3' * 64,))


def test_em_to_quantum_blocks_missing_coupling_review():
    inp = em_inputs()
    inp['evidence'] = tuple(e for e in inp['evidence'] if e.kind != EvidenceKind.COUPLING_REVIEW)
    with pytest.raises(MissingEvidence, match='coupling_review'):
        preflight_em_to_quantum(**inp)


def test_em_to_quantum_blocks_unrelated_coupling_evidence():
    inp = em_inputs()
    inp['evidence'] = tuple(
        evidence(EvidenceKind.COUPLING_REVIEW, ('3' * 64,)) if e.kind == EvidenceKind.COUPLING_REVIEW else e
        for e in inp['evidence'])
    with pytest.raises(MissingEvidence, match='does not cover'):
        preflight_em_to_quantum(**inp)


def test_em_to_quantum_blocks_cross_revision_and_non_parent_artifacts():
    inp = em_inputs()
    inp['active_revision'] = OLD
    with pytest.raises(StaleRevision):
        preflight_em_to_quantum(**inp)
    inp = em_inputs()
    inp['reviewed_terms'] = (HamiltonianTerm('EC', q('0.3', 'GHz', Dimension.ENERGY_OVER_H),
                                            'Transmon', 'reviewed_epr', ('9' * 64,)),)
    with pytest.raises(UnsafeMapping, match='unrelated'):
        preflight_em_to_quantum(**inp)


def test_immutable_lineage_and_edge_evidence():
    src = artifact('SourceOne', 'circuit.netlist')
    out = artifact('TargetOne', 'quantum_metal.qdesign_recipe', '2', engine='quantum_metal')
    review = evidence(EvidenceKind.NETLIST_REVIEW, (src.sha256,))
    edge = reviewed_edge(parents=(src,), target=out, evidence=(review,), active_revision=REV)
    assert edge.source[0] == src
    assert edge.target == out
    with pytest.raises(FrozenInstanceError):
        edge.operation = 'tamper'
    with pytest.raises(InteropValidationError):
        ProvenanceEdge((src,), artifact('TargetOld', 'quantum_metal.qdesign_recipe', '2', rev=OLD),
                       'reviewed_mapping', (review,))
    with pytest.raises(UnsafeMapping, match='lineage'):
        reviewed_edge(parents=(src,), target=out,
                      evidence=(evidence(EvidenceKind.NETLIST_REVIEW, ('9'*64,)),),
                      active_revision=REV)


def test_versioned_quantity_evidence_and_artifact_schemas_are_strict():
    assert q(1, 'Hz', Dimension.FREQUENCY).schema_version == 'sqe.quantity.v1'
    with pytest.raises(InteropValidationError, match='quantity schema'):
        Quantity(1, 'Hz', Dimension.FREQUENCY, schema_version='sqe.quantity.v2')
    with pytest.raises(InteropValidationError, match='artifact schema'):
        ArtifactRef('NetV2', 'circuit.netlist', '1'*64, REV, 'external',
                    'fixture-v1', schema_version='sqe.artifact.v2')
    with pytest.raises(InteropValidationError, match='evidence record schema'):
        EvidenceRecord('ReviewV2', EvidenceKind.NETLIST_REVIEW, 'd'*64,
                       'ReviewPerson', REV, ('1'*64,), schema_version='sqe.evidence-record.a01.v2')
    with pytest.raises(InteropValidationError, match='evidence edge schema'):
        ProvenanceEdge((artifact('SourceV1', 'circuit.netlist'),),
                       artifact('TargetV1', 'quantum_metal.qdesign_recipe', '2'),
                       'reviewed_mapping', (evidence(EvidenceKind.NETLIST_REVIEW, ('1'*64,)),),
                       schema_version='sqe.evidence-edge.a01.v2')


def test_stable_digest_and_explicit_portable_decimal_units():
    source = netlist()
    s = canonical_json(source)
    assert '"value":"12"' in s
    assert '"dimension":"energy_over_h"' in s
    assert content_digest(source) == content_digest(source)
    assert len(content_digest(source)) == 64
    with pytest.raises(InteropValidationError):
        artifact('BadHash', 'circuit.netlist', 'z')


def test_compatibility_declarations_do_not_change_adapter_abi():
    for agent in ('A02', 'A03', 'A04', 'A05', 'A06'):
        item = compatibility_for(agent)
        assert item.consumer == agent
        assert item.status == 'declaration_only_no_adapter_integration'
        assert item.blocked_without
    with pytest.raises(ValueError):
        compatibility_for('A09')
