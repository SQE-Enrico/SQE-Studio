"""SQE v0.6 physical design contract: one source -> masks, QGeometry, Palace, circuit.

A tiled prototype (1/2/4 transmons) reuses the *exact* validated single-cell
positive-metal shapes. Tiling has NO engineered inter-cell coupling. The
nominal circuit is explicitly an estimate; electrostatic extraction upgrades
only the Maxwell capacitance, never the distributed resonator inductance.
"""
from __future__ import annotations

import csv
import math
import re
import subprocess
import time
from pathlib import Path
from dataclasses import asdict

import numpy as np
from scipy.constants import h, pi, physical_constants

from . import cad, em, geometry, quantumlab
from .geometry import Rect
from .io import digest, read_json, sha256, write_json

PHI0 = physical_constants['mag. flux quantum'][0]
SIZES = (1, 2, 4)


def default_spec(cfg, size=1):
    if size not in SIZES:
        raise ValueError('Physical prototypes currently support 1, 2 or 4 transmons')
    return {'schema_version': 1, 'topology': 'tiled_floating_transmons', 'size': size,
            'junction_ej_ghz': [round(cfg['circuit']['EJ_GHz'] + i * 0.25, 6) for i in range(size)],
            'junction_cj_ff': [round(cfg['circuit']['Cj_fF_override'] or 2.5, 6) for _ in range(size)],
            'nominal_cq_ff': 78.0, 'nominal_cr_ff': 70.0, 'nominal_lr_nh': 8.0,
            'nominal_cqr_ff': 3.5, 'nominal_port_c_ff': 2.0,
            'nominal_readout_qc': 12000.0,
            'note': 'Tiled prototype: adjacent cells share ground but no designed qubit-qubit coupler.'}


def validate_spec(spec):
    if isinstance(spec, dict) and spec.get("schema_version") == 2:
        from .parametric_qpu import validate_spec as implementation
        return implementation(spec)
    if not isinstance(spec, dict): raise ValueError('physical_qpu must be a JSON object')
    allowed = {'schema_version','topology','size','junction_ej_ghz','junction_cj_ff',
               'nominal_cq_ff','nominal_cr_ff','nominal_lr_nh','nominal_cqr_ff',
               'nominal_port_c_ff','nominal_readout_qc','note'}
    if set(spec) - allowed: raise ValueError('Unsupported physical_qpu fields: '+str(sorted(set(spec)-allowed)))
    n = spec.get('size')
    if type(n) is not int or n not in SIZES: raise ValueError('Only physical 1/2/4-cell prototypes supported')
    if spec.get('schema_version') != 1 or spec.get('topology') != 'tiled_floating_transmons':
        raise ValueError('Unsupported physical design schema/topology')
    for key in ('junction_ej_ghz','junction_cj_ff'):
        values=spec.get(key)
        if not isinstance(values,list) or len(values)!=n:
            raise ValueError(key+': must contain one value per junction')
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<v<1e5 for v in values):
            raise ValueError(key+': all entries must be finite positive numbers')
    for key in ('nominal_cq_ff','nominal_cr_ff','nominal_lr_nh','nominal_cqr_ff',
                'nominal_port_c_ff','nominal_readout_qc'):
        value=spec.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<1e6:
            raise ValueError(key+': finite positive value required')
    if not isinstance(spec.get('note',''),str) or len(spec.get('note',''))>500:
        raise ValueError('Note exceeds 500 characters')
    return n


def _shift(rect,dx,dy):
    return {k:round(v+(dx if k[0]=='x' else dy),6) for k,v in rect.items()}


