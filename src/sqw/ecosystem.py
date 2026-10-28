"""Topology-independent, opt-in research workflow across external quantum EDA engines.

This is a thin orchestration layer, not a duplicate CAD/FEM/quantum solver. A
step consumes a versioned file, produces immutable artifacts, and records a
content hash and epistemic status. Third-party imports are deliberately lazy.
"""
from __future__ import annotations

import csv
import importlib.metadata
import importlib.util
import json
import math
import os
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from . import __version__
from .io import digest, environment, read_json, sha256, write_json

OPERATIONS = {
    'quantumlab': ('modes', 'sparameters'),
    'scqubits': ('spectrum',),
    'quantum-metal': ('inspect',),
    'sqdmetal': ('palace_capacitance', 'palace_eigenmode'),
    'josephsoncircuits': ('export', 'linear_sweep'),
}
MODULES = {'quantumlab': None, 'scqubits': 'scqubits', 'quantum-metal': 'qiskit_metal',
           'sqdmetal': 'SQDMetal', 'josephsoncircuits': None}
PACKAGES = {'scqubits': 'scqubits', 'quantum-metal': 'quantum-metal',
            'sqdmetal': 'SQDMetal', 'josephsoncircuits': 'JosephsonCircuits.jl'}
NAME = re.compile(r'^[a-z][a-z0-9_-]{0,47}$')


class EcosystemAdapter(Protocol):
    """Contract for trusted third-party adapters installed via Python entry points.

    A runner returns (epistemic_status, relative_artifact_names, metadata).
    Stage inputs and outputs must stay inside their supplied directories.
    """
    operations: tuple[str, ...]

    def run(self, operation: str, source: Path, settings: dict, output: Path,
            *, allow_solvers: bool) -> tuple[str, list[str], dict]: ...


CUSTOM_ADAPTERS: dict[str, EcosystemAdapter] = {}


def register_adapter(name: str, adapter: EcosystemAdapter):
    """Explicit trust boundary: only applications/plugins the operator trusts."""
    if not isinstance(name,str) or not NAME.fullmatch(name) or name in OPERATIONS:
        raise ValueError('Invalid or already registered adapter name')
    operations = getattr(adapter,'operations',None)
    if not isinstance(operations,tuple) or not operations or len(operations)>16 or \
            not all(isinstance(op,str) and NAME.fullmatch(op) for op in operations) or \
            not callable(getattr(adapter,'run',None)):
        raise ValueError('Plugin must provide tuple operations and a run method')
    CUSTOM_ADAPTERS[name]=adapter
    OPERATIONS[name]=operations
    MODULES[name]=None


def load_plugins():
    """Discover installed entry points ONLY after explicit operator approval."""
    for entry in importlib.metadata.entry_points(group='sqw.ecosystem_adapters'):
        register_adapter(entry.name, entry.load())


def _safe(root, relative):
    """Allow only files within the project/run root, including symlink checks."""
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() \
            or '\\' in relative or ':' in relative or '..' in Path(relative).parts:
        raise ValueError(f'Unsafe relative file reference: {relative!r}')
    target = (Path(root).resolve() / relative).resolve()
    if not target.is_relative_to(Path(root).resolve()):
        raise ValueError('File reference escapes the project root')
    return target


def validate(spec):
    if not isinstance(spec, dict) or spec.get('schema_version') != 1:
        raise ValueError('Expected ecosystem workflow schema_version 1')
    if not isinstance(spec.get('name'), str) or not spec['name'].strip():
        raise ValueError('Project name required')
    steps = spec.get('steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= 64:
        raise ValueError('Expected 1 to 64 workflow steps')
    known = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) - {'id','engine','operation','source','needs','settings'}:
            raise ValueError('Unknown workflow step fields')
        sid, engine, op = step.get('id'), step.get('engine'), step.get('operation')
        if not isinstance(sid, str) or not NAME.fullmatch(sid) or sid in known:
            raise ValueError('Step IDs must be unique lowercase, filesystem-safe identifiers')
        if engine not in OPERATIONS or op not in OPERATIONS[engine]:
            raise ValueError(f'Unsupported adapter operation {engine}.{op}')
        needs = step.get('needs', [])
        if not isinstance(needs, list) or any(n not in known for n in needs) or len(set(needs))!=len(needs):
            raise ValueError(f'{sid}: needs must refer to preceding distinct steps')
        source = step.get('source')
        if isinstance(source, str):
            _safe('.', source)
        elif isinstance(source, dict) and set(source)=={'step','file'}:
            if source['step'] not in needs:
                raise ValueError(f'{sid}: source step must be declared in needs')
            _safe('.', source['file'])
        else:
            raise ValueError(f'{sid}: source must be relative filename or step/file reference')
        settings = step.get('settings', {})
        if not isinstance(settings, dict):
            raise ValueError('settings must be a JSON object')
        known.add(sid)
    return steps


