"""Stage dependency contracts and conservative parameter signatures for checkpoint reuse."""
import importlib.util
import shutil
from functools import lru_cache
from pathlib import Path

from .. import geometry
from ..io import digest,environment,sha256
from .. import __version__
from .process import resolve

DEMO=['spec','layout','em-export','quantize','experiment','report','fabrication']
FEM=['spec','layout','em-export','mesh','solve:electrostatic','solve:eigenmode','solve:linearized','solve:driven','import','quantize','experiment','report','fabrication']
PARENTS={'spec':[],'layout':[],'em-export':['layout'],'mesh':['layout'],
 'solve:electrostatic':['em-export','mesh'],'solve:eigenmode':['em-export','mesh'],
 'solve:driven':['em-export','mesh'],'solve:linearized':['em-export','mesh'],
 'import':['layout','solve:electrostatic','solve:eigenmode'],'quantize':['layout','em-export'],
 'experiment':['quantize'],'report':['spec','layout','quantize','experiment'],
 'fabrication':['layout','quantize']}
TITLES={'spec':'Electrical targets','layout':'Parametric chip layout','em-export':'Electromagnetic model',
 'mesh':'3D mesh','solve:electrostatic':'Capacitance solve','solve:eigenmode':'Passive eigenmodes',
 'solve:driven':'Driven S-parameter sweep','solve:linearized':'Linearized JJ eigenmodes', 'import':'Mode identification and extraction','quantize':'Quantum circuit','experiment':'Expected measurements',
 'report':'Integrated report','fabrication':'Process and wafer candidates'}


def plan(target,mode):
    allowed=FEM if mode=='fem' else DEMO
    if target not in allowed: raise ValueError('Unknown stage for this workflow mode')
    wanted=set()
    def add(stage):
        if stage in wanted: return
        wanted.add(stage)
        for parent in PARENTS[stage]: add(parent)
        if stage=='quantize' and mode=='fem': add('import')
    add(target)
    return [s for s in allowed if s in wanted]


@lru_cache(maxsize=1)
def engine_identity():
    root=Path(__file__).parents[1]
    files=[root/(name+'.py') for name in ('config','geometry','cad','circuit','experiment','em','workflow','provenance','io','palace_bridge','qmetal_interop')]
    files.append(Path(__file__).parent/'process.py')
    files.append(root.parents[1]/'scripts'/'palace-wsl-run.sh')
    return {'version':__version__,'source_sha256':digest({p.name:sha256(p) for p in files}),
            'packages':environment()['packages']}


def signature(stage,doc,mode):
    cfg,p=resolve(doc)
    common={'contract':1,'engine':engine_identity(),'stage':stage,'mode':mode,'backends':doc.get('backends',{})}
    groups={
      'spec':{'targets':cfg['targets'],'ncut':cfg['circuit']['ncut']},
      'layout':{'layout':cfg['layout']},
      'em-export':{'layout':cfg['layout'],'materials':cfg['materials'],'em':cfg['em'],'circuit':cfg['circuit']},
      'mesh':{'layout':cfg['layout'],'materials':cfg['materials'],'em':cfg['em']},
      'solve:electrostatic':{'layout':cfg['layout'],'materials':cfg['materials'],'em':cfg['em'],'circuit':cfg['circuit']},
      'solve:eigenmode':{'layout':cfg['layout'],'materials':cfg['materials'],'em':cfg['em'],'circuit':cfg['circuit']},
      'solve:linearized':{'layout':cfg['layout'],'materials':cfg['materials'],'em':cfg['em'],'circuit':cfg['circuit']},
      'solve:driven':{'layout':cfg['layout'],'materials':cfg['materials'],'em':cfg['em'],'circuit':cfg['circuit']},
      'import':{'layout':cfg['layout'],'materials':cfg['materials'],'em':cfg['em'],'circuit':cfg['circuit'],'mode_index':doc.get('readout_mode')},
      'quantize':{k:cfg[k] for k in ('device','materials','circuit','layout','targets','em')},
      'experiment':cfg,'report':cfg,'fabrication':doc}
    common['parameters']=groups[stage]
    return digest(common)


def capabilities(settings):
    packages={name:importlib.util.find_spec(name) is not None for name in ('qpdk','scqubits','qutip','gmsh','klayout','qiskit_metal','SQDMetal')}
    from ..palace_bridge import readiness
    palace = readiness(settings.palace)
    return {'packages':packages,'palace':palace['installed'],'palace_details':palace,
            'capacity':{'max_jobs':settings.max_jobs,'cpus':settings.total_cpus,'memory_gb':settings.total_memory_gb},
            'engine_template':'Floating two-pad transmon / half-wave readout. Other topologies require a geometry provider.',
            'macro_execution':'Administrator-reviewed Python executes as the trusted worker account.'}


def blockers(stage,doc,mode,settings):
    errors=[]
    try:
        cfg,p=resolve(doc)
        geometry.build(cfg)
    except (ValueError,TypeError,KeyError,AttributeError) as exc:
        return [str(exc)]
    caps=capabilities(settings)
    back=doc.get('backends',{})
    steps=plan(stage,mode)
    for field,package,required in [('cad','qpdk','layout'),('quantum','scqubits','quantize'),('dynamics','qutip','experiment')]:
        if required in steps and back.get(field)==package and not caps['packages'][package]: errors.append(f'Worker package missing: {package}')
    for step in steps:
        if step=='mesh' and not caps['packages']['gmsh']: errors.append('Gmsh is not installed on this worker')
        if step.startswith('solve:') and not caps['palace']: errors.append('Palace executable is not available')
        if step=='import' and (type(doc.get('readout_mode')) is not int or doc['readout_mode']<1):
            errors.append('Select the readout mode after inspecting the passive eigenmode fields')
        if step=='fabrication' and p['junction_kind']=='lab_gds' and not caps['packages']['klayout']:
            errors.append('Laboratory GDS cell assembly requires KLayout Python on the worker')
        if step=='fabrication' and p['junction_kind']=='lab_gds' and not p['junction_asset_id']:
            errors.append('Select a laboratory junction GDS asset')
        if step=='fabrication' and p['junction_kind']=='overlap' and min(p['junction_width_nm'],p['junction_overlap_nm'])<p['min_junction_width_nm']:
            errors.append('Junction dimensions are below the declared process minimum')
    return list(dict.fromkeys(errors))