def build(cfg,spec):
    if isinstance(spec,dict) and spec.get("schema_version") == 2:
        from .parametric_qpu import build as implementation
        return implementation(cfg,spec)
    n=validate_spec(spec)
    cell=geometry.build(cfg)
    w=cell['chip']['x1']-cell['chip']['x0']
    h=cell['chip']['y1']-cell['chip']['y0']
    cols=2 if n in (2,4) else 1
    rows=n//cols
    metal={'ground':[]}; ports={}; components=[]; terminals=[]; junctions=[]; feed_ports=[]
    for i in range(n):
        col,row=i%cols,i//cols
        dx=(col-(cols-1)/2)*w
        dy=(row-(rows-1)/2)*h
        for name,rects in cell['metal'].items():
            owner='ground' if name=='ground' else f'Q{i}.{name}'
            metal.setdefault(owner,[]).extend(_shift(r,dx,dy) for r in rects)
            if name!='ground':
                terminals.append(owner)
                components.append({'id':owner,'cell':f'Q{i}','type':name,
                                   'anchor_um':[dx,dy], 'metal_net':owner})
        for name,rect in cell['ports'].items():
            owner=f'Q{i}.{name}'
            ports[owner]=_shift(rect,dx,dy)
            if name=='junction': junctions.append({'id':f'J{i}', 'port':owner,
                'islands':[f'Q{i}.pad_a',f'Q{i}.pad_b'],
                'ej_ghz':spec['junction_ej_ghz'][i], 'cj_ff':spec['junction_cj_ff'][i]})
            else: feed_ports.append({'id':f'Q{i}.{name}','surface':owner,'net':f'Q{i}.feedline',
                                    'impedance_ohm':50.0})
    # Reconnect the original cells' ground planes across INTERNAL scribe/edge
    # keepouts. Their signals remain at least the original die edge clearance away.
    setback=cfg['layout']['die_edge_clearance_um']
    chip={'x0':-cols*w/2,'y0':-rows*h/2,'x1':cols*w/2,'y1':rows*h/2}
    for col in range(1,cols):
        x=chip['x0']+col*w
        metal['ground'].append(asdict(Rect(x-setback,chip['y0']+setback,
                                          x+setback,chip['y1']-setback)))
    for row in range(1,rows):
        y=chip['y0']+row*h
        metal['ground'].append(asdict(Rect(chip['x0']+setback,y-setback,
                                          chip['x1']-setback,y+setback)))
    # Each cell was connectivity-tested by geometry.build; tiling cannot bring
    # signal nets into another cell because the source cell has a nonzero keepout.
    tags={'air':1,'silicon':2,'ground':10,'outer':99}
    tags.update({name:100+i for i,name in enumerate(terminals)})
    tags.update({name:1000+i for i,name in enumerate(ports)})
    result={'schema_version':2,'units':'um','topology':spec['topology'],
            'chip':chip,'metal':metal,'ports':ports,'components':components,
            'junctions':junctions,'feed_ports':feed_ports,'terminals':terminals,
            'physical_tags':tags,'cell_geometry_sha256':cell['geometry_sha256'],
            'design_spec_sha256':digest(spec),'fabrication_status':'HOLD',
            'designed_interqubit_couplers':0,
            'limitations':['No physical Q-Q coupler; cross-cell capacitive coupling only if FEM resolves it',
                'JJ gap is an idealized lumped patch; no shadow-evaporation mask',
                'Not a process DRC or a fabrication-ready routing/packaging model']}
    result['geometry_sha256']=digest({key:result[key] for key in ('units','chip','metal','ports','physical_tags','cell_geometry_sha256')})
    return result


def circuit(cfg,spec):
    if isinstance(spec,dict) and spec.get("schema_version") == 2:
        from .parametric_qpu import circuit as implementation
        return implementation(cfg,spec)
    """Generate an electrical STARTING estimate. NOT FEM-extracted C or g."""
    n=validate_spec(spec)
    d=quantumlab.preset(4 if n==2 else n)
    d['name']='SQE physical source / '+str(n)+' tiled transmons'
    # Delete pre-existing nearest-neighbor couplings: the physical layout has none.
    d['elements']=[el for el in d['elements'] if not el['id'].startswith('Cg')
                   and int(re.search(r'(\d+)$',el['id']).group(1))<n]
    for el in d['elements']:
        i=int(re.search(r'(\d+)$',el['id']).group(1))
        if el['id'].startswith('Cqr'): el['value']=spec['nominal_cqr_ff']
        elif el['id'].startswith('Cq'): el['value']=spec['nominal_cq_ff']
        elif el['id'].startswith('J'): el['ej_ghz']=spec['junction_ej_ghz'][i]
        elif el['id'].startswith('Cr'): el['value']=spec['nominal_cr_ff']
        elif el['id'].startswith('Lr'): el['value']=spec['nominal_lr_nh']
        elif el['id'].startswith('Cqr'): el['value']=spec['nominal_cqr_ff']
    d['ports']=[{'id':f'P{i+1}', 'node':f'r{i//2}','z0_ohm':50.0,
                 'coupling_ff':spec['nominal_port_c_ff']} for i in range(n*2)]
    d['qubits']=[{'id':f'Q{i}','junction':f'J{i}','node':f'q{i}',
                  'target_ghz':5.0+i*0.07,'tolerance_mhz':500.} for i in range(n)]
    d['model']='differential_island_reduction__user_declared_nominal_C_and_L'
    d['notes']='Derived topology and EJ from physical_qpu, but C and resonator L are user-declared seeds, NOT geometric extraction; no Q-Q coupling.'
    quantumlab.validate(d)
    return d


