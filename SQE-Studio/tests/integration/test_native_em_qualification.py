"""Release qualification tests: never replace real native outcomes with fixture PASS."""
from pathlib import Path
import hashlib
import json
import zipfile
import pytest

from sqe_studio.qualification import qualify
from sqe_studio.native_em_qualification import _option_check, qualify_native_em


@pytest.mark.parametrize('reviewer,ack,solve,refine', [
    ('Expert',False,False,False),('',True,False,False),
    ('x',True,False,False),('Expert',True,False,True),
    ('Expert',True,'yes',False),('Expert',True,True,1)])
def test_requires_operator_review_and_consistent_plan(reviewer,ack,solve,refine):
    with pytest.raises(ValueError):
        _option_check(reviewer,ack,solve,refine)


def test_quick_native_em_never_claims_solver_when_missing(tmp_path,monkeypatch):
    import sqe_studio.native_em_qualification as em
    root=Path(__file__).resolve().parents[2]
    output=tmp_path/'em-evidence.zip'
    monkeypatch.setattr(em.importlib.util, 'find_spec',
                        lambda name: None if name=='SQDMetal' else object())
    def must_not_start(*args, **kwargs):
        raise AssertionError('Missing native dependencies must NOT invoke the worker')
    monkeypatch.setattr(em,'_run',must_not_start)
    report=qualify(root,output,profile='native_em',em_options={
        'reviewer':'ExpertOperator','acknowledged':True,'solve':False,'refine':False})
    assert report['counts']['PASS']==1  # only explicit acknowledgement
    assert report['counts']['FAIL']==0
    assert report['rc_status']=='BLOCKED_NOT_RELEASE_CANDIDATE'
    with zipfile.ZipFile(output) as z:
        hashes=json.loads(z.read('INTEGRITY.json'))['files']
        assert all(hashlib.sha256(z.read(name)).hexdigest()==h for name,h in hashes.items())
        assert not any(n.endswith('.msh') for n in z.namelist())
        assert json.loads(z.read('QUALIFICATION.json'))['review']['review_record']['status'].startswith('explicit')
        assert b'No personal designs' in z.read('SUMMARY.md')


def test_native_em_worker_failure_is_reported_without_fake_mesh(tmp_path,monkeypatch):
    import sqe_studio.native_em_qualification as em
    root=Path(__file__).resolve().parents[2]
    output=tmp_path/'em-fail.zip'
    monkeypatch.setattr(em.importlib.util,'find_spec',lambda n:object())
    monkeypatch.setattr(em,'_run',lambda *args,**kwargs: (1, 'EngineBlocked: test native failure', 0.5))
    report=qualify_native_em(root,output,reviewer='ExpertOperator',acknowledged=True)
    assert any(x['id']=='mesh_and_deck' and x['status']=='FAIL' for x in report['stages'])
    assert report['scientific_qualification']=='not_established'
    with zipfile.ZipFile(output) as z:
        assert b'EngineBlocked' in z.read('logs/mesh_and_deck.txt')
        assert 'native/mesh_and_deck-manifest.json' not in z.namelist()


def test_report_inside_source_rejected_and_no_partial(tmp_path):
    root=Path(__file__).resolve().parents[2]
    with pytest.raises(ValueError):
        qualify_native_em(root,root/'unsafe-em.zip',reviewer='ExpertOperator',acknowledged=True)
    assert not (root/'unsafe-em.zip').exists()


def test_zero_worker_exit_without_valid_manifest_is_a_failure(tmp_path,monkeypatch):
    import sqe_studio.native_em_qualification as em
    root=Path(__file__).resolve().parents[2]
    monkeypatch.setattr(em.importlib.util,'find_spec',lambda n:object())
    monkeypatch.setattr(em,'_run',lambda *args,**kwargs: (0, 'No manifest was produced', 0.01))
    output=tmp_path/'invalid-native-evidence.zip'
    result=qualify_native_em(root,output,reviewer='PhysicsOperator',acknowledged=True)
    assert any(x['id']=='mesh_and_deck' and x['status']=='FAIL' for x in result['stages'])
    assert result['counts']['FAIL']==1
    with zipfile.ZipFile(output) as z:
        assert not any(name.endswith('-manifest.json') for name in z.namelist())


def test_native_em_reference_materials_match_explicit_sqdmetal_catalogue():
    """Recorded RC13 field failure: silicon 11.7/zero-loss was not native SQDMetal's default.

    Values are exploratory catalogue constants, NOT independently measured data.
    Actual native deck remains subject to full _validate_deck checks.
    """
    from sqe_studio.interop.laptop_benchmark import resonator_project, approve_exploratory_stack
    from sqe_studio.native_em_qualification import ASSUMPTIONS, MATERIAL_SOURCE_URL
    model = resonator_project()
    substrate = model['process']['stack'][0]
    assert substrate['material'] == 'silicon'
    assert substrate['relative_permittivity'] == 11.45
    assert substrate['loss_tangent'] == 2.7e-6
    assert '11.45' in ASSUMPTIONS and '2.7e-6' in ASSUMPTIONS
    assert MATERIAL_SOURCE_URL.endswith('/SQDMetal/Utilities/Materials.py')


def test_native_em_rejects_old_dielectric_deck_without_silent_adjustment():
    from sqe_studio.interop.laptop_benchmark import resonator_project
    from sqe_studio.adapters import sqdmetal_palace_adapter as em
    from sqe_studio.adapters.base import EngineBlocked
    model = resonator_project()
    study = model['studies'][0]
    reviewed_stack = model['process']['stack']
    # Deliberately synthetic physical tags/deck: a validator unit test, not a native solve.
    document = {
        'Problem': {'Type': 'Eigenmode'},
        'Model': {'L0': 1e-3, 'Mesh': 'sqe_em.msh'},
        'Solver': {'Order': 1, 'Eigenmode': {'N': 1, 'Target': 5.0}},
        'Domains': {'Materials': [
            {'Attributes': [2], 'Permittivity': 1.0, 'LossTan': 0.0},
            {'Attributes': [1], 'Permittivity': 11.45, 'LossTan': 2.7e-6}]},
        'Boundaries': {'PEC': {'Attributes': [5]}, 'WavePort': [],
                       'LumpedPort': [{'Index': 1, 'Attributes': [6]},
                                      {'Index': 2, 'Attributes': [7]}]},
    }
    from copy import deepcopy
    em._validate_deck(document, study['inputs']['em'],
                      {'kind': 'eigenmode', '_stack_for_validation': reviewed_stack},
                      {1, 2}, {5, 6, 7})
    old = deepcopy(document)
    old['Domains']['Materials'][1].update(Permittivity=11.7, LossTan=0.0)
    with pytest.raises(EngineBlocked, match=r'native eps_r=11\.7.*reviewed eps_r=11\.45'):
        em._validate_deck(old, study['inputs']['em'],
                          {'kind': 'eigenmode', '_stack_for_validation': reviewed_stack},
                          {1, 2}, {5, 6, 7})