def doctor():
    result = {}
    for engine in OPERATIONS:
        mod = MODULES[engine]
        try:
            installed = mod is None or importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError, AttributeError):
            installed = False
        pkg = PACKAGES.get(engine)
        try:
            version = importlib.metadata.version(pkg) if pkg and engine != 'josephsoncircuits' else None
        except importlib.metadata.PackageNotFoundError:
            version = None
        if engine == 'josephsoncircuits':
            installed = shutil.which('julia') is not None
        result[engine] = {'available': installed, 'version': version,
                          'operations': list(OPERATIONS[engine]),
                          'external_validation_required': engine in ('sqdmetal','josephsoncircuits')}
    result['palace'] = {'available': shutil.which('palace') is not None}
    result['gmsh'] = {'available': shutil.which('gmsh') is not None or importlib.util.find_spec('gmsh') is not None}
    return result


def plan(spec, root):
    steps = validate(spec)
    root = Path(root).resolve()
    return {'schema_version':1, 'project':spec['name'],
            'steps':[{'id':s['id'], 'adapter':s['engine']+'.'+s['operation'],
                      'dependencies':s.get('needs',[]), 'source':s['source'],
                      'available':(s['engine']=='josephsoncircuits' and s['operation']=='export')
                      or doctor()[s['engine']]['available']}
                     for s in steps], 'notes':[
                        'Availability only tests runtime presence, not scientific correctness.',
                        'Python design factories are trusted code and require --allow-project-code.',
                        'External FEM execution requires --allow-solvers and qualified geometry/boundaries.']}


def _source(root, out, step):
    source = step['source']
    if isinstance(source, str):
        result = _safe(root,source)
    else:
        result = _safe(out/'steps'/source['step'], source['file'])
    if not result.is_file():
        raise ValueError(f"Missing source for {step['id']}: {result}")
    return result


def _qdesign(source, allow_project_code):
    if source.suffix == '.json':
        from .qmetal_interop import to_qdesign
        return to_qdesign(read_json(source)), 'manifest_positive_metal_only'
    if source.suffix == '.py':
        if not allow_project_code:
            raise ValueError('Project Python factories require --allow-project-code (trusted local code)')
        namespace = runpy.run_path(str(source), run_name='__sqe_design_factory__')
        factory = namespace.get('build_design')
        if not callable(factory):
            raise ValueError('Trusted Python design file must define build_design() -> QDesign')
        design = factory()
        if not hasattr(design, 'qgeometry') or not hasattr(design, 'components'):
            raise ValueError('build_design() must return a Quantum Metal QDesign')
        return design, 'user_quantum_metal_factory_unqualified'
    raise ValueError('Quantum Metal source must be a QGeometry manifest JSON or trusted .py factory')


def _quantumlab(operation, source, settings, directory):
    from . import quantumlab
    design = read_json(source)
    quantumlab.validate(design)
    if operation == 'modes':
        result = quantumlab.solve_modes(design)
    else:
        result = quantumlab.sparameters(design, start_ghz=settings.get('start_ghz',3.0),
                                       stop_ghz=settings.get('stop_ghz',10.0),
                                       points=settings.get('points',201))
    write_json(directory/'result.json', result)
    return 'COMPUTED_REDUCED_ORDER', ['result.json'], {'fidelity':result.get('fidelity','lumped_network')}