def qmetal_manifest(geom):
    if geom.get("schema_version") == 3:
        from .parametric_qpu import qmetal_manifest as implementation
        return implementation(geom)
    payload={'schema_version':1,'format':'sqe-quantum-metal-positive-mask-v1',
        'geometry_sha256':geom['geometry_sha256'],'coordinates':'millimeters','gds_layer':1,
        'chip':{'width_mm':(geom['chip']['x1']-geom['chip']['x0'])/1000,
                'height_mm':(geom['chip']['y1']-geom['chip']['y0'])/1000},
        'components':[{'name':k,'attribute':geom['physical_tags'][k], 'layer':1,
             'subtract':False,'rectangles_mm':[[r[key]/1000 for key in ('x0','y0','x1','y1')] for r in rectangles]}
            for k,rectangles in geom['metal'].items()],
        'ports':[{'name':k,'rectangle_mm':[r[key]/1000 for key in ('x0','y0','x1','y1')]}
            for k,r in geom['ports'].items()],
        'notes':['Exact positive-metal rectangles; no Quantum Metal pins/route extraction',
                 'GDS and mesh share geometry_sha256; fabrication HOLD']}
    payload['manifest_sha256']=digest(payload)
    return payload


def export_gds(geom,path):
    if geom.get("schema_version") == 3:
        from .parametric_qpu import export_gds as implementation
        return implementation(geom,path)
    rectangles=[(Rect(**r),1,0) for chunks in geom['metal'].values() for r in chunks]
    # Junction and RF port patches annotated, NOT real electrical metal shapes.
    for name, r in geom['ports'].items():
        layer=91 if name.endswith('.junction') else 92
        rectangles.append((Rect(**r),layer,0))
    c=geom['chip']; border=2
    rectangles += [(Rect(c['x0'],c['y0'],c['x1'],c['y0']+border),99,0),
                   (Rect(c['x0'],c['y1']-border,c['x1'],c['y1']),99,0)]
    cad.write_library(path,[{'name':'SQE_PHYSICAL_HOLD','rectangles':rectangles}])
    return str(path)


def _base_config(cfg):
    return {'Model':{'Mesh':'device.msh','L0':1e-6},
         'Domains':{'Materials':[{'Attributes':[1],'Permittivity':1.0},
            {'Attributes':[2],'Permittivity':cfg['materials']['epsilon_r']}],
            'Postprocessing':{'Energy':[{'Index':2,'Attributes':[2]}]}}}


