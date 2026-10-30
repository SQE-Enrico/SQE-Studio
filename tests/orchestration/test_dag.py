"""DAG contract tests; fake refs do NOT constitute engine acceptance."""
from dataclasses import replace
from types import SimpleNamespace
import pytest
from sqe_studio.orchestration.dag import ArtifactDAG, STAGES, Stage, GraphBlocked


def ref(kind, revision='r1', source='a'*64, status='review_required'):
    return SimpleNamespace(artifact_type=kind, revision_id=revision,
                           project_digest=source, scientific_status=status, manifest_sha256='c'*64)


def test_topological_dependencies_and_native_bridges_do_not_autostart():
    dag = ArtifactDAG()
    assert dag.order.index('qdesign') < dag.order.index('mesh') < dag.order.index('deck')
    assert dag.order.index('deck') < dag.order.index('em_modes') < dag.order.index('quantum_map') < dag.order.index('quantum_native')
    assert dag.prerequisites('quantum_map') == ('em_modes', 'em_capacitance')
    assert dag.prerequisites('circuit_native') == ('netlist',)
    assert dag.next_ready({}, revision_id='r1', project_digest='a'*64) == ()
    with pytest.raises(GraphBlocked, match='native typed adapter'):
        dag.require_ready('qdesign', {}, revision_id='r1', project_digest='a'*64)


def test_graph_requires_provenance_review_and_integrated_capability():
    dag = ArtifactDAG()
    provided = {'qdesign': ref('quantum_metal.qdesign_recipe')}
    with pytest.raises(GraphBlocked, match='review'):
        dag.require_ready('mesh', provided, revision_id='r1', project_digest='a'*64,
                          capabilities={'mesh'})
    reviews = {'qdesign_to_mesh': {'decision': 'approved', 'reviewer': 'engineer',
                                   'evidence_sha256': 'b'*64, 'revision_id': 'r1',
                                   'project_digest': 'a'*64,
                                   'parent_manifest_sha256': ['c'*64]}}
    assert dag.require_ready('mesh', provided, revision_id='r1', project_digest='a'*64,
                             capabilities={'mesh'}, reviews=reviews) == (provided['qdesign'],)
    provided['qdesign'] = ref('quantum_metal.qdesign_recipe', revision='r0')
    with pytest.raises(GraphBlocked, match='old or different revision'):
        dag.require_ready('mesh', provided, revision_id='r1', project_digest='a'*64,
                          capabilities={'mesh'}, reviews=reviews)
    provided['qdesign'] = ref('quantum_metal.gdsii')
    with pytest.raises(GraphBlocked, match='type mismatch'):
        dag.require_ready('mesh', provided, revision_id='r1', project_digest='a'*64,
                          capabilities={'mesh'}, reviews=reviews)


def test_no_automatic_quantization_mapping_or_circuit_ports():
    dag = ArtifactDAG()
    provided = {'em_modes': ref('palace.eigenmodes'),
                'em_capacitance': ref('palace.capacitance_matrix')}
    with pytest.raises(GraphBlocked, match='quantization_parameter_mapping'):
        dag.require_ready('quantum_map', provided, revision_id='r1', project_digest='a'*64,
                          capabilities={'quantum_map'})
    with pytest.raises(GraphBlocked, match='missing prerequisite netlist'):
        dag.require_ready('circuit_native', {}, revision_id='r1', project_digest='a'*64,
                          capabilities={'circuit_native'})
    assert 'quantum_map' not in dag.next_ready(provided, revision_id='r1', project_digest='a'*64)


def test_rejects_cycles_and_unknown_edges_and_duplicates():
    with pytest.raises(ValueError, match='Cycle'):
        ArtifactDAG([Stage('x', 'x', ('y',), 'A01'), Stage('y', 'y', ('x',), 'A01')])
    with pytest.raises(ValueError, match='Unknown'):
        ArtifactDAG([Stage('x', 'x', ('missing',), 'A01')])
    with pytest.raises(ValueError, match='Duplicate'):
        ArtifactDAG([Stage('x', 'x', (), 'A01'), Stage('x', 'x', (), 'A01')])