def _scqubits(source, settings, directory):
    import scqubits as scq
    nlevels = settings.get('levels',6)
    if type(nlevels) is not int or not 2 <= nlevels <= 16:
        raise ValueError('scqubits levels must be an integer in [2,16]')
    if source.suffix.lower() in ('.yaml','.yml'):
        if not hasattr(scq.Circuit,'from_yaml_file'):
            raise RuntimeError('This scqubits version lacks Circuit.from_yaml_file; require >=4.3.2')
        obj = scq.Circuit.from_yaml_file(str(source))
        kind = 'Circuit.from_yaml_file'
    else:
        data = read_json(source)
        kind = data.get('model')
        allowed = {
            'Transmon': {'EJ','EC','ng','ncut','truncated_dim'},
            'Fluxonium': {'EJ','EC','EL','flux','cutoff','truncated_dim'},
            'TunableTransmon': {'EJmax','EC','d','flux','ng','ncut','truncated_dim'},
        }
        if kind not in allowed or not isinstance(data.get('parameters'),dict):
            raise ValueError('scqubits source requires supported model and parameters')
        values = data['parameters']
        if set(values) - allowed[kind]:
            raise ValueError('Unsupported scqubits constructor parameter')
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in values.values()):
            raise ValueError('scqubits parameters must be finite numbers')
        obj = getattr(scq,kind)(**values)
    levels = [float(v) for v in obj.eigenvals(evals_count=nlevels)]
    if len(levels) != nlevels or any(not math.isfinite(v) for v in levels):
        raise ValueError('scqubits returned nonfinite or incomplete eigenvalues')
    write_json(directory/'spectrum.json', {'schema_version':1, 'engine':'scqubits',
              'model':kind,'unit':'GHz E/h','eigenenergies_GHz':levels,
              'transitions_GHz':[v-levels[0] for v in levels],
              'f01_GHz':levels[1]-levels[0], 'not_from_EM_extraction':True})
    return 'COMPUTED_QUANTUM', ['spectrum.json'], {}


def _metal(source, settings, directory, allow_project_code):
    design, fidelity = _qdesign(source,allow_project_code)
    tables = design.qgeometry.tables
    polys = tables['poly']
    result = {'schema_version':1, 'engine':'quantum-metal',
              'components':sorted(design.components.keys()), 'polygons':int(len(polys)),
              'geometry_provenance':fidelity,
              'note':'Component inventory is not a mesh, EPR result or manufacturability approval.'}
    write_json(directory/'inventory.json',result)
    return 'INSPECTED_GEOMETRY', ['inventory.json'], {}


def _sqdmetal(operation, source, settings, directory, allow_project_code, allow_solvers):
    # SQDMetal's public QDesign -> Palace integration, NOT reimplemented Gmsh/FEM.
    # This needs a qualified Metal design (layer polarity, ground, ports, stackup).
    design, fidelity = _qdesign(source, allow_project_code)
    if fidelity == 'manifest_positive_metal_only' and settings.get('execute',False):
        raise ValueError('Cannot solve from the positive-mask bridge: use qualified QDesign factory')
    if operation == 'palace_capacitance':
        from SQDMetal.PALACE.Capacitance_Simulation import PALACE_Capacitance_Simulation as Engine
    else:
        from SQDMetal.PALACE.Eigenmode_Simulation import PALACE_Eigenmode_Simulation as Engine
    options = settings.get('solver_options', {})
    if not isinstance(options, dict):
        raise ValueError('solver_options must be a dictionary')
    name = settings.get('name','sqe_study')
    if not isinstance(name,str) or not NAME.fullmatch(name):
        raise ValueError('SQDMetal simulation name must be filesystem-safe')
    if settings.get('execute',False) and not allow_solvers:
        raise ValueError('External solver execution requires --allow-solvers')
    sim = Engine(name=name, metal_design=design, sim_parent_directory=str(directory),
                 mode='simPC', meshing='GMSH', user_options=options, create_files=True)
    layer = settings.get('metal_layer',1)
    if type(layer) is not int or not 0 <= layer <= 255:
        raise ValueError('metal_layer must be an integer between 0 and 255')
    sim.add_metallic(layer)
    # Not a safe default: some QDesigns contain a genuine positive ground plane.
    if settings.get('add_ground_plane',False):
        sim.add_ground_plane()
    for port in settings.get('junction_ports',[]):
        if not isinstance(port,dict) or set(port) - {'component','lj_h','cj_f'}:
            raise ValueError('Each junction port must declare component/Lj, optional Cj')
        if not isinstance(port.get('component'),str) or not isinstance(port.get('lj_h'),(int,float)) or port['lj_h']<=0:
            raise ValueError('Invalid Josephson port')
        sim.create_port_JosephsonJunction(port['component'], L_J=port['lj_h'], C_J=port.get('cj_f',0.0))
    sim.prepare_simulation()
    outputs = [p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()]
    status='PREPARED_NOT_SOLVED'
    if settings.get('execute',False):
        # The native solver output is authoritative. Never relabel its units as
        # fF or merge into the old four-terminal SQE extraction automatically.
        native = sim.run()
        status='SOLVED_UNQUALIFIED'
        if operation == 'palace_capacitance' and native is not None:
            import numpy as np
            try:
                arr=np.asarray(native,dtype=float)
            except (TypeError,ValueError):
                arr=np.empty((0,0))
            if arr.ndim==2 and arr.shape[0] == arr.shape[1] and arr.size and np.all(np.isfinite(arr)):
                write_json(directory/'native_capacitance_matrix.json', {
                    'state':'SOLVED_UNQUALIFIED','origin':'SQDMetal.PALACE_Capacitance_Simulation.run',
                    'unit':'native_SQDMetal_return_unverified',
                    'conductor_order':'not_normalized_to_SQE_nodes', 'matrix':arr.tolist()})
        outputs = [p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()]
    write_json(directory/'adapter.json', {'engine':'SQDMetal', 'operation':operation,
              'state':status, 'source':fidelity,
              'limitations':['Geometric, material and boundary validation remains separate',
                             'SQDMetal outputs have not been mapped into SQE native capacitance/eigenmode contract']})
    return status, sorted(set(outputs+['adapter.json'])), {'project_fidelity':fidelity}