def palace_configs(cfg,spec,geom):
    if isinstance(spec,dict) and spec.get("schema_version") == 2:
        from .parametric_qpu import palace_configs as implementation
        return implementation(cfg,spec,geom)
    """Return config name -> config; driven excitation is EXACTLY one port per run."""
    from copy import deepcopy
    tags=geom['physical_tags']; emcfg=cfg['em']
    order=emcfg['order']
    base=_base_config(cfg)
    linear={'Type':'SuperLU','KSPType':'FGMRES','Tol':emcfg['linear_tol'],'MaxIts':500}
    bc_term=[{'Index':i+1,'Attributes':[tags[name]]} for i,name in enumerate(geom['terminals'])]
    common_pec=[tags[k] for k in geom['metal']]+[tags['outer']]
    electro={**deepcopy(base),'Problem':{'Type':'Electrostatic','Output':'electrostatic'},
            'Boundaries':{'Ground':{'Attributes':[tags['ground'],tags['outer']]},'Terminal':bc_term},
            'Solver':{'Order':order,'Electrostatic':{'Save':0},
                      'Linear':{'Type':'BoomerAMG','KSPType':'CG','Tol':emcfg['linear_tol'],'MaxIts':500}}}
    # Electrostatic terminals must NOT also be in Ground; PEC matches all conductors.
    assert not set(sum((x['Attributes'] for x in bc_term),[])) & set(electro['Boundaries']['Ground']['Attributes'])
    rfports=[{'Index':i+1,'Attributes':[tags[p['surface']]],'Direction':'+Y','R':p['impedance_ohm']}
             for i,p in enumerate(geom['feed_ports'])]
    jjports=[]
    for i,j in enumerate(geom['junctions']):
        lj=PHI0**2/(4*pi*pi*h*j['ej_ghz']*1e9)
        jjports.append({'Index':100+i,'Attributes':[tags[j['port']]],'Direction':'+X',
                        'L':lj,'C':j['cj_ff']*1e-15})
    eigen={**deepcopy(base),'Problem':{'Type':'Eigenmode','Output':'eigenmode'},
          'Boundaries':{'PEC':{'Attributes':common_pec},'LumpedPort':rfports+jjports},
          'Solver':{'Order':order,'Eigenmode':{'Target':emcfg['eigen_target_GHz'],
                     'N':emcfg['modes'],'Save':emcfg['modes'],'Tol':1e-7},'Linear':linear}}
    if emcfg['kinetic_Ls_pH_per_square']>0:
        sheet=[tags[k] for k in geom['metal']]
        eigen['Boundaries']['PEC']['Attributes']=[tags['outer']]
        eigen['Boundaries']['Impedance']=[{'Attributes':sheet,'Ls':emcfg['kinetic_Ls_pH_per_square']*1e-12}]
    result={'electrostatic':electro,'eigenmode':eigen}
    # Palace emits port-S.csv for exactly ONE excitation per run (official docs).
    for i,_ in enumerate(rfports):
        c=deepcopy(eigen)
        key=f'driven-{i+1}'
        c['Problem']={'Type':'Driven','Output':key}
        c['Solver'].pop('Eigenmode')
        c['Solver']['Driven']={'Samples':[{'Type':'Linear','MinFreq':cfg['device']['band_min_GHz'],
            'MaxFreq':cfg['device']['band_max_GHz'],'NSample':61,'SaveStep':0}]}
        for p in c['Boundaries']['LumpedPort']:
            p['Excitation']=int(p['Index']==i+1)
        assert sum(bool(p['Excitation']) for p in c['Boundaries']['LumpedPort']) == 1
        result[key]=c
    return result


def export_package(cfg,spec,out,*,with_gds=True):
    if isinstance(spec,dict) and spec.get("schema_version") == 2:
        from .parametric_qpu import export_package as implementation
        return implementation(cfg,spec,out,with_gds=with_gds)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    geom=build(cfg,spec)
    configs=palace_configs(cfg,spec,geom)
    nominal=circuit(cfg,spec)
    write_json(out/'physical_spec.json',spec)
    write_json(out/'geometry.json',geom)
    write_json(out/'nominal_circuit.json',nominal)
    write_json(out/'qmetal.json',qmetal_manifest(geom))
    for name,value in configs.items(): write_json(out/f'{name}.json',value)
    contract={'schema_version':2,'geometry_sha256':geom['geometry_sha256'],
       'design_spec_sha256':geom['design_spec_sha256'],
       'terminal_order':geom['terminals'],'port_order':[p['id'] for p in geom['feed_ports']],
       'junction_order':[j['id'] for j in geom['junctions']],
       'tag_map':geom['physical_tags'],'palace_configs':list(configs),
       'C_source':'not_extracted','circuit_source':'user_declared_nominal_parameters',
       'mask_status':'HOLD','electromagnetic_status':'NOT_SOLVED'}
    write_json(out/'contract.json',contract)
    # Optional Julia netlist sidecar. The main physical export must not fail when
    # a physically incomplete SQUID topology cannot be reduced correctly.
    try:
        from .josephson_bridge import export_design as _export_josephson
        _export_josephson(nominal,out/'josephsoncircuits')
    except ValueError as exc:
        write_json(out/'josephsoncircuits-export-status.json',
                   {'state':'BLOCKED_INCOMPLETE_TOPOLOGY','reason':str(exc),
                    'engine':'JosephsonCircuits.jl','simulation_performed':False})
    if with_gds:export_gds(geom,out/'physical_HOLD.gds')
    return {'geometry':geom,'contract':contract,'nominal_circuit':nominal}


