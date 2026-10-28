"""SQE v0.7 data-driven planar superconducting QPU design.

A design description owns materials, fabrication stack, placed two-island qubits,
explicit physical couplers and CPW centre-lines. Exact orthogonal masks and
2D design-rule checks share one geometry contract. FEM is opt-in and a partial
model: junction evaporation, bridges, vias and packaging are NOT inferred.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import math
from pathlib import Path

from shapely.geometry import box, LineString
from shapely.ops import unary_union

from . import cad, quantumlab
from .geometry import Rect
from .io import digest, write_json

IDENT = __import__('re').compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,45}$')
FAMILIES = ('floating', 'cross', 'pocket')
COUPLERS = ('capacitive_pad', 'interdigitated', 'bus_cpw', 'tunable_squid', 'custom_rects')
ROUTERS = ('straight', 'manhattan', 'waypoints', 'meander')
PROCESS = ('dolan', 'manhattan', 'generic')
MAX_QUBITS = 16


def default_spec(cfg, size=2):
    if not 1 <= size <= MAX_QUBITS: raise ValueError('Use 1..16 qubits')
    cols = math.ceil(math.sqrt(size)); rows = math.ceil(size / cols)
    pitch=1800.
    qubits=[{'id':f'Q{i}','family':'floating','x_um':(i % cols-(cols-1)/2)*pitch,
             'y_um':(i//cols-(rows-1)/2)*pitch,'rotation_deg':0,
             'width_um':240.,'height_um':310.,'junction_id':f'J{i}',
             'ej_ghz':round(cfg['circuit']['EJ_GHz']+.2*i,4), 'cj_ff':2.5}
            for i in range(size)]
    couplers=[]
    for i in range(size):
        j=i+1
        if j<size and i//cols == j//cols:
            couplers.append({'id':f'K{i}_{j}','kind':'capacitive_pad','a':f'Q{i}.east',
                             'b':f'Q{j}.west','gap_um':20.,'finger_width_um':38.,
                             'nominal_c_ff':0.35})
    return {'schema_version':2,'name':'Flexible planar QPU',
      'chip':{'width_um':max(5200.,cols*pitch+2000),'height_um':max(4200.,rows*pitch+1800),
              'edge_clearance_um':160.},
      'materials':{'vacuum':{'kind':'dielectric','epsilon_r':1.,'loss_tangent':0.},
                   'silicon':{'kind':'dielectric','epsilon_r':11.7,'loss_tangent':1e-6},
                   'aluminum':{'kind':'superconductor','london_depth_nm':50.,
                               'sheet_inductance_ph_sq':0.}},
      'stack':[{'id':'substrate','role':'dielectric','material':'silicon',
                'z0_um':-525.,'thickness_um':525.},
               {'id':'base','role':'conductor','material':'aluminum',
                'z0_um':0.,'thickness_um':.1,'gds_layer':1,'gds_datatype':0},
               {'id':'junction','role':'junction_mask','material':'aluminum',
                'z0_um':.1,'thickness_um':.05,'gds_layer':91,'gds_datatype':0}],
      'junction_process':{'method':'dolan','junction_layer_id':'junction',
                          'orientation_deg':0.,'linewidth_um':.18,'overlap_um':.14,
                          'undercut_um':.25,'lead_extension_um':.5,
                          'note':'Lithography intent only: no calibrated angle/shadow process simulation'},
      'qubits':qubits,'couplers':couplers,
      'routes':[{'id':'readout_bus','net':'readout_bus','layer':'base',
                  'style':'manhattan','start_um':[-1400.,-min(1400.,rows*pitch/2+420.)],
                  'end_um':[1400.,-min(1400.,rows*pitch/2+420.)],
                  'waypoints_um':[],'width_um':12.,'gap_um':7.,
                  'bend_preference':'horizontal','meander_pitch_um':180.,
                  'meander_depth_um':120.}],
      'design_rules':{'min_signal_gap_um':3.,'min_edge_um':30.,
                       'min_trace_width_um':2.},
      'nominal':{'cq_ff':78.,'cr_ff':70.,'lr_nh':8.,'cqr_ff':3.5,
                 'port_c_ff':2.,'qc':12000.},
      'notes':'Multilayer process metadata is separate from tested planar Palace solver domain.'}


def _num(x, name, lo=None, hi=1e7):
    if type(x) not in (float, int) or not math.isfinite(x) or (lo is not None and x<=lo) or x>=hi:
        raise ValueError(f'{name}: finite number outside supported range')
    return float(x)


def _id(value, ctx):
    if not isinstance(value,str) or not IDENT.fullmatch(value):
        raise ValueError(f'{ctx}: use a short alphanumeric identifier')
    return value


def validate_spec(s):
    if not isinstance(s,dict) or s.get('schema_version')!=2:
        raise ValueError('Parametric QPU requires schema_version=2')
    chip=s['chip'];_num(chip['width_um'],'chip width',100);_num(chip['height_um'],'chip height',100)
    edge=_num(chip['edge_clearance_um'],'chip margin',0)
    if edge*2>=min(chip['width_um'],chip['height_um']):raise ValueError('Edge margin exceeds chip')
    mat=s['materials'];stack=s['stack']
    if not isinstance(mat,dict) or not 1<=len(mat)<=32 or not isinstance(stack,list) or not 2<=len(stack)<=24:
        raise ValueError('1..32 materials and 2..24 stack layers required')
    for name,m in mat.items():
        _id(name,'material');kind=m['kind']
        if kind not in ('dielectric','superconductor','normal_metal'):raise ValueError('Unknown material kind')
        if kind=='dielectric':
            _num(m['epsilon_r'],f'{name}.epsilon_r',0)
            _num(m.get('loss_tangent',0),f'{name}.loss_tangent',-1)
            if m.get('loss_tangent',0)>=1:raise ValueError('Loss tangent must be <1')
        if kind=='superconductor':
            _num(m.get('london_depth_nm',0),f'{name}.london_depth_nm',-1)
            _num(m.get('sheet_inductance_ph_sq',0),f'{name}.Ls',-1)
        if kind=='normal_metal':_num(m['conductivity_s_m'],f'{name}.conductivity',0,1e12)
    ids=set(); metal_ids=[];dielectric=[];gds=set()
    for l in stack:
        lid=_id(l['id'],'layer')
        if lid in ids:raise ValueError('Duplicate stack layer '+lid)
        ids.add(lid)
        if l['material'] not in mat:raise ValueError(f'{lid} references missing material')
        z=_num(l['z0_um'],f'{lid}.z0',-1e5,1e5)
        thickness=_num(l['thickness_um'],f'{lid}.thickness',0,1e5)
        role=l['role']
        if role=='dielectric':
            if mat[l['material']]['kind']!='dielectric':raise ValueError('Dielectric layer requires dielectric material')
            dielectric.append((z,z+thickness,lid))
        elif role in ('conductor','junction_mask'):
            if mat[l['material']]['kind']=='dielectric':raise ValueError('Metal layer references dielectric')
            layer=l['gds_layer'];dt=l.get('gds_datatype',0)
            if type(layer)!=int or type(dt)!=int or not 0<=layer<=32767 or not 0<=dt<=32767:
                raise ValueError('GDS layer/datatype out of range')
            if (layer,dt) in gds:raise ValueError('Two stack layers share the same GDS layer/datatype')
            gds.add((layer,dt))
            if role=='conductor':metal_ids.append(lid)
        else:raise ValueError('Unknown stack role '+str(role))
    if not metal_ids:raise ValueError('A conducting base layer is required')
    dielectric.sort()
    for x,y in zip(dielectric,dielectric[1:]):
        if x[1]>y[0]+1e-6:raise ValueError('Dielectric volumes overlap: '+x[2]+' / '+y[2])
    process=s['junction_process']
    if process['method'] not in PROCESS:raise ValueError('Unsupported junction method')
    if process['junction_layer_id'] not in ids:raise ValueError('Junction mask layer missing')
    if next(l for l in stack if l['id']==process['junction_layer_id'])['role']!='junction_mask':
        raise ValueError('Junction process requires a junction_mask layer')
    for k in ('linewidth_um','overlap_um','undercut_um','lead_extension_um'):
        _num(process[k],k,0 if k in ('linewidth_um','overlap_um') else -1)
    _num(process['orientation_deg'],'JJ orientation',-361,361)
    # Schema-provided geometry library: user-defined qubit shapes are first-class,
    # not restricted to the built-in named examples.
    libraries=s.get('libraries',{})
    if not isinstance(libraries,dict) or not isinstance(libraries.get('qubit_shapes',{}),dict):
        raise ValueError('libraries.qubit_shapes must be a dictionary')
    custom_shapes=libraries.get('qubit_shapes',{})
    if len(custom_shapes)>32:raise ValueError('At most 32 reusable qubit templates')
    for name,tpl in custom_shapes.items():
        _id(name,'qubit template')
        if not isinstance(tpl,dict) or set(tpl.get('electrodes',{}))!={'pad_a','pad_b'}:
            raise ValueError('Custom qubit requires pad_a and pad_b electrodes')
        for island,rects in tpl['electrodes'].items():
            if not isinstance(rects,list) or not 1<=len(rects)<=120:
                raise ValueError('Custom electrodes need 1..120 rectangles')
            for rect in rects:
                if not isinstance(rect,list) or len(rect)!=4:
                    raise ValueError('Custom rect must be [x0,y0,x1,y1]')
                for value in rect:_num(value,'custom rectangle',-1e5,1e5)
                if rect[0]>=rect[2] or rect[1]>=rect[3]:
                    raise ValueError('Custom rectangle width and height must be positive')
        pins=tpl.get('pins',{})
        if set(pins)!=set(('east','west','north','south')):
            raise ValueError('Custom qubit must declare east/west/north/south pins')
        for pin,config in pins.items():
            if config.get('island') not in ('pad_a','pad_b') or not isinstance(config.get('xy_um'),list) or len(config['xy_um'])!=2:
                raise ValueError('Custom pin requires island and xy_um')
            for value in config['xy_um']:_num(value,'custom pin',-1e5,1e5)
    qubits=s['qubits']
    if not isinstance(qubits,list) or not 1<=len(qubits)<=MAX_QUBITS:
        raise ValueError('1..16 qubits required')
    qubit_ids=set();junction_ids=set();locations=set()
    for q in qubits:
        qi=_id(q['id'],'qubit')
        if qi in qubit_ids:raise ValueError('Duplicate qubit '+qi)
        qubit_ids.add(qi)
        if q['family'] not in FAMILIES and q['family'] not in custom_shapes:raise ValueError('Unknown qubit family/template '+q['family'])
        for key in ('x_um','y_um'):_num(q[key],qi+'.'+key,-1e5,1e5)
        for key in ('width_um','height_um','ej_ghz','cj_ff'):_num(q[key],qi+'.'+key,0)
        _num(q['rotation_deg'],'rotation',-361,361)
        if q['rotation_deg'] % 90:raise ValueError('Planar rectilinear layout supports 90-degree rotations only')
        jid=_id(q['junction_id'],'junction')
        if jid in junction_ids:raise ValueError('Duplicate junction id')
        junction_ids.add(jid)
        if (q['x_um'],q['y_um']) in locations:raise ValueError('Overlapping qubit centers')
        locations.add((q['x_um'],q['y_um']))
    rules=s['design_rules']
    for k in ('min_signal_gap_um','min_edge_um','min_trace_width_um'):_num(rules[k],k,0)
    coupler_ids=set()
    for c in s['couplers']:
        ci=_id(c['id'],'coupler')
        if ci in coupler_ids:raise ValueError('Duplicate coupler')
        coupler_ids.add(ci)
        if c['kind'] not in COUPLERS:raise ValueError('Unknown coupler type')
        for end in ('a','b'):
            qname,pin=c[end].split('.',1) if isinstance(c[end],str) and '.' in c[end] else ('','')
            if qname not in qubit_ids or pin not in ('east','west','north','south'):
                raise ValueError(f'{ci}: endpoints must be QID.east/west/north/south')
        if c['a'].split('.')[0]==c['b'].split('.')[0]:raise ValueError('Self coupler is unsupported')
        _num(c['gap_um'],ci+'.gap',0)
        _num(c['finger_width_um'],ci+'.finger_width',0)
        _num(c['nominal_c_ff'],ci+'.nominal_c',0)
        if c['kind']=='custom_rects':
            if c.get('electrical_model','C') not in ('C','SQUID'):
                raise ValueError('Custom coupler electrical_model must be C or SQUID')
            shapes=c.get('electrodes',{})
            if set(shapes)!={'a','b'}:raise ValueError('Custom coupler needs a/b electrode polygons')
            for island,rects in shapes.items():
                if not isinstance(rects,list) or not 1<=len(rects)<=80:
                    raise ValueError('Custom coupler requires 1..80 rectangles per electrode')
                for rect in rects:
                    if not isinstance(rect,list) or len(rect)!=4:
                        raise ValueError('Custom coupler rectangle must have four coordinates')
                    for value in rect:_num(value,'custom coupler rectangle',-1e5,1e5)
                    if rect[0]>=rect[2] or rect[1]>=rect[3]:
                        raise ValueError('Custom coupler rectangle has nonpositive area')
        if c['kind']=='interdigitated':
            fingers=c.get('fingers',3)
            if type(fingers)!=int or not 2<=fingers<=16:raise ValueError('Fingers must be 2..16')
        if c['kind']=='tunable_squid':
            _num(c.get('ej_ghz',8.),ci+'.ej',0)
    route_ids=set()
    for r in s['routes']:
        ri=_id(r['id'],'route')
        if ri in route_ids:raise ValueError('Duplicate route')
        route_ids.add(ri);_id(r['net'],'route net')
        if r['layer'] not in metal_ids:raise ValueError('Route targets unknown conductor layer')
        if r['style'] not in ROUTERS:raise ValueError('Unknown CPW style')
        for key in ('start_um','end_um'):
            xy=r[key]
            if not isinstance(xy,list) or len(xy)!=2:raise ValueError('Route endpoint must be [x,y]')
            for v in xy:_num(v,ri+'.'+key,-1e5,1e5)
        if not isinstance(r.get('waypoints_um',[]),list) or len(r['waypoints_um'])>40:raise ValueError('At most 40 waypoints')
        for xy in r['waypoints_um']:
            if not isinstance(xy,list) or len(xy)!=2:raise ValueError('Waypoint must be [x,y]')
            for v in xy:_num(v,'route waypoint',-1e5,1e5)
        for k in ('width_um','gap_um','meander_pitch_um','meander_depth_um'):_num(r[k],ri+'.'+k,0)
        if r['width_um']<rules['min_trace_width_um']:raise ValueError('Route narrower than design rule')
        if r['gap_um']<rules['min_signal_gap_um']:raise ValueError('CPW ground clearance violates minimum gap')
        if r.get('bend_preference','horizontal') not in ('horizontal','vertical'):
            raise ValueError('Invalid bend preference')
    for k,v in s['nominal'].items():_num(v,'nominal.'+k,0)
    return len(qubits)


def _rect(x0,y0,x1,y1):
    if x1<=x0 or y1<=y0:raise ValueError('Invalid metal rectangle')
    return box(x0,y0,x1,y1)


def _rotate_rect(shape,x,y,rotation):
    from shapely import affinity
    if rotation:shape=affinity.rotate(shape,rotation,origin=(0,0))
    return affinity.translate(shape,x,y)


def _midpoint(q,pin):
    half=q['width_um']/2
    # Q island A is left, island B is right; pin orientation rotates with component.
    template=q.get('_template')
    local=template['pins'][pin]['xy_um'] if template else {
         'west':(-1.5*half,0),'east':(1.5*half,0),
         'north':(0,q['height_um']/2),'south':(0,-q['height_um']/2)}[pin]
    angle=math.radians(q['rotation_deg']); x,y=local
    return (q['x_um']+x*math.cos(angle)-y*math.sin(angle),
            q['y_um']+x*math.sin(angle)+y*math.cos(angle))


def _island(q,pin):
    # The west/east ports refer to electrode A/B, respectively; N/S are A.
    template=q.get('_template')
    return q['id']+'.'+(template['pins'][pin]['island'] if template else
                          ('pad_b' if pin=='east' else 'pad_a'))


def _path_points(route):
    start=tuple(route['start_um']);end=tuple(route['end_um']);anchors=[start]+[tuple(p) for p in route['waypoints_um']]+[end]
    style=route['style']
    points=[anchors[0]]
    for a,b in zip(anchors,anchors[1:]):
        if a==b:continue
        if a[0]!=b[0] and a[1]!=b[1]:
            if style in ('straight','waypoints'):
                raise ValueError(f"Route {route['id']}: nonorthogonal path; add an anchor or select manhattan")
            bend=(b[0],a[1]) if route.get('bend_preference','horizontal')=='horizontal' else (a[0],b[1])
            points.append(bend)
        points.append(b)
    if len(points)<2:raise ValueError('Degenerate route')
    if style=='meander':
        # Insert an alternating, axis-aligned detour on the longest segment.
        k=max(range(len(points)-1),key=lambda i:abs(points[i][0]-points[i+1][0])+abs(points[i][1]-points[i+1][1]))
        a,b=points[k:k+2];horizontal=a[1]==b[1];length=abs((b[0]-a[0]) if horizontal else (b[1]-a[1]));pitch=route['meander_pitch_um'];depth=route['meander_depth_um']
        count=int(length//pitch)-1
        if count<2:raise ValueError('Meander segment shorter than two pitches')
        count=min(count,100)
        direction=1 if (b[0]-a[0] if horizontal else b[1]-a[1])>0 else -1
        path=[a]
        # Connect successive stations at alternate transverse heights; unlike
        # dead-end stubs, this produces a real lengthened continuous CPW.
        offset=0.
        for i in range(1,count+1):
            station=i*length/(count+1)
            along=a[0]+direction*station if horizontal else a[1]+direction*station
            before=(along,a[1]+offset) if horizontal else (a[0]+offset,along)
            offset=depth*(1 if i%2 else -1)
            after=(along,a[1]+offset) if horizontal else (a[0]+offset,along)
            path.extend((before,after))
        last=(path[-1][0],a[1]) if horizontal else (a[0],path[-1][1])
        path.append(last)
        path.append(b);points=points[:k]+path+points[k+2:]
    compact=[points[0]]
    for p in points[1:]:
        if p!=compact[-1]:compact.append(p)
    if len(compact)<2:raise ValueError('Zero-length route')
    for a,b in zip(compact,compact[1:]):
        if a[0]!=b[0] and a[1]!=b[1]:raise ValueError('Non-orthogonal route')
    return compact


def _path_shape(points,width):
    return LineString(points).buffer(width/2,cap_style=3,join_style=2)


def _rectangles(poly):
    """Exact orthogonal polygon decomposition to 1 nm quantized GDS rectangles."""
    if poly.is_empty:return []
    polys=list(poly.geoms) if poly.geom_type=='MultiPolygon' else [poly]
    if any(p.geom_type!='Polygon' for p in polys):raise ValueError('Unsupported polygon type')
    ys=sorted(set(round(y,6) for p in polys for ring in [p.exterior,*p.interiors] for x,y in ring.coords))
    out=[];xmin,xmax=poly.bounds[0]-10,poly.bounds[2]+10
    for a,b in zip(ys,ys[1:]):
        if b-a<1e-6:continue
        mid=(a+b)/2
        section=poly.intersection(LineString([(xmin,mid),(xmax,mid)]))
        segments=([section] if section.geom_type=='LineString' else
                  list(section.geoms) if section.geom_type=='MultiLineString' else [])
        for line in segments:
            left,right=line.bounds[0],line.bounds[2]
            if right-left>1e-6:out.append({'x0':round(left,6),'y0':a,'x1':round(right,6),'y1':b})
        if len(out)>20000:raise ValueError('Geometry requires >20000 rectangles; simplify layout')
    # Compact contiguous vertical rectangles with matching x-span.
    by_x={}
    for r in out:by_x.setdefault((r['x0'],r['x1']),[]).append(r)
    merged=[]
    for group in by_x.values():
        group.sort(key=lambda r:r['y0'])
        for r in group:
            if merged and merged[-1]['x0']==r['x0'] and merged[-1]['x1']==r['x1'] and abs(merged[-1]['y1']-r['y0'])<1e-6:
                merged[-1]['y1']=r['y1']
            else:merged.append(r.copy())
    if not math.isclose(sum((r['x1']-r['x0'])*(r['y1']-r['y0']) for r in merged),poly.area,rel_tol=1e-7,abs_tol=1e-3):
        raise ValueError('Non-orthogonal polygon cannot be losslessly tiled; choose orthogonal geometry')
    return merged


def build(cfg,s):
    validate_spec(s)
    shapes=s.get('libraries',{}).get('qubit_shapes',{})
    qmap={q['id']:{**q,'_template':shapes.get(q['family'])} for q in s['qubits']}
    chip=s['chip'];hw=chip['width_um']/2;hh=chip['height_um']/2
    edge=chip['edge_clearance_um']; outline=box(-hw,-hh,hw,hh)
    allowed=outline.buffer(-edge,join_style=2)
    metal={};layer_map={};clearance={};jj_ports={};components=[];connectivity=[];coupler_records=[];process_features=[]
    layer_base=next(l['id'] for l in s['stack'] if l['role']=='conductor')
    rules=s['design_rules']
    for item in s['qubits']:
        q=qmap[item['id']]
        w,h=q['width_um'],q['height_um'];gap=max(12.,w*.10)
        a=_rect(-w-gap/2,-h/2,-gap/2,h/2)
        b=_rect(gap/2,-h/2,w+gap/2,h/2)
        if q.get('_template'):
            t=q['_template']
            a=unary_union([_rect(*r) for r in t['electrodes']['pad_a']])
            b=unary_union([_rect(*r) for r in t['electrodes']['pad_b']])
        if q['family']=='cross':
            a=unary_union([a, _rect(-w-gap/2, -h*.7, -w-gap/2+w*.36,h*.7)])
        if q['family']=='pocket':
            a=unary_union([a,_rect(-w-gap/2,-h*.7,-gap/2,h*.7)])
        for suffix,shape in (('pad_a',a),('pad_b',b)):
            net=q['id']+'.'+suffix
            metal[net]=_rotate_rect(shape,q['x_um'],q['y_um'],q['rotation_deg'])
            layer_map[net]=layer_base;clearance[net]=rules['min_signal_gap_um']
        jw=min(gap*.9, max(2.,s['junction_process']['linewidth_um']*4))
        marker=_rect(-jw/2,-max(1.,s['junction_process']['linewidth_um']),jw/2,max(1.,s['junction_process']['linewidth_um']))
        jj_ports[q['junction_id']]=_rotate_rect(marker,q['x_um'],q['y_um'],q['rotation_deg'])
        # Process-intent polygons: two independent lithographic exposure shapes.
        # The actual Dolan double-angle shadow projection depends on resist,
        # evaporation angles, bias and undercut, none of which is inferred here.
        from shapely import affinity
        proc=s['junction_process'];linewidth=proc['linewidth_um'];overlap=proc['overlap_um']
        span=max(2.,proc['lead_extension_um']*2+overlap)
        if proc['method']=='dolan':
            features=[('bridge_exposure',_rect(-span/2,-linewidth/2,span/2,linewidth/2)),
                      ('undercut_intent',_rect(-overlap/2,-(linewidth+2*proc['undercut_um'])/2,
                                                      overlap/2,(linewidth+2*proc['undercut_um'])/2))]
        elif proc['method']=='manhattan':
            features=[('first_evaporation_intent',_rect(-span/2,-linewidth/2,span/2,linewidth/2)),
                      ('second_evaporation_intent',_rect(-linewidth/2,-span/2,linewidth/2,span/2))]
        else:
            features=[('junction_marker',_rect(-overlap/2,-linewidth/2,overlap/2,linewidth/2))]
        for fid,poly in features:
            poly=affinity.rotate(poly,proc['orientation_deg'],origin=(0,0))
            poly=_rotate_rect(poly,q['x_um'],q['y_um'],q['rotation_deg'])
            process_features.append({'junction_id':q['junction_id'],'feature':fid,
                         'points_um':[[round(float(x),6),round(float(y),6)] for x,y in list(poly.exterior.coords)[:-1]],
                         'gds_datatype_offset':0 if fid.endswith(('exposure','intent')) and fid in ('bridge_exposure','first_evaporation_intent') else 1})
        components.append({'id':q['id'],'family':q['family'],'pins':{p:list(_midpoint(q,p)) for p in ('east','west','north','south')},
                           'junction_id':q['junction_id'],'islands':[q['id']+'.pad_a',q['id']+'.pad_b']})
    for c in s['couplers']:
        qa,pina=c['a'].split('.');qb,pinb=c['b'].split('.')
        A=qmap[qa];B=qmap[qb];a=_midpoint(A,pina);b=_midpoint(B,pinb)
        # Directed antipodal ports must face each other; orthogonal turns are routes, not hidden couplers.
        is_horizontal=abs(a[1]-b[1])<1e-5
        is_vertical=abs(a[0]-b[0])<1e-5
        if not(is_horizontal or is_vertical):raise ValueError(c['id']+': coupler pins must be axis-aligned; change positions/rotation')
        dist=abs(b[0]-a[0])+abs(b[1]-a[1]);gap=c['gap_um'];width=c['finger_width_um']
        if dist<=gap+10:raise ValueError(c['id']+': too little room for coupling fingers')
        sign=1 if (b[0]-a[0] if is_horizontal else b[1]-a[1])>0 else -1
        midpoint=((a[0]+b[0])/2,(a[1]+b[1])/2)
        aa=(midpoint[0]-sign*gap/2,midpoint[1]) if is_horizontal else (midpoint[0],midpoint[1]-sign*gap/2)
        bb=(midpoint[0]+sign*gap/2,midpoint[1]) if is_horizontal else (midpoint[0],midpoint[1]+sign*gap/2)
        net_a=_island(A,pina);net_b=_island(B,pinb)
        if c['kind']=='custom_rects':
            # User-defined local electrode rectangles: u axis from A toward B,
            # v axis transverse. No silently added wires or invented topology.
            from shapely.geometry import Polygon
            def custom_rect(rect):
                x0,y0,x1,y1=rect
                def pos(u,v):
                    return (midpoint[0]+sign*u,midpoint[1]+v) if is_horizontal else (midpoint[0]+v,midpoint[1]+sign*u)
                return Polygon([pos(*xy) for xy in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))])
            pa=unary_union([custom_rect(r) for r in c['electrodes']['a']])
            pb=unary_union([custom_rect(r) for r in c['electrodes']['b']])
            if not metal[net_a].union(pa).geom_type=='Polygon' or not metal[net_b].union(pb).geom_type=='Polygon':
                raise ValueError('Custom coupler electrodes must physically connect to their named qubit islands')
        elif c['kind']=='interdigitated':
            # True alternating combs: separate left/right backbones and fingers.
            # Finger clearance is at least the user-selected gap in both axes.
            number=c.get('fingers',3);pitch=width+gap
            halfspan=(number-1)*pitch/2+width/2
            span=max(5*width+2*gap,90.)
            if dist< span+gap+30:raise ValueError(c['id']+': insufficient coupler length for interdigitated comb')
            # Transform local (longitudinal, transverse) coordinates onto axis.
            def pos(u,v):
                return (midpoint[0]+sign*u,midpoint[1]+v) if is_horizontal else (midpoint[0]+v,midpoint[1]+sign*u)
            def stripe(u0,v0,u1,v1):
                corners=[pos(u,v) for u,v in ((u0,v0),(u1,v0),(u1,v1),(u0,v1))]
                from shapely.geometry import Polygon
                return Polygon(corners)
            left=-span/2;right=span/2
            a_parts=[stripe(left-width/2,-halfspan,left+width/2,halfspan)]
            b_parts=[stripe(right-width/2,-halfspan,right+width/2,halfspan)]
            for k in range(number):
                v=(k-(number-1)/2)*pitch
                if k%2==0:a_parts.append(stripe(left,v-width/2,right-width/2-gap,v+width/2))
                else:b_parts.append(stripe(left+width/2+gap,v-width/2,right,v+width/2))
            # Attach the comb backbones to opposite pads with butt-ended traces.
            pa=unary_union(a_parts+[LineString([a,pos(left,0)]).buffer(width/2,cap_style=2,join_style=2)])
            pb=unary_union(b_parts+[LineString([b,pos(right,0)]).buffer(width/2,cap_style=2,join_style=2)])
        elif c['kind']=='bus_cpw':
            lead=min(140.,dist*.16)
            if dist <= 2*lead+2*gap+2*width:
                raise ValueError(c['id']+': insufficient length for isolated CPW bus')
            def advance(pt,direction):
                return (pt[0]+sign*direction,pt[1]) if is_horizontal else (pt[0],pt[1]+sign*direction)
            a_tip=advance(a,lead);b_tip=advance(b,-lead)
            bus_left=advance(a,lead+gap);bus_right=advance(b,-lead-gap)
            pa=LineString([a,a_tip]).buffer(width/2,cap_style=2,join_style=2)
            pb=LineString([b,b_tip]).buffer(width/2,cap_style=2,join_style=2)
            bus_name=c['id']+'.bus'
            if bus_name in metal:raise ValueError('Duplicate bus net '+bus_name)
            metal[bus_name]=LineString([bus_left,bus_right]).buffer(width/2,cap_style=2,join_style=2)
            layer_map[bus_name]=layer_base
            clearance[bus_name]=max(gap,rules['min_signal_gap_um'])
        else:
            pa=LineString([a,aa]).buffer(width/2,cap_style=2,join_style=2)
            pb=LineString([b,bb]).buffer(width/2,cap_style=2,join_style=2)
        metal[net_a]=unary_union([metal[net_a],pa]);metal[net_b]=unary_union([metal[net_b],pb])
        rec={'id':c['id'],'kind':c['kind'],'islands':[net_a,net_b],
             'gap_um':gap,'nominal_c_ff':c['nominal_c_ff'],
             'electrical_assumption':'user-declared nominal; not FEM extracted',
             'design_verified':('user_supplied_connected_rectangles' if c['kind']=='custom_rects' else 'interdigitated comb electrodes' if c['kind']=='interdigitated' else 'two separated positive-metal fingers')}
        if c['kind']=='bus_cpw':
            rec['bus_net']=bus_name
            rec['design_verified']='continuous isolated CPW bus between two coupling fingers; distributed propagation not extracted'
        if c['kind']=='tunable_squid' or (c['kind']=='custom_rects' and c.get('electrical_model')=='SQUID'):
            name=c['id']+'.junction';orientation='x' if is_horizontal else 'y'
            port=_rect(midpoint[0]-gap/2,midpoint[1]-width/4,midpoint[0]+gap/2,midpoint[1]+width/4) if is_horizontal else _rect(midpoint[0]-width/4,midpoint[1]-gap/2,midpoint[0]+width/4,midpoint[1]+gap/2)
            jj_ports[name]=port
            rec['ej_ghz']=c.get('ej_ghz',8.);rec['design_verified']='single linearized effective SQUID marker; loop masks not fabricated'
        coupler_records.append(rec)
        connectivity.append({'kind':c['kind'],'id':c['id'],'from':net_a,'to':net_b,'galvanic':False})
    route_manifest=[]
    for r in s['routes']:
        pts=_path_points(r);shape=_path_shape(pts,r['width_um']);net=r['net'];
        if net in metal and layer_map[net]!=r['layer']:raise ValueError('Net spans layers without an explicit via: '+net)
        metal[net]=unary_union([metal[net],shape]) if net in metal else shape
        layer_map[net]=r['layer'];clearance[net]=max(clearance.get(net,0),r['gap_um'])
        route_manifest.append({'id':r['id'],'net':net,'layer':r['layer'],
           'style':r['style'],'points_um':[list(p) for p in pts],
           'length_um':round(sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for a,b in zip(pts,pts[1:])),6),
           'width_um':r['width_um'],'gap_um':r['gap_um']})
    # Physical constraints check positive-metal distance on every same-layer net.
    names=list(metal)
    for i,na in enumerate(names):
        if not allowed.covers(metal[na]):raise ValueError(f'{na}: metal violates chip edge keepout')
        for nb in names[i+1:]:
            if layer_map[na]!=layer_map[nb]:continue
            required=rules['min_signal_gap_um']
            if metal[na].distance(metal[nb])+1e-7 < required:
                raise ValueError(f'DRC short/insufficient gap {na} ↔ {nb}; distance={metal[na].distance(metal[nb]):.3f} um')
    # Generate a real continuous ground plane, with ALL signal clearance removed.
    conductor_layers=[l['id'] for l in s['stack'] if l['role']=='conductor']
    ground_by_layer={}
    for lid in conductor_layers:
        cut=[poly.buffer(clearance[n],cap_style=3,join_style=2) for n,poly in metal.items() if layer_map[n]==lid]
        ground_by_layer[lid]=allowed.difference(unary_union(cut)) if cut else allowed
    rects={'ground':_rectangles(ground_by_layer[layer_base])}
    rects.update({name:_rectangles(shape) for name,shape in metal.items()})
    # Additional ground nets, if multiple conductor planes, are separate attributes.
    for lid,shape in ground_by_layer.items():
        if lid!=layer_base:rects['ground.'+lid]=_rectangles(shape)
    if any(not rs for rs in rects.values()):raise ValueError('Empty conductor/net')
    ports={k:_bounding_rect(shape) for k,shape in jj_ports.items()}
    port_ids=[r['id']+'.start' for r in route_manifest]+[r['id']+'.end' for r in route_manifest]
    for r in route_manifest:
        p0,p1=r['points_um'][0],r['points_um'][-1];wd=r['width_um']
        for suffix,p in [('start',p0),('end',p1)]:
            ports[r['id']+'.'+suffix]={'x0':p[0]-wd/2,'y0':p[1]-wd/2,
                                     'x1':p[0]+wd/2,'y1':p[1]+wd/2}
    tags={'air':1,'outer':99}
    for i,l in enumerate([l for l in s['stack'] if l['role']=='dielectric']):tags[l['id']]=2+i
    tags.update({name:100+i for i,name in enumerate(rects)})
    tags.update({name:1000+i for i,name in enumerate(ports)})
    result={'schema_version':3,'units':'um','topology':'user_defined_graph',
       'chip':{'x0':-hw,'y0':-hh,'x1':hw,'y1':hh},'metal':rects,'metal_layers':{
         **{name:layer_map[name] for name in metal},
         **{'ground':layer_base},**{'ground.'+k:k for k in conductor_layers if k!=layer_base}},
       'ports':ports,'components':components,
       'junctions':[{'id':q['junction_id'],'port':q['junction_id'],
                     'islands':[q['id']+'.pad_a',q['id']+'.pad_b'],
                     'ej_ghz':q['ej_ghz'],'cj_ff':q['cj_ff'],
                     'process':s['junction_process']['method']} for q in s['qubits']],
       'feed_ports':[{'id':n,'surface':n,'net':r['net'],'impedance_ohm':50.}
                     for r in route_manifest for n in (r['id']+'.start',r['id']+'.end')],
       'terminals':[k for k in rects if not k.startswith('ground')],
       'physical_tags':tags,'stack':deepcopy(s['stack']),'materials':deepcopy(s['materials']),
       'junction_process':deepcopy(s['junction_process']),'process_features':process_features,
       'couplers':coupler_records,'connections':connectivity,'routes':route_manifest,
       'design_spec_sha256':digest(s),'fabrication_status':'HOLD',
       'designed_interqubit_couplers':len(coupler_records),
       'limitations':['Planar axis-aligned geometries; no via/airbridge connectivity',
           'Dolan and Manhattan mask parameters are process intent, not calibrated evaporation masks',
           'Bus CPW / tunable couplers are not fully resolved 3D circuit models',
           'Conductor thickness and surface oxides not yet represented as meshed finite-thickness solids',
           'Routes are waypoints/manhattan/meanders, not a general obstacle-avoiding autorouter']}
    result['geometry_sha256']=digest({k:result[k] for k in ('units','chip','metal','metal_layers','ports','physical_tags','stack','process_features')})
    return result


def _bounding_rect(poly):
    x0,y0,x1,y1=poly.bounds
    return {'x0':round(x0,6),'y0':round(y0,6),'x1':round(x1,6),'y1':round(y1,6)}


def qmetal_manifest(g):
    layers={x['id']:x for x in g['stack']}
    data={'schema_version':2,'format':'sqe-positive-mask-orthogonal',
          'geometry_sha256':g['geometry_sha256'],'coordinates':'millimeters',
          'components':[{'name':k,'layer':layers[g['metal_layers'][k]]['gds_layer'],
             'attribute':g['physical_tags'][k],'subtract':False,
             'rectangles_mm':[[r[f]/1000 for f in ('x0','y0','x1','y1')] for r in vals]}
             for k,vals in g['metal'].items()],
          'ports':[{'name':k,'rectangle_mm':[r[f]/1000 for f in ('x0','y0','x1','y1')]}
                   for k,r in g['ports'].items()],
          'stack':g['stack'],'junction_process':g['junction_process'],
          'process_features':g['process_features'],
          'notes':['All rectangles derive from the exact clipped design geometry',
                   'Two-port pin semantics require review in Quantum Metal',
                   'No mask fabrication qualification']}
    data['manifest_sha256']=digest(data)
    return data


def export_gds(g,path):
    layers={l['id']:l for l in g['stack']}
    rectangles=[]
    for name,rs in g['metal'].items():
        l=layers[g['metal_layers'][name]]
        rectangles.extend((Rect(**r),l['gds_layer'],l.get('gds_datatype',0)) for r in rs)
    jl=next(l for l in g['stack'] if l['id']==g['junction_process']['junction_layer_id'])
    for name,r in g['ports'].items():
        if name in {j['port'] for j in g['junctions']} or name.endswith('.junction'):
            rectangles.append((Rect(**r),jl['gds_layer'],jl.get('gds_datatype',0)))
        else:rectangles.append((Rect(**r),92,0))
    process_polygons=[(f['points_um'],jl['gds_layer'],
         min(32767,jl.get('gds_datatype',0)+f['gds_datatype_offset']))
         for f in g['process_features']]
    cad.write_library(path,[{'name':'SQE_PARAMETRIC_HOLD','rectangles':rectangles,
                             'polygons':process_polygons}])
    return str(path)


def circuit(cfg,s):
    validate_spec(s)
    q=s['qubits'];nom=s['nominal'];elements=[];qubits=[];positions={}
    for i,item in enumerate(q):
        node='q'+str(i);rn='r'+str(i)
        positions[node]=[item['x_um'],item['y_um']]
        positions[rn]=[item['x_um'],item['y_um']-220]
        elements += [{'id':'Cq'+str(i),'kind':'C','a':node,'b':'0','value':nom['cq_ff']},
                     {'id':item['junction_id'],'kind':'JJ','a':node,'b':'0','ej_ghz':item['ej_ghz']},
                     {'id':'Cr'+str(i),'kind':'C','a':rn,'b':'0','value':nom['cr_ff']},
                     {'id':'Lr'+str(i),'kind':'L','a':rn,'b':'0','value':nom['lr_nh']},
                     {'id':'Cqr'+str(i),'kind':'C','a':node,'b':rn,'value':nom['cqr_ff']}]
        qubits.append({'id':item['id'],'junction':item['junction_id'],'node':node,
                       'target_ghz':5+i*.07,'tolerance_mhz':500.})
    nodes={item['id']:'q'+str(i) for i,item in enumerate(q)}
    for c in s['couplers']:
        a=nodes[c['a'].split('.')[0]];b=nodes[c['b'].split('.')[0]]
        if c['kind']=='tunable_squid' or (c['kind']=='custom_rects' and c.get('electrical_model')=='SQUID'):
            elements.append({'id':'K_'+c['id'],'kind':'SQUID','a':a,'b':b,
                             'ej_ghz':c.get('ej_ghz',8.),'asymmetry':.1,'flux_phi0':0})
        elif c['kind']=='bus_cpw':
            node='bus_'+c['id']
            positions[node]=[(positions[a][0]+positions[b][0])/2,(positions[a][1]+positions[b][1])/2]
            elements.extend([{'id':'K_'+c['id']+'_A','kind':'C','a':a,'b':node,'value':c['nominal_c_ff']},
                {'id':'K_'+c['id']+'_B','kind':'C','a':b,'b':node,'value':c['nominal_c_ff']},
                {'id':'K_'+c['id']+'_C','kind':'C','a':node,'b':'0','value':nom['cr_ff']},
                {'id':'K_'+c['id']+'_L','kind':'L','a':node,'b':'0','value':nom['lr_nh']}])
        else:
            elements.append({'id':'K_'+c['id'],'kind':'C','a':a,'b':b,'value':c['nominal_c_ff']})
    ports=[{'id':'P1','node':'r0','z0_ohm':50.,'coupling_ff':nom['port_c_ff']}]
    if len(q)>1:ports.append({'id':'P2','node':'r'+str(len(q)-1),'z0_ohm':50.,'coupling_ff':nom['port_c_ff']})
    data={'schema_version':1,'name':s.get('name','QPU physical graph'),
      'model':'nominal_graph_from_physical_coupler_edges__NOT_EM_EXTRACTED',
      'elements':elements,'qubits':qubits,'positions':positions,'ports':ports,
      'chip':{'width_um':s['chip']['width_um'],'height_um':s['chip']['height_um'],
               'metal_layer':next(x['gds_layer'] for x in s['stack'] if x['role']=='conductor'),
               'junction_layer':next(x['gds_layer'] for x in s['stack'] if x['role']=='junction_mask'),
               'min_gap_um':s['design_rules']['min_signal_gap_um']},
      'notes':'Graph connections match coupler declarations; C, L, g and EJ are unmeasured/user-defined; CPW route distributed parameters are not reduced automatically.'}
    quantumlab.validate(data)
    return data


def palace_configs(cfg,s,g):
    """Generate conservative Palace input. Multilayer geometry needs mesh verification.

    Domain assignments and geometry tags share the design contract. Boundary
    configurations are generator outputs and MUST pass a native Palace preflight.
    """
    from .physical_qpu import PHI0
    from scipy.constants import h,pi
    tags=g['physical_tags'];emcfg=cfg['em']
    domains=[{'Attributes':[tags['air']],'Permittivity':1.}]
    for l in s['stack']:
        if l['role']=='dielectric':
            mat=s['materials'][l['material']]
            d={'Attributes':[tags[l['id']]],'Permittivity':mat['epsilon_r']}
            if mat.get('loss_tangent'):d['LossTan']=mat['loss_tangent']
            domains.append(d)
    base={'Model':{'Mesh':'device.msh','L0':1e-6},'Domains':{'Materials':domains}}
    ports=[{'Index':i+1,'Attributes':[tags[p['surface']]],'Direction':'+Y','R':p['impedance_ohm']}
           for i,p in enumerate(g['feed_ports'])]
    jj=[]
    for i,j in enumerate(g['junctions']):
        lj=PHI0**2/(4*pi*pi*h*j['ej_ghz']*1e9)
        jj.append({'Index':100+i,'Attributes':[tags[j['port']]],'Direction':'+X',
                   'L':lj,'C':j['cj_ff']*1e-15})
    for i,c in enumerate(g['couplers']):
        if c['kind']=='tunable_squid' or (c['kind']=='custom_rects' and c.get('electrical_model')=='SQUID'):
            if c['id']+'.junction' not in tags:raise ValueError('Missing tunable coupler port')
            lj=PHI0**2/(4*pi*pi*h*c['ej_ghz']*1e9)
            jj.append({'Index':300+i,'Attributes':[tags[c['id']+'.junction']],
                       'Direction':'+X','L':lj})
    linear={'Type':'SuperLU','KSPType':'FGMRES','Tol':emcfg['linear_tol'],'MaxIts':500}
    conductor_attrs=[tags[x] for x in g['metal']]
    static={'Problem':{'Type':'Electrostatic','Output':'electrostatic'},**deepcopy(base),
            'Boundaries':{'Ground':{'Attributes':[tags['ground'],tags['outer']]},
             'Terminal':[{'Index':i+1,'Attributes':[tags[n]]} for i,n in enumerate(g['terminals'])]},
            'Solver':{'Order':emcfg['order'],'Electrostatic':{'Save':0},
                      'Linear':{'Type':'BoomerAMG','KSPType':'CG','Tol':emcfg['linear_tol'],'MaxIts':500}}}
    eigen={'Problem':{'Type':'Eigenmode','Output':'eigenmode'},**deepcopy(base),
         'Boundaries':{'PEC':{'Attributes':conductor_attrs+[tags['outer']]},'LumpedPort':ports+jj},
         'Solver':{'Order':emcfg['order'],'Eigenmode':{'Target':emcfg['eigen_target_GHz'],
          'N':emcfg['modes'],'Save':emcfg['modes'],'Tol':1e-7},'Linear':linear}}
    result={'electrostatic':static,'eigenmode':eigen}
    for i in range(len(ports)):
        d=deepcopy(eigen);name=f'driven-{i+1}';d['Problem']={'Type':'Driven','Output':name}
        d['Solver'].pop('Eigenmode')
        d['Solver']['Driven']={'Samples':[{'Type':'Linear','MinFreq':cfg['device']['band_min_GHz'],
                  'MaxFreq':cfg['device']['band_max_GHz'],'NSample':61,'SaveStep':0}]}
        for p in d['Boundaries']['LumpedPort']:p['Excitation']=int(p['Index']==i+1)
        result[name]=d
    return result


def export_package(cfg,s,out,*,with_gds=True):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    g=build(cfg,s);configs=palace_configs(cfg,s,g);nominal=circuit(cfg,s)
    for name,content in [('physical_spec',s),('geometry',g),('nominal_circuit',nominal),
                         ('qmetal',qmetal_manifest(g)),('materials',s['materials']),
                         ('stackup',s['stack']),('routes',g['routes']),
                         ('couplers',g['couplers'])]:write_json(out/(name+'.json'),content)
    for name,config in configs.items():write_json(out/(name+'.json'),config)
    contract={'schema_version':3,'geometry_sha256':g['geometry_sha256'],
        'design_spec_sha256':g['design_spec_sha256'],'terminal_order':g['terminals'],
        'port_order':[p['id'] for p in g['feed_ports']],
        'junction_order':[j['id'] for j in g['junctions']],
        'tag_map':g['physical_tags'],'stack_sha256':digest(s['stack']),
        'materials_sha256':digest(s['materials']),'palace_configs':list(configs),
        'C_source':'not_extracted','circuit_source':'user_declared_nominal_parameters',
        'mask_status':'HOLD','electromagnetic_status':'NOT_SOLVED',
        'fem_limitations':g['limitations']}
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
    if with_gds:export_gds(g,out/'physical_HOLD.gds')
    return {'geometry':g,'contract':contract,'nominal_circuit':nominal}


def mesh(cfg,g,out):
    """Multi-dielectric planar Gmsh mesh with sheet-metal physical groups.

    No thickness-based metal volume is claimed. Only supported when the base
    conductor lies on the uppermost dielectric interface at z=0.
    """
    import gmsh
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    layers=g['stack'];conductor=[l for l in layers if l['role']=='conductor']
    dielectrics=sorted([l for l in layers if l['role']=='dielectric'],key=lambda l:l['z0_um'])
    if len(conductor)!=1 or abs(conductor[0]['z0_um'])>1e-9:
        raise ValueError('Palace mesh currently supports exactly one planar conductor sheet at z=0; multilayer mask export remains supported')
    if abs(dielectrics[-1]['z0_um']+dielectrics[-1]['thickness_um'])>1e-7:
        raise ValueError('Uppermost dielectric must end at z=0 for this Palace mesher')
    for x,y in zip(dielectrics,dielectrics[1:]):
        if abs(x['z0_um']+x['thickness_um']-y['z0_um'])>1e-7:
            raise ValueError('Palace dielectric stack must be contiguous')
    gmsh.initialize()
    try:
        gmsh.model.add('sqe_parametric_qpu');occ=gmsh.model.occ
        c=g['chip']; margin=cfg['em']['box_margin_um'];airh=cfg['em']['air_height_um'];bottom=cfg['em']['bottom_air_um']
        x0=c['x0']-margin;y0=c['y0']-margin;w=c['x1']-c['x0']+2*margin;h=c['y1']-c['y0']+2*margin
        zb=dielectrics[0]['z0_um']-bottom
        air=occ.addBox(x0,y0,zb,w,h,airh-zb)
        volumes=[(3,air)];names=['air']
        for d in dielectrics:
            v=occ.addBox(c['x0'],c['y0'],d['z0_um'],c['x1']-c['x0'],c['y1']-c['y0'],d['thickness_um'])
            volumes.append((3,v));names.append(d['id'])
        sheets=[];sheet_names=[]
        for name,rects in list(g['metal'].items())+[(k,[v]) for k,v in g['ports'].items()]:
            for r in rects:
                t=occ.addRectangle(r['x0'],r['y0'],0,r['x1']-r['x0'],r['y1']-r['y0'])
                sheets.append((2,t));sheet_names.append(name)
        # Fragment material domains and conductor sheets together.
        _,mapping=occ.fragment([volumes[0]],volumes[1:]+sheets)
        occ.synchronize()
        domain_groups={}
        for i,name in enumerate(names):
            domain_groups[name]={t for d,t in mapping[i] if d==3}
        for name in names[1:]:domain_groups['air']-=domain_groups[name]
        sheet_groups={}
        for i,name in enumerate(sheet_names):
            for dim,tag in mapping[len(volumes)+i]:
                if dim==2:sheet_groups.setdefault(name,set()).add(tag)
        outer=[];tol=1e-4
        for dim,tag in gmsh.model.getEntities(2):
            bb=gmsh.model.getBoundingBox(dim,tag)
            for ax,plane in ((0,x0),(0,x0+w),(1,y0),(1,y0+h),(2,zb),(2,airh)):
                if abs(bb[ax]-plane)<tol and abs(bb[ax+3]-plane)<tol:
                    outer.append(tag);break
        sheet_groups['outer']=set(outer)
        for name,group in domain_groups.items():
            if not group:raise ValueError('Missing Gmsh material volume '+name)
            gmsh.model.addPhysicalGroup(3,sorted(group),g['physical_tags'][name],name)
        for name in g['physical_tags']:
            if name in domain_groups:continue
            group=sheet_groups.get(name)
            if not group:raise ValueError('Missing Gmsh boundary '+name)
            gmsh.model.addPhysicalGroup(2,sorted(group),g['physical_tags'][name],name)
        gmsh.option.setNumber('Mesh.MeshSizeMax',cfg['em']['mesh_max_um'])
        gmsh.option.setNumber('Mesh.MeshSizeMin',cfg['em']['mesh_min_um'])
        gmsh.option.setNumber('Mesh.MshFileVersion',2.2)
        gmsh.model.mesh.generate(3)
        gmsh.write(str(out/'device.msh'))
        from .io import sha256
        record={'geometry_sha256':g['geometry_sha256'],'mesh_sha256':sha256(out/'device.msh'),
            'nodes':len(gmsh.model.mesh.getNodes()[0]),
            'volume_elements':sum(len(tags) for tags in gmsh.model.mesh.getElements(3)[1]),
            'physical_groups':{**{k:sorted(v) for k,v in domain_groups.items()},
                               **{k:sorted(v) for k,v in sheet_groups.items()}},'units':'um',
            'fidelity':'multi_dielectric_zero_thickness_planar_sheets'}
        write_json(out/'mesh.json',record)
        return record
    finally:gmsh.finalize()


def run_workflow(cfg,s,stage,out,*,ranks=1,executable='palace'):
    from . import physical_qpu
    from .io import sha256
    out=Path(out);art=export_package(cfg,s,out)
    stages={'package','mesh','electrostatic','capacitance','eigenmode','driven','convergence-eigenmode','convergence-electrostatic'}
    if stage not in stages:raise ValueError('Unsupported physical workflow stage')
    result={'stage':stage,'status':'completed','geometry_sha256':art['geometry']['geometry_sha256'],
            'fabrication_status':'HOLD',
            'fidelity':'geometry_contract_only' if stage=='package' else 'actual_Palace_output_required'}
    if stage!='package':
        mesh(cfg,art['geometry'],out)
        result['mesh_sha256']=sha256(out/'device.msh')
    if stage in ('electrostatic','capacitance'):
        physical_qpu.solve(out,['electrostatic'],ranks,executable)
    if stage=='capacitance':
        # General graph reduction cannot assume v0.6 Q{i}.pad_* naming.
        result['capacitance_file']='electrostatic/terminal-C.csv'
        result['capacitance_projection']='manual until named graph transform implemented'
    if stage=='eigenmode':physical_qpu.solve(out,['eigenmode'],ranks,executable)
    if stage.startswith('convergence-'):
        from .palace_quality import run as run_convergence
        report=run_convergence(out,stage.removeprefix('convergence-'),ranks=ranks,executable=executable)
        result['convergence_report']=f'{stage}-report.json'
        result['numerically_converged']=report['numerically_converged']
        result['scientifically_qualified']=report['scientifically_qualified']
        result['fidelity']='real_palace_convergence_required__no_mode_overlap'
    if stage=='driven':
        names=[k for k in art['contract']['palace_configs'] if k.startswith('driven-')]
        physical_qpu.solve(out,names,ranks,executable)
        result['sparameter_columns']={k:k+'/port-S.csv' for k in names}
    write_json(out/'result.json',result)
    (out/'result.sha256').write_text(sha256(out/'result.json')+'\n',encoding='ascii')
    return result
