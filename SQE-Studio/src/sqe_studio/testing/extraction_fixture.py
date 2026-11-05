"""Explicit constructed EM fixture for M19 software/native-quantum tests ONLY.
No QDesign, Gmsh, Palace or measured device is represented by these bytes.
Reuses the existing A11/A17 provenance fixture, independent of pytest.
"""
from hashlib import sha256
import json
from ..contracts import digest, validate_project
from ..interop.laptop_benchmark import resonator_project

def _write(root, name, blob):
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    b = blob if isinstance(blob, bytes) else json.dumps(blob, sort_keys=True).encode()
    file.write_bytes(b)
    return {'name': name, 'sha256': sha256(b).hexdigest(), 'bytes': len(b)}

def _capacitance_fixture(tmp_path):
    model = resonator_project(execution='solve')
    model['process']['source'] = 'reviewed'  # Fixture assumption; not real expert approval.
    study = model['studies'][0]
    study['kind'] = 'capacitance'
    em = study['inputs']['em']
    em['ports'] = [
        {'index': 1, 'kind': 'conductor', 'component': 'LP1', 'native_attributes': [9]},
        {'index': 2, 'kind': 'conductor', 'component': 'LP2', 'native_attributes': [10]},
    ]
    em['boundaries']['farfield'] = 'ground'
    em['solver'] = {k: v for k, v in em['solver'].items() if k not in ('start_hz', 'modes')}
    validate_project(model)
    native = tmp_path / 'native'
    entries = [
        _write(native, 'sqe_em/outputFiles/terminal-C.csv',
               b'Terminal,C1 (fF),C2 (fF)\n1,150,-50\n2,-50,160\n'),
        _write(native, 'sqe_em/sqe_em.msh', b'mock mesh, not native'),
        _write(native, 'sqe_em/sqe_em.json', {
            'Problem': {'Type': 'Electrostatic'},
            'Boundaries': {'Ground': {'Attributes': [3, 4]},
                           'Terminal': [{'Index': 1, 'Attributes': [9]},
                                        {'Index': 2, 'Attributes': [10]}]}}),
        _write(native, 'sqe_em/palace-native.log', b'fixture log, no solver ran'),
        _write(native, 'a03-native-artifacts.json', {
            'schema': 'sqe.a03.native-artifacts.v1', 'execution': 'solve',
            'native_completion': {'exit_code': 0}, 'versions': {'palace': 'Palace 0.16'},
            'port_convention': {'ordering': 'reviewed SQDMetal creation order',
                                'index_base': 1, 'ports': em['ports']}}),
    ]
    revision = 'c' * 32
    manifest = {
        'schema': 'sqe.artifact.v1', 'engine': 'sqdmetal_palace',
        'engine_version': 'SQDMetal 0.7; Gmsh 4; Palace 0.16',
        'revision_id': revision, 'project_digest': digest(model),
        'study_id': study['id'], 'kind': 'capacitance',
        'artifact_type': 'palace.capacitance_matrix',
        'fabrication_status': 'HOLD', 'scientific_status': 'review_required',
        'provenance': {'used_revision': revision, 'used_project_sha256': digest(model)},
        'artifacts': entries, 'parents': [],
    }
    _write(native, 'RESULT_MANIFEST.json', manifest)
    evidence = tmp_path / 'review.md'
    evidence.write_text('Fixture: no physical conductor review and no actual solver execution.')
    return model, native, evidence

MESH = '$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n5\n1 0 0 0\n2 1 0 0\n3 0 1 0\n4 0 0 1\n5 0 0 -1\n$EndNodes\n$Elements\n6\n1 2 2 3 101 1 2 4\n2 2 2 4 102 2 3 4\n3 2 2 9 103 1 3 4\n4 2 2 10 104 1 2 3\n5 4 2 1 201 1 2 3 4\n6 4 2 2 202 1 3 2 5\n$EndElements\n'


def source_fixture(root):
    model, folder, _ = _capacitance_fixture(root)
    model['family']='transmon'
    model['notes']='SOFTWARE_FIXTURE_ONLY: constructed Maxwell matrix and mesh; no Palace solve or literature device.'
    study=model['studies'][0]
    model['intent']['transmon_capacitance_selection']={
        'schema':'sqe.saved-transmon-capacitance-selection.v1','study_id':study['id'],
        'island_a':'LP1','island_b':'LP2',
        'other_terminal_policy':{'fixed_zero':[],'floating_zero_charge':[]},
        'configuration':'TWO_ISLAND_CHARGE_TRANSFER',
        'junction_capacitance_assumption':'MATRIX_ONLY_JUNCTION_SHUNT_NOT_ESTABLISHED'}
    stack=model['process']['stack']
    deck={'Problem':{'Type':'Electrostatic','Output':'outputFiles'},
          'Model':{'Mesh':'sqe_em.msh','L0':1e-3},
          'Solver':{'Order':study['inputs']['em']['solver']['order']},
          'Domains':{'Materials':[
              {'Attributes':[1],'Permittivity':stack[2]['relative_permittivity'],'LossTan':stack[2]['loss_tangent']},
              {'Attributes':[2],'Permittivity':stack[0]['relative_permittivity'],'LossTan':stack[0]['loss_tangent']}]},
          'Boundaries':{'Ground':{'Attributes':[3,4]},
                        'Terminal':[{'Index':1,'Attributes':[9]},{'Index':2,'Attributes':[10]}]}}
    (folder/'sqe_em/sqe_em.json').write_text(json.dumps(deck),encoding='utf-8')
    (folder/'sqe_em/sqe_em.msh').write_text(MESH,encoding='utf-8')
    manifest=json.loads((folder/'RESULT_MANIFEST.json').read_text(encoding='utf-8'))
    manifest['engine_version']='SOFTWARE_FIXTURE_ONLY_NO_PALACE'
    manifest['project_digest']=digest(model)
    manifest['provenance'].update(used_project_sha256=digest(model),execution_kind='SOFTWARE_FIXTURE')
    for entry in manifest['artifacts']:
        path=folder/entry['name']
        entry.update(sha256=sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
    (folder/'RESULT_MANIFEST.json').write_text(json.dumps(manifest),encoding='utf-8')
    return folder,manifest,{'revision':manifest['revision_id'],'revision_digest':digest(model),'model':model}


def declaration():
    return {'schema':'sqe.conditional-transmon-assumptions.m19.v1',
            'junction_capacitance_fF':2.0,
            'junction_capacitance_convention':'ADDITIONAL_LUMPED_CJ_NOT_IN_MAXWELL_MATRIX',
            'junction_reference':'Designer test assumption: additional lumped 2 fF; not a measurement',
            'josephson':{'quantity':'EJ_over_h','value':15.0,'unit':'GHz',
                         'reference':'Designer test assumption: EJ/h 15 GHz; not extracted from PEC'},
            'ng':0.0,'ncut':15,'levels':4,'acknowledged':True}
