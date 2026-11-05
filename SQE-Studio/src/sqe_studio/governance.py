"""Current development integrity, separate from scientific qualification.

One exact current source fingerprint replaces the retired historical permit chain.
The numerical/core baseline remains pinned; this never authorizes fabrication.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import stat

POLICY='DEVELOPMENT_POLICY.json'
CORE='config/core_hashes.json'
CORE_BASELINE='1f9c351168acf26afff4a060e9592d25bf09498f1c685764e28933e70c04fbc2'
PROTECTED_DIRS=('src','tests','scripts','tools','requirements','config')
PROTECTED_FILES=('pyproject.toml','Launch SQE Studio.pyw','solver_setup.py',
                 'workstation_setup.py','sqdmetal_source.py','automatic_test_plan.json','qualification_plan.json')

class ScienceFirstGateError(ValueError):
    pass

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()

def sha(data):return sha256(data).hexdigest()

def _regular(path):
    info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink() or
            getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400)):
        raise ScienceFirstGateError('NO_GO: linked or nonregular protected source')
    return path.read_bytes()

def source_hashes(root):
    root=Path(root)
    # Reuse the existing hardened inventory walk, including Windows junction checks.
    import importlib.util
    spec=importlib.util.spec_from_file_location('sqe_source_inventory',root/'tools/verify_release_source.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    found=module.inventory(root)
    return {p:h for p,h in found.items() if p in PROTECTED_FILES or p.split('/')[0] in PROTECTED_DIRS}

def fingerprint(root):return sha(canonical(source_hashes(root)))

def check(root):
    root=Path(root)
    try:
        policy=json.loads(_regular(root/POLICY))
        core=json.loads(_regular(root/CORE))
        if sha(canonical(core))!=CORE_BASELINE:
            raise ScienceFirstGateError('NO_GO: core numerical baseline changed')
        for name,expected in core.items():
            if sha(_regular(root/name))!=expected:
                raise ScienceFirstGateError('NO_GO: numerical/core source changed: '+name)
        required={'schema','authorization','scope','baseline_package_sha256','protected_fingerprint',
                  'independent_technical_reviewer','independent_scientific_reviewer','scientific_release'}
        if (not isinstance(policy,dict) or set(policy)!=required or
                policy.get('schema')!='sqe.current-development-policy.v1' or
                policy.get('scope')!='SOFTWARE_MODULARIZATION_AND_CONTEXT_REDUCTION' or
                not isinstance(policy.get('authorization'),str) or not policy['authorization'].strip() or
                policy.get('baseline_package_sha256')!='99022b932487421f8415a503f4267413d881f8ee62ce634350dc9f7095e6ae66' or
                policy.get('independent_technical_reviewer')!='UNASSIGNED' or
                policy.get('independent_scientific_reviewer')!='UNASSIGNED' or
                policy.get('scientific_release')!='NOT_AUTHORIZED' or
                policy.get('protected_fingerprint')!=fingerprint(root)):
            raise ScienceFirstGateError('NO_GO: current policy or source fingerprint is inconsistent')
    except ScienceFirstGateError:raise
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:
        raise ScienceFirstGateError('NO_GO: current policy/source cannot be verified') from error
    return {'status':'OWNER_AUTHORIZED_DEVELOPMENT','code_status':'CURRENT_MODULAR_SOURCE_VERIFIED',
            'code_fingerprint':policy['protected_fingerprint'],'science_status':'NOT_QUALIFIED',
            'independent_review':'MISSING','approval_required':False,
            'caution':'Software refactoring only; no new physical qualification or fabrication approval.'}