def _josephson(operation, source, settings, directory, allow_solvers):
    from .josephson_bridge import export_design
    if source.suffix != '.json':
        raise ValueError('JosephsonCircuits source must be a QuantumLab circuit JSON')
    rec = export_design(read_json(source),directory)
    if operation == 'export':
        return 'EXPORTED_NOT_SIMULATED', ['circuit.jl','josephsoncircuits-contract.json'], {}
    if not allow_solvers:
        raise ValueError('Julia execution requires --allow-solvers')
    julia = shutil.which(settings.get('julia','julia'))
    if not julia:
        raise ValueError('Julia executable not found')
    # A real Julia invocation using the official linearized solve API; not HB pumping.
    # CSV output is deliberately simple and retains original unprocessed complex S.
    lo = settings.get('start_ghz',4.0); hi=settings.get('stop_ghz',8.0)
    count=settings.get('points',81)
    port1=settings.get('input_port',1); port2=settings.get('output_port',1)
    if not all(type(v) in (int,float) and math.isfinite(v) for v in (lo,hi)) or not 0<lo<hi<=100:
        raise ValueError('Invalid Julia frequency sweep')
    if type(count) is not int or not 2<=count<=10001:
        raise ValueError('Julia points out of range')
    nports = sum(x['type']=='P' for x in rec['elements'])
    if not nports or any(type(v) is not int or not 1<=v<=nports for v in (port1,port2)):
        raise ValueError('Julia port indices must refer to defined circuit ports')
    run_source = f'''include("circuit.jl")
using DelimitedFiles
ws = 2*pi .* collect(range(({lo:.17g})*1e9, ({hi:.17g})*1e9, length={count}))
solution = JosephsonCircuits.hblinsolve(ws, circuit, circuitdefs)
svals = solution.S(outputmode=(0,), outputport={port2}, inputmode=(0,), inputport={port1}, freqindex=:)
writedlm("sparameters.csv", hcat(ws ./ (2*pi*1e9), real.(svals), imag.(svals)), ',')
'''
    (directory/'linear_sweep.jl').write_text(run_source,encoding='utf-8')
    project = settings.get('julia_project') or os.environ.get('SQE_JULIA_ENV')
    julia_args = [julia,'--startup-file=no']
    if project:
        julia_args.append('--project='+str(Path(project).resolve()))
    complete = subprocess.run(julia_args+['linear_sweep.jl'], cwd=directory,
                              capture_output=True,text=True,timeout=600,check=False)
    (directory/'julia.log').write_text(complete.stdout+'\n'+complete.stderr,encoding='utf-8')
    if complete.returncode:
        raise RuntimeError('JosephsonCircuits failed; inspect Julia log in step directory')
    target=directory/'sparameters.csv'
    if not target.is_file():
        raise RuntimeError('Julia solver did not produce sparameters.csv')
    with target.open(newline='',encoding='utf-8') as stream:
        rows=list(csv.reader(stream))
    if len(rows)!=count:
        raise ValueError('Julia S-parameter sample count mismatch')
    for i,row in enumerate(rows):
        if len(row)!=3:
            raise ValueError('Julia must return [frequency GHz, real S, imaginary S]')
        values=[float(item) for item in row]
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Julia returned a nonfinite S-parameter value')
        frequency=lo+(hi-lo)*i/(count-1)
        if abs(values[0]-frequency)>max(1e-7,abs(frequency)*1e-9):
            raise ValueError('Julia returned an unexpected frequency axis')
    return 'SOLVED_LINEAR_UNQUALIFIED', ['circuit.jl','josephsoncircuits-contract.json','linear_sweep.jl',
                                    'julia.log','sparameters.csv'], {'port_in':port1,'port_out':port2}