def mesh(cfg,geom,out):
    if geom.get("schema_version") == 3:
        from .parametric_qpu import mesh as implementation
        return implementation(cfg,geom,out)
    """OCC fragment all conducting sheets and volumes; preserve versioned group tags."""
    import gmsh
    out=Path(out)
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',1)
        gmsh.model.add('sqe_unified_qpu')
        occ=gmsh.model.occ
        c=Rect(**geom['chip']); emcfg=cfg['em']; m=cfg['materials']
        box=c.expanded(emcfg['box_margin_um'])
        zb=-m['substrate_thickness_um']-emcfg['bottom_air_um']
        air=occ.addBox(box.x0,box.y0,zb,box.x1-box.x0,box.y1-box.y0,emcfg['air_height_um']-zb)
        sub=occ.addBox(c.x0,c.y0,-m['substrate_thickness_um'],
            c.x1-c.x0,c.y1-c.y0,m['substrate_thickness_um'])
        tools=[];names=[]
        for name,rects in {**geom['metal'],**{k:[v] for k,v in geom['ports'].items()}}.items():
            faces=[(2,occ.addRectangle(r['x0'],r['y0'],0,r['x1']-r['x0'],r['y1']-r['y0'])) for r in rects]
            # Fuse each conductor before fragmenting; same-net overlapping rectangles are expected.
            if len(faces)>1:
                faces=occ.fuse([faces[0]],faces[1:])[0]
            for face in faces:
                tools.append(face);names.append(name)
        _,mapping=occ.fragment([(3,air)],[(3,sub)]+tools)
        occ.synchronize()
        sivols={t for d,t in mapping[1] if d==3}
        airvols={t for d,t in mapping[0] if d==3}-sivols
        groups={'air':sorted(airvols),'silicon':sorted(sivols)}
        for name,entities in zip(names,mapping[2:],strict=True):
            groups.setdefault(name,[]).extend(t for d,t in entities if d==2)
        outer=[];tol=1e-4
        for dim,tag in gmsh.model.getEntities(2):
            b=gmsh.model.getBoundingBox(dim,tag)
            if any(abs(b[ax]-v)<tol and abs(b[ax+3]-v)<tol for ax,vs in (
                (0,(box.x0,box.x1)),(1,(box.y0,box.y1)),(2,(zb,emcfg['air_height_um']))) for v in vs):
                outer.append(tag)
        groups['outer']=outer
        for name,ids in groups.items():
            if not ids:raise ValueError('Empty Gmsh group '+name)
            dim=3 if name in ('air','silicon') else 2
            gmsh.model.addPhysicalGroup(dim,sorted(set(ids)),geom['physical_tags'][name],name)
        edges=sorted({abs(t) for name in geom['metal'] if name!='ground'
             for s in groups[name] for dim,t in gmsh.model.getBoundary([(2,s)],oriented=False) if dim==1})
        field=gmsh.model.mesh.field.add('Distance')
        gmsh.model.mesh.field.setNumbers(field,'CurvesList',edges)
        gmsh.model.mesh.field.setNumber(field,'Sampling',1000)
        threshold=gmsh.model.mesh.field.add('Threshold')
        for k,v in {'InField':field,'SizeMin':emcfg['mesh_min_um'],
             'SizeMax':emcfg['mesh_max_um'],'DistMin':4,'DistMax':120}.items():
            gmsh.model.mesh.field.setNumber(threshold,k,v)
        gmsh.model.mesh.field.setAsBackgroundMesh(threshold)
        for opt,val in {'Mesh.MeshSizeFromPoints':0,'Mesh.MeshSizeFromCurvature':0,
              'Mesh.MeshSizeExtendFromBoundary':0,'Mesh.MeshSizeMax':emcfg['mesh_max_um'],
              'Mesh.MshFileVersion':2.2}.items():gmsh.option.setNumber(opt,val)
        gmsh.model.mesh.generate(3)
        gmsh.write(str(out/'device.msh'))
        types,tags,_=gmsh.model.mesh.getElements(3)
        rec={'geometry_sha256':geom['geometry_sha256'],'mesh_sha256':sha256(out/'device.msh'),
            'nodes':len(gmsh.model.mesh.getNodes()[0]),'volume_elements':sum(len(t) for t in tags),
            'element_types':types.tolist(),'physical_groups':groups,'units':'um'}
        write_json(out/'mesh.json',rec)
        return rec
    finally:gmsh.finalize()


def solve(out,problems,ranks=1,executable='palace',timeout=14400):
    """No fake outputs: solver must produce nonempty CSV; failures retain logs."""
    from .palace_bridge import command
    out=Path(out).resolve()
    mesh_hash=sha256(out/'device.msh')
    if mesh_hash!=read_json(out/'mesh.json')['mesh_sha256']:
        raise ValueError('Mesh integrity failed')
    contract=read_json(out/'contract.json')
    if contract['geometry_sha256']!=read_json(out/'mesh.json')['geometry_sha256']:
        raise ValueError('Contract/mesh geometry mismatch')
    for key in problems:
        if key not in contract['palace_configs']:
            raise ValueError('Unknown Palace configuration: '+key)
        cfgfile=out/f'{key}.json'; cfg=read_json(cfgfile)
        if cfg['Problem']['Output']!=key:raise ValueError('Unexpected solver output path')
        dest=out/key
        if dest.exists() and any(dest.iterdir()):raise ValueError('Refusing to overwrite solver output '+key)
        args,identity=command(out,key,ranks,executable)
        if args and args[0].lower().endswith('wsl.exe'):
            # Bound the Linux process even if the Windows WSL proxy is killed.
            # No shell interpretation or user-controlled command text.
            args = args[:4] + ['timeout', '--signal=TERM', '--kill-after=10s',
                                str(int(timeout))+'s'] + args[4:]
        record={'status':'running','configuration_sha256':sha256(cfgfile),
                'geometry_sha256':contract['geometry_sha256'],'mesh_sha256':mesh_hash,
                'solver_identity':identity,'command':args}
        write_json(out/f'solve-{key}.json',record)
        start=time.monotonic()
        try:
            with (out/f'{key}.log').open('w') as log:
                subprocess.run(args,cwd=out,stdout=log,stderr=subprocess.STDOUT,
                               timeout=timeout,check=True)
            expected={'Electrostatic':'terminal-C.csv','Eigenmode':'eig.csv',
                      'Driven':'port-S.csv'}[cfg['Problem']['Type']]
            path=dest/expected
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(f'Palace did not produce {key}/{expected}')
            record.update(status='completed',elapsed_seconds=time.monotonic()-start,
                outputs_sha256={p.relative_to(out).as_posix():sha256(p) for p in dest.rglob('*.csv')})
            write_json(out/f'solve-{key}.json',record)
        except Exception as exc:
            record.update(status='failed',error=str(exc))
            write_json(out/f'solve-{key}.json',record)
            raise
    return [read_json(out/f'solve-{name}.json') for name in problems]


def verify_solve(out,name):
    out=Path(out)
    record=read_json(out/f'solve-{name}.json')
    if record['status']!='completed' or record['mesh_sha256']!=sha256(out/'device.msh') or \
        record['configuration_sha256']!=sha256(out/f'{name}.json') or \
        record['geometry_sha256']!=read_json(out/'contract.json')['geometry_sha256']:
        raise ValueError('Stale/invalid Palace provenance '+name)
    for file,hsh in record['outputs_sha256'].items():
        p=out/file
        if not p.is_file() or sha256(p)!=hsh:raise ValueError('Changed Palace output '+file)
    return record


def extract_capacitance(out):
    """Project full conductor capacitance onto (pad_a-pad_b)/2 and resonator nodes.

    Feedlines are held at zero potential for this projection. The resulting
    Maxwell C is a matrix model, not an explicit passive-element netlist.
    """
    out=Path(out)
    verify_solve(out,'electrostatic')
    contract=read_json(out/'contract.json')
    order=contract['terminal_order']; count=len(order)
    cap=em.read_palace_capacitance(out/'electrostatic'/'terminal-C.csv',count)
    names=[];n=len(contract['junction_order'])
    T=np.zeros((count,2*n))
    for i in range(n):
        for suffix,coef in (('pad_a',0.5),('pad_b',-0.5)):
            T[order.index(f'Q{i}.{suffix}'),i]=coef
        T[order.index(f'Q{i}.resonator'),n+i]=1.0
        names.append(f'Q{i}.differential')
    names.extend(f'Q{i}.resonator' for i in range(n))
    projected=T.T @ cap @ T
    if not np.allclose(projected,projected.T,rtol=1e-8,atol=1e-7) or np.min(np.linalg.eigvalsh(projected))<=0:
        raise ValueError('Extracted projected C is not positive definite')
    result={'schema_version':1,'source':'verified_palace_electrostatic',
       'geometry_sha256':contract['geometry_sha256'],
       'raw_sha256':sha256(out/'electrostatic'/'terminal-C.csv'),
       'terminal_order':order,'conductor_maxwell_c_ff':cap.tolist(),
       'differential_coordinate_order':names,'coordinate_transform':T.tolist(),
       'projected_maxwell_c_ff':projected.tolist(),
       'readout_inductance_source':'NOT_EXTRACTED',
       'jj_capacitances_included':False,
       'assumptions':['Pad differential potential Va=+phi/2, Vb=-phi/2',
           'Feedline held at fixed zero AC potential during capacitance projection',
           'No assignment of measured readout frequency, coupling g, Q or Kerr from capacitance alone',
           'Mode shapes and field distributions need an independent eigenmode solve']}
    write_json(out/'capacitance-extraction.json',result)
    return result