def execute(spec, root, out, *, allow_project_code=False, allow_solvers=False):
    steps = validate(spec)
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Execution requires a new/empty output directory (immutable run)')
    # Avoid accidentally writing into the project tree's input artifacts.
    if not root.is_dir():
        raise ValueError('Project root does not exist')
    out.mkdir(parents=True,exist_ok=True)
    write_json(out/'workflow.json',spec)
    run = {'schema_version':1,'sqe_version':__version__,'source_sha256':digest(spec),
           'environment':environment(), 'project':spec['name'],'steps':{},'state':'RUNNING'}
    write_json(out/'run.json',run)
    for s in steps:
        sid = s['id']; dest = out/'steps'/sid
        dest.mkdir(parents=True)
        try:
            src = _source(root,out,s)
            # Versioned local input snapshot: research runs remain inspectable
            # and verifiable even if the original project is later edited.
            if src.stat().st_size > 32 * 1024 * 1024:
                raise ValueError('Input source exceeds 32 MiB; use an external verified data workflow')
            original_hash = sha256(src)
            inputs = out/'inputs'
            inputs.mkdir(exist_ok=True)
            snapshot = inputs/(sid+src.suffix.lower())
            shutil.copyfile(src,snapshot)
            if sha256(snapshot) != original_hash:
                raise ValueError('Input source changed while snapshotting')
            settings=s.get('settings',{})
            engine,operation=s['engine'],s['operation']
            if engine=='quantumlab':
                status,files,meta=_quantumlab(operation,src,settings,dest)
            elif engine=='scqubits':
                status,files,meta=_scqubits(src,settings,dest)
            elif engine=='quantum-metal':
                status,files,meta=_metal(src,settings,dest,allow_project_code)
            elif engine=='sqdmetal':
                status,files,meta=_sqdmetal(operation,src,settings,dest,allow_project_code,allow_solvers)
            elif engine=='josephsoncircuits':
                status,files,meta=_josephson(operation,src,settings,dest,allow_solvers)
            else:
                status,files,meta=CUSTOM_ADAPTERS[engine].run(operation,src,settings,dest,
                                                               allow_solvers=allow_solvers)
            if not isinstance(status,str) or not NAME.fullmatch(status.lower().replace(' ','-')) \
                    or not isinstance(files,list) or not isinstance(meta,dict):
                raise ValueError('Adapter violated the result record contract')
            if sha256(src) != original_hash:
                raise ValueError('Input source changed while executing the adapter')
            artifacts={name:sha256(_safe(dest,name)) for name in files}
            run['steps'][sid]={'adapter':engine+'.'+operation,'state':status,
                               'source':str(src), 'source_snapshot':snapshot.relative_to(out).as_posix(),
                               'source_sha256':original_hash,'artifacts':artifacts,'metadata':meta}
        except Exception as exc:
            run['state']='FAILED'
            run['steps'][sid]={'state':'FAILED','error':str(exc),'error_type':type(exc).__name__}
            write_json(out/'run.json',run)
            raise
        write_json(out/'run.json',run)
    run['state']='COMPLETED'
    write_json(out/'run.json',run)
    return run


def verify(out):
    out = Path(out).resolve()
    run=read_json(out/'run.json')
    spec=read_json(out/'workflow.json')
    if digest(spec)!=run['source_sha256']:
        raise ValueError('Workflow specification was tampered with')
    if run['state']!='COMPLETED' or set(run['steps'])!={s['id'] for s in validate(spec)}:
        raise ValueError('Run not completed')
    for sid,record in run['steps'].items():
        snap = _safe(out,record['source_snapshot'])
        if not snap.is_file() or sha256(snap) != record['source_sha256']:
            raise ValueError(f'Input snapshot mismatch: {sid}')
        for name,expect in record['artifacts'].items():
            p=_safe(out/'steps'/sid,name)
            if not p.is_file() or sha256(p)!=expect:
                raise ValueError(f'Artifact mismatch: {sid}/{name}')
    return {'verified':True,'steps':len(run['steps']),'state':run['state'],
            'note':'SHA integrity only, not physical accuracy or numerical convergence'}