def epr_from_table(frequency_ghz,ej_ghz,participation,*,source='user_supplied'):
    """First-order EPR from explicitly mapped (mode,junction) participation table."""
    f=np.asarray(frequency_ghz,dtype=float)
    ej=np.asarray(ej_ghz,dtype=float)
    p=np.asarray(participation,dtype=float)
    if not 1<=len(f)<=64 or not 1<=len(ej)<=32 or p.shape!=(len(f),len(ej)):
        raise ValueError('EPR dimensions inconsistent')
    if not np.all(np.isfinite(p)) or not np.all(np.isfinite(f)) or not np.all(np.isfinite(ej)):
        raise ValueError('Nonfinite EPR values')
    q=em.epr_kerr(f,ej,p)
    return {'source':source,'fidelity':'first_order_linearized_mode_EPR',
      'frequencies_ghz':f.tolist(),'junction_ej_ghz':ej.tolist(),
      'participation':p.tolist(),
      'cross_kerr_magnitude_mhz':q['cross_Kerr_MHz'].tolist(),
      'cross_kerr_signed_mhz':(-q['cross_Kerr_MHz']).tolist(),
      'anharmonicity_mhz':q['anharmonicity_MHz'].tolist(),
      'limitations':['Only linearized junction participation; no junction self-consistency or exact BB quantization',
        'Requires mapped Palace port-EPR.csv and mode selection for field-derived EPR',
        'Surface and bulk loss require additional calibrated loss tangents and field participations']}


def purcell_estimate(qubit_ghz,resonator_ghz,coupling_mhz,resonator_qc):
    """Dispersive two-mode estimate; not a full EM impedance or filter analysis."""
    if not all(type(v) in (int,float) and math.isfinite(v) and v>0
               for v in (qubit_ghz,resonator_ghz,coupling_mhz,resonator_qc)):
        raise ValueError('Finite positive inputs required')
    detuning=abs(qubit_ghz-resonator_ghz)*1000
    if detuning<=5*coupling_mhz:raise ValueError('Dispersive limit not satisfied: |delta| > 5g required')
    kappa=2*pi*resonator_ghz*1e9/resonator_qc
    rate=(coupling_mhz/detuning)**2*kappa
    return {'model':'two_mode_dispersive_approximation','rate_per_s':rate,
       't1_us':1e6/rate,'assumptions':['User-supplied g and resonator Qc',
       'No frequency-dependent Purcell filter, impedance extraction or multi-mode effects']}


def run_workflow(cfg,spec,stage,out,*,ranks=1,executable='palace'):
    if isinstance(spec,dict) and spec.get("schema_version") == 2:
        from .parametric_qpu import run_workflow as implementation
        return implementation(cfg,spec,stage,out,ranks=ranks,executable=executable)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    artifacts=export_package(cfg,spec,out)
    actions={'package','mesh','electrostatic','eigenmode','driven','capacitance','convergence-eigenmode','convergence-electrostatic'}
    if stage not in actions:raise ValueError('Unknown physical stage')
    data={'stage':stage,'status':'completed','geometry_sha256':artifacts['geometry']['geometry_sha256'],
          'fidelity':('geometry_contract_only' if stage=='package' else
                     'meshed_not_field_solved' if stage=='mesh' else 'actual_palace_output_required'),
          'fabrication_status':'HOLD'}
    if stage!='package':
        mesh(cfg,artifacts['geometry'],out)
        data['mesh_sha256']=sha256(out/'device.msh')
    if stage in ('electrostatic','capacitance'):
        solve(out,['electrostatic'],ranks,executable)
    if stage=='capacitance':data['extraction']=extract_capacitance(out)
    if stage=='eigenmode':solve(out,['eigenmode'],ranks,executable)
    if stage.startswith('convergence-'):
        from .palace_quality import run as run_convergence
        result=run_convergence(out,stage.removeprefix('convergence-'),ranks=ranks,executable=executable)
        data['convergence_report']=f'{stage}-report.json'
        data['numerically_converged']=result['numerically_converged']
        data['scientifically_qualified']=result['scientifically_qualified']
        data['fidelity']='real_palace_convergence_required__no_mode_overlap'
    if stage=='driven':
        names=[k for k in read_json(out/'contract.json')['palace_configs'] if k.startswith('driven-')]
        solve(out,names,ranks,executable)
        data['sparameter_columns']={name:f'{name}/port-S.csv' for name in names}
    write_json(out/'result.json',data)
    (out/'result.sha256').write_text(sha256(out/'result.json')+'\n',encoding='ascii')
    return data


def epr_from_palace_mapped(out, mode_column, junction_columns):
    """Postprocess an AUTHENTIC eigenmode solve with explicit Palace CSV columns.

    The Palace CSV schema can change with solver versions; never silently guess
    the participation column or the junction index. Explicit columns are
    matched against the actual file header and the recorded port indices.
    """
    out=Path(out)
    verify_solve(out,'eigenmode')
    contract=read_json(out/'contract.json')
    if set(junction_columns)!=set(contract['junction_order']):
        raise ValueError('Map every junction by its named id, exactly once')
    ports=read_json(out/'eigenmode.json')['Boundaries']['LumpedPort']
    expected={str(100+i):name for i,name in enumerate(contract['junction_order'])}
    if not set(expected).issubset({str(p['Index']) for p in ports if 'L' in p}):
        raise ValueError('No matching linearized junction ports in Palace configuration')
    path=out/'eigenmode'/'port-EPR.csv'
    if not path.is_file():raise ValueError('Palace eigenmode did not provide port-EPR.csv')
    with path.open(newline='',encoding='utf-8') as stream:
        reader=csv.DictReader(stream,skipinitialspace=True)
        fields=[x.strip() for x in (reader.fieldnames or [])]
        if len(fields)!=len(set(fields)) or mode_column not in fields or not set(junction_columns.values()).issubset(fields):
            raise ValueError('Explicit EPR column mapping does not match the CSV header: '+str(fields))
        rows=[];indices=[]
        for original in reader:
            row={k.strip():v for k,v in original.items() if k is not None}
            ix=float(row[mode_column])
            if not math.isfinite(ix) or int(ix)!=ix or ix<1 or int(ix) in indices:
                raise ValueError('Nonsequential or duplicated Palace mode index')
            indices.append(int(ix))
            rows.append([float(row[junction_columns[j]]) for j in contract['junction_order']])
    if not indices:raise ValueError('Empty EPR table')
    if indices!=list(range(1,len(indices)+1)):
        raise ValueError('EPR rows must include consecutive modes 1..N')
    from .em import read_eigenfrequency
    freqs=[read_eigenfrequency(out/'eigenmode'/'eig.csv',ix) for ix in indices]
    spec=read_json(out/'physical_spec.json')
    result=epr_from_table(freqs,spec['junction_ej_ghz'],rows,source='verified_palace_eigenmode_csv_mapped')
    result['port_epr_sha256']=sha256(path)
    result['eig_sha256']=sha256(out/'eigenmode'/'eig.csv')
    result['geometry_sha256']=contract['geometry_sha256']
    result['column_mapping']={'mode':mode_column,'junctions':junction_columns}
    write_json(out/'epr-quantization.json',result)
    return result


def dielectric_loss_budget(frequency_ghz,participations,loss_tangents):
    """Participation-weighted dielectric Q and T1; NO automatic field extraction."""
    if set(participations)!=set(loss_tangents) or not participations:
        raise ValueError('Every dielectric region must have one loss tangent')
    if type(frequency_ghz) not in (float,int) or not math.isfinite(frequency_ghz) or not 0<frequency_ghz<1e3:
        raise ValueError('Invalid mode frequency')
    contributions={}
    for name in participations:
        p,tan=participations[name],loss_tangents[name]
        if any(type(x) not in (float,int) or not math.isfinite(x) for x in (p,tan)) or not 0<=p<=1 or not 0<=tan<1:
            raise ValueError('Invalid participation or loss tangent: '+name)
        contributions[name]=p*tan
    if sum(participations.values())>1+1e-8:raise ValueError('Participation sum exceeds unity')
    invq=sum(contributions.values())
    return {'method':'assumed_participation_times_assumed_loss_tangent',
      'fidelity':'user_input_loss_budget_not_EM_prediction',
      'inverse_q':invq,'q_dielectric':(1/invq if invq else None),
      't1_us':(1e6/(2*pi*frequency_ghz*1e9*invq) if invq else None),
      'contributions_invq':contributions,
      'assumptions':['Surface and bulk energy participation supplied externally',
                     'Material loss tangents supplied externally, no fitted TLS saturation',
                     'Conductor, radiation, quasiparticle, Purcell and package losses excluded']}
