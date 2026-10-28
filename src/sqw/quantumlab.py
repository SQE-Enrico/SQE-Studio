"""Open Quantum Design Lab: deterministic reduced-order quantum and microwave analyses.

This module NEVER calls a lumped model an EM/FEM/MoM field solve. Units in the
portable document are fF, nH, GHz, kelvin, microseconds and a flux quantum.
All numerical quantities are converted to SI before assembly.
"""
from __future__ import annotations

import copy
import math

import numpy as np
from scipy.constants import h, hbar, physical_constants, pi
from scipy.linalg import eigh
from scipy.integrate import solve_ivp
from scipy.optimize import minimize_scalar

PHI0 = physical_constants['mag. flux quantum'][0]
ALLOWED = {'C', 'L', 'R', 'JJ', 'SQUID'}
ANALYSES = ('modes', 'sparameters', 'flux', 'dynamics', 'yield', 'duffing', 'design_checks', 'optimize', 'loss_budget')


def preset(size=1):
    """Topology-only starting design; geometry is a separately verified workflow."""
    if size not in (1, 4, 9, 16):
        raise ValueError('Supported QPU template sizes: 1, 4, 9, 16 qubits')
    elements = []
    qubits = []
    positions = {}
    side = int(math.ceil(math.sqrt(size)))
    for i in range(size):
        x, y = (i % side) * 200, (i // side) * 250
        positions[f'q{i}'] = [100+x, 100+y]
        positions[f'r{i}'] = [100+x, 170+y]
        elements.extend([
            {'id': f'Cq{i}', 'kind': 'C', 'a': f'q{i}', 'b': '0', 'value': 78.0 + i * 0.5},
            {'id': f'J{i}', 'kind': 'JJ', 'a': f'q{i}', 'b': '0', 'ej_ghz': 13.0 + i * 0.32},
            {'id': f'Cr{i}', 'kind': 'C', 'a': f'r{i}', 'b': '0', 'value': 70.0},
            {'id': f'Lr{i}', 'kind': 'L', 'a': f'r{i}', 'b': '0', 'value': 8.0 + i * 0.12},
            {'id': f'Cqr{i}', 'kind': 'C', 'a': f'q{i}', 'b': f'r{i}', 'value': 3.5},
        ])
        qubits.append({'id': f'Q{i}', 'junction': f'J{i}', 'node': f'q{i}',
                       'target_ghz': 5.0 + i * 0.07, 'tolerance_mhz': 500.0})
    for i in range(size):
        for j in range(i+1, size):
            if (j == i+1 and i//side == j//side) or j == i+side:
                elements.append({'id': f'Cg{i}_{j}', 'kind': 'C',
                                 'a': f'q{i}', 'b': f'q{j}', 'value': 0.35})
    return {'schema_version': 1, 'name': f'{size}-transmon superconducting QPU',
            'model': 'lumped_linearization_plus_weak_Josephson_quartic',
            'elements': elements, 'qubits': qubits, 'positions': positions,
            'ports': [
                {'id': 'P1', 'node': 'r0', 'z0_ohm': 50.0, 'coupling_ff': 2.0},
                {'id': 'P2', 'node': f'r{size-1}', 'z0_ohm': 50.0, 'coupling_ff': 2.0},
            ], 'chip': {'width_um': max(1500, 400*side), 'height_um': max(1500, 430*side),
                       'metal_layer': 1, 'junction_layer': 91, 'min_gap_um': 2},
            'notes': 'Electrical graph, not a validated lithography layout.'}


def validate(design):
    if not isinstance(design, dict) or not isinstance(design.get('elements'), list):
        raise ValueError('Design must contain a list of elements')
    elements = design['elements']
    if not 1 <= len(elements) <= 240:
        raise ValueError('Use 1–240 elements per reduced-order model')
    ids, nodes = set(), set()
    for element in elements:
        if not isinstance(element, dict): raise ValueError('Every element must be an object')
        kind, ident = element.get('kind'), element.get('id')
        if kind not in ALLOWED: raise ValueError(f'Unsupported element type: {kind}')
        if not isinstance(ident, str) or not (1 <= len(ident) <= 60) or ident in ids:
            raise ValueError('Element IDs must be distinct and 1–60 characters')
        ids.add(ident)
        for pin in ('a', 'b'):
            value = element.get(pin)
            if not isinstance(value, str) or not (1 <= len(value) <= 48):
                raise ValueError('Element node identifiers must be short strings')
            if value != '0': nodes.add(value)
        if element['a'] == element['b']: raise ValueError(f'{ident}: both pins connect to same node')
        fields = {'C': ('value',), 'L': ('value',), 'R': ('value',),
                  'JJ': ('ej_ghz',), 'SQUID': ('ej_ghz', 'asymmetry', 'flux_phi0')}[kind]
        for field in fields:
            val = element.get(field)
            if type(val) not in (int, float) or not math.isfinite(val):
                raise ValueError(f'{ident}: {field} must be finite')
            if (field not in ('flux_phi0', 'asymmetry') and not 0 < val < 1e9) or (field == 'asymmetry' and not 0 <= val < 1):
                raise ValueError(f'{ident}: {field} out of range')
        if kind == 'R' and element['value'] < 0.001: raise ValueError(f'{ident}: resistance too small')
    if not nodes or len(nodes) > 64: raise ValueError('Use 1–64 distinct non-ground nodes')
    ports = design.get('ports', [])
    if not isinstance(ports, list) or len(ports)>8: raise ValueError('At most eight RF ports')
    port_ids=set()
    for port in ports:
        if not isinstance(port,dict) or port.get('node') not in nodes: raise ValueError('Port refers to an unknown node')
        if not isinstance(port.get('id'),str) or port['id'] in port_ids: raise ValueError('Port IDs must be distinct')
        port_ids.add(port['id'])
        for field in ('z0_ohm','coupling_ff'):
            v=port.get(field)
            if type(v) not in (float,int) or not math.isfinite(v) or v<=0: raise ValueError(f'Port {field} must be positive')
    qubits = design.get('qubits', [])
    if not isinstance(qubits, list) or len(qubits)>32: raise ValueError('At most 32 qubit assignments')
    for q in qubits:
        if not isinstance(q,dict) or q.get('junction') not in ids or q.get('node') not in nodes:
            raise ValueError('Qubit references an unknown junction/node')
        if next(x for x in elements if x['id']==q['junction'])['kind'] not in ('JJ','SQUID'):
            raise ValueError('Qubit must reference a JJ or SQUID')
    return sorted(nodes)


def _ej(ej_ghz, flux, asym):
    x=pi*flux
    return float(ej_ghz * np.hypot(np.cos(x), asym*np.sin(x)))


def _branches(design, flux_override=None):
    nodes = validate(design)
    idx = {name:i for i,name in enumerate(nodes)}
    n=len(nodes)
    C=np.zeros((n,n)); K=np.zeros((n,n)); G=np.zeros((n,n))
    jj=[]
    for el in design['elements']:
        v=np.zeros(n)
        if el['a']!='0': v[idx[el['a']]]+=1
        if el['b']!='0': v[idx[el['b']]]-=1
        outer=np.outer(v,v)
        kind=el['kind']
        if kind=='C': C+=el['value']*1e-15*outer
        if kind=='R': G+=outer/el['value']
        if kind=='L': K+=outer/(el['value']*1e-9)
        if kind in ('JJ','SQUID'):
            flux=(el.get('flux_phi0',0) if flux_override is None else flux_override) if kind=='SQUID' else 0
            ej=_ej(el['ej_ghz'],flux,el.get('asymmetry',0)) if kind=='SQUID' else el['ej_ghz']
            if ej>1e-8:
                inductance=PHI0**2/(4*pi*pi*h*ej*1e9)
                K+=outer/inductance
                jj.append((el['id'],v,ej,inductance))
    return nodes,C,K,G,jj


def solve_modes(design, flux_override=None):
    nodes,C,K,G,jjs=_branches(design,flux_override)
    if not np.allclose(C,C.T,rtol=1e-10,atol=0): raise ValueError('Invalid capacitance matrix')
    if np.linalg.eigvalsh(C*1e15).min() <= 1e-10:
        raise ValueError('Capacitance matrix singular; every dynamic node needs finite capacitance to ground or a capacitive path')
    if np.linalg.eigvalsh(K*1e-6).min() <= 1e-12:
        raise ValueError('Inductive stiffness matrix singular; remove floating DC islands or add physical inductive paths')
    w2,U=eigh(K,C)
    if np.min(w2)<=0: raise ValueError('Nonpositive squared eigenfrequency')
    w=np.sqrt(w2)
    modes=[]
    phases=[]; participation=[]
    for k,omega in enumerate(w):
        zpf=np.sqrt(hbar/(2*omega))
        phi=np.array([2*pi/PHI0*np.dot(v,U[:,k])*zpf for _,v,_,_ in jjs])
        p=np.array([(np.dot(v,U[:,k])**2/L)/omega**2 for _,v,_,L in jjs])
        phases.append(phi); participation.append(p)
        modes.append({'index': k, 'frequency_ghz': float(omega/(2*pi*1e9)),
                      'junction_participation': {j[0]:float(p[i]) for i,j in enumerate(jjs)},
                      'node_weights': {node: float(abs(U[i,k])*np.sqrt(C[i,i])) for i,node in enumerate(nodes)}})
    phases=np.asarray(phases)
    ej=np.asarray([j[2] for j in jjs])*1e9
    # Perturbative RWA of -EJ*phi^4/24; Hz converted to GHz.
    alpha= -0.5*np.einsum('j,mj->m',ej,phases**4)/1e9
    chi= -np.einsum('j,mj,nj->mn',ej,phases**2,phases**2)/1e9
    for i,m in enumerate(modes):
        m['anharmonicity_mhz']=float(alpha[i]*1000)
        # First-order vacuum renormalization of the 0->1 transition; a weak-anharmonicity estimate.
        m['estimated_f01_ghz']=float(m['frequency_ghz']+alpha[i]+(sum(chi[i])-chi[i,i])/2)
    assignments={}
    used=set()
    for q in design.get('qubits',[]):
        junction=q['junction']
        options=sorted(range(len(modes)),key=lambda i:modes[i]['junction_participation'].get(junction,0),reverse=True)
        eligible=[i for i in options if i not in used]
        if eligible:
            chosen=eligible[0]; used.add(chosen)
            assignments[q['id']]={'mode_index':chosen,'frequency_ghz':modes[chosen]['estimated_f01_ghz'],
                                   'linear_frequency_ghz':modes[chosen]['frequency_ghz'],
                                   'anharmonicity_mhz':modes[chosen]['anharmonicity_mhz'],
                                   'junction_participation':modes[chosen]['junction_participation'].get(junction,0)}
    return {'analysis':'modes','fidelity':'reduced_order_weak_anharmonicity',
            'modes':modes,'qubit_assignments':assignments,
            'chi_mhz':(chi*1e3 + np.diag((alpha-np.diag(chi))*1e3)).round(7).tolist(), 'C_fF':(C*1e15).round(7).tolist(),
            'nodes':nodes,'assumptions':[
                'Ideal lossless lumped capacitors and inductors in eigenanalysis',
                'JJ/SQUID linearized at a stable phase; fourth-order perturbative RWA',
                'Qubit f01 includes the first-order vacuum quartic shift; mode frequency is linear LC',
                'Chi matrix diagonal is self-anharmonicity; off-diagonal is cross-Kerr. Weak quartic approximation only',
                'Participation refers to circuit branch energy, NOT full-wave electric/magnetic field EPR',
                'No automatic geometric coupling, packaging, substrate, radiation or conductor-loss calculation',
            ]}


def sparameters(design, start_ghz=3.0, stop_ghz=10.0, points=201):
    nodes,C,K,G,_=_branches(design)
    ports=design.get('ports',[])
    if not ports: raise ValueError('Add at least one RF port')
    if not (0<start_ghz<stop_ghz<=100) or not 2<=points<=1201:
        raise ValueError('Frequency limits must satisfy 0 < start < stop <= 100 GHz; points 2–1201')
    ids={n:i for i,n in enumerate(nodes)}
    n=len(nodes); k=len(ports)
    B=np.zeros((n+k,n+k))
    for j,p in enumerate(ports):
        v=np.zeros(n+k); v[ids[p['node']]]+=1; v[n+j]-=1
        B+=p['coupling_ff']*1e-15*np.outer(v,v)
    refs=np.array([p['z0_ohm'] for p in ports])
    root=np.sqrt(refs)
    freq=np.linspace(start_ghz,stop_ghz,points)
    result=[]
    for f in freq:
        w=2*pi*f*1e9
        Y=np.zeros((n+k,n+k),dtype=complex)
        Y[:n,:n]=G+1j*(w*C-K/w)
        Y+=1j*w*B
        Yii=Y[:n,:n]
        # Tiny regularization preserves resonances but prevents a floating network at isolated frequencies.
        Yii+=np.eye(n)*1e-14
        Yp=Y[n:,n:]-Y[n:,:n]@np.linalg.solve(Yii,Y[:n,n:])
        A=(root[:,None]*Yp)*root[None,:]
        S=np.linalg.solve(np.eye(k,dtype=complex)+A,np.eye(k,dtype=complex)-A)
        if not np.all(np.isfinite(S)):raise ValueError('Non-finite scattering response')
        result.append(S)
    arr=np.asarray(result)
    curves=[]
    for i in range(k):
        for j in range(k):
            db=20*np.log10(np.maximum(np.abs(arr[:,i,j]),1e-15))
            curves.append({'name':f'S{i+1}{j+1}', 'db':db.round(5).tolist(),
                           'phase_deg':np.rad2deg(np.unwrap(np.angle(arr[:,i,j]))).round(4).tolist()})
    # Touchstone v1 RI is generated directly from computed complex S values.
    lines=[f'! Quantum Design Lab lumped-network model | {k}-port', '# GHZ S RI R 50']
    if not np.allclose(refs,refs[0]) or refs[0]!=50:
        lines[1]=f'# GHZ S RI R {refs[0]:g}'
    if not np.allclose(refs,refs[0]):
        lines=[] # caller must not export misleading Touchstone v1 for unequal reference impedances
    if lines:
        for f,s in zip(freq,arr):
            # Touchstone two-port order is S11, S21, S12, S22 (column-major).
            vals=[f'{f:.9f}']
            for j in range(k):
                for i in range(k): vals.extend((f'{s[i,j].real:.10e}',f'{s[i,j].imag:.10e}'))
            lines.append(' '.join(vals))
    return {'analysis':'sparameters','fidelity':'linear_lumped_network', 'frequency_ghz':freq.round(7).tolist(),
            'curves':curves,'port_ids':[p['id'] for p in ports],
            'touchstone':'\n'.join(lines)+'\n' if lines else None,
            'assumptions':['Frequency-domain passive, linearized JJ small-signal analysis',
                           'Port coupling is ideal series capacitance; distributed CPW and radiation absent']}


def flux_sweep(design, start=0., stop=1., points=101):
    if not any(e['kind']=='SQUID' for e in design['elements']):
        raise ValueError('Flux sweep requires a SQUID element')
    if not 0<=start<stop<=3 or not 2<=points<=301: raise ValueError('Flux sweep bounds or sample count invalid')
    fluxes=np.linspace(start,stop,points)
    freqs=[]
    for flux in fluxes:
        r=solve_modes(design,float(flux))
        freqs.append([m['frequency_ghz'] for m in r['modes']])
    return {'analysis':'flux','fidelity':'linearized_squid', 'flux_phi0':fluxes.round(6).tolist(),
            'frequency_ghz':np.round(freqs,6).tolist(),
            'assumptions':['Effective-SQUID EJ from interference; no flux-loop inductance or nonlinear phase equilibrium',
                           'Modes sorted by frequency; traces may exchange character near avoided crossings']}


def dynamics(design, qubit=None, sequence='rabi', points=201, duration_us=2.0,
             rabi_mhz=4., detuning_mhz=0.5, t1_us=30., t2_us=20.):
    validate(design)
    assignments=solve_modes(design)['qubit_assignments']
    if not assignments: raise ValueError('At least one qubit assignment is required')
    q=qubit or next(iter(assignments))
    if q not in assignments: raise ValueError('Unknown qubit')
    if sequence not in ('rabi','ramsey','t1','echo'): raise ValueError('Unknown pulse sequence')
    if not (2<=points<=1201 and 0<duration_us<=20000 and 0<t1_us<=1e7 and 0<t2_us<=2*t1_us):
        raise ValueError('Time grid or coherence parameters invalid (T2 must not exceed 2*T1)')
    if not (0<=rabi_mhz<=1000 and -1000<=detuning_mhz<=1000): raise ValueError('Drive parameters invalid')
    gamma1=1/t1_us; gamma2=1/t2_us
    times=np.linspace(0,duration_us,points)
    # Bloch vector x,y,z where p(excited)=(1+z)/2.
    if sequence=='rabi':
        initial=[0,0,-1]
        omega=2*pi*rabi_mhz
        delta=2*pi*detuning_mhz
    elif sequence=='t1':
        initial=[0,0,1]; omega=delta=0
    else:
        initial=[1,0,0]; omega=0; delta=2*pi*detuning_mhz
    def rhs(t,y):
        x,yv,z=y
        d=delta*(-1 if sequence=='echo' and t>=duration_us/2 else 1)
        return [-gamma2*x-d*yv, d*x-gamma2*yv-omega*z, omega*yv-gamma1*(z+1)]
    result=solve_ivp(rhs,(0,duration_us),initial,t_eval=times,rtol=1e-8,atol=1e-10)
    if not result.success:raise ValueError(result.message)
    excited=(1+result.y[2])/2
    if sequence in ('ramsey','echo'):
        excited=(1+result.y[0])/2 # ideal final pi/2 readout rotation
    return {'analysis':'dynamics','fidelity':'two_level_markovian_bloch', 'qubit':q,'sequence':sequence,
            'time_us':times.round(7).tolist(),'p_excited':np.clip(excited,0,1).round(8).tolist(),
            'assumptions':['Rotating-wave two-level master equation with constant T1/T2',
                           'No leakage to |2>, pulse distortion, noise spectrum, control electronics or gate fidelity']}


def yield_analysis(design, count=120, seed=7, ej_sigma_pct=1., c_sigma_pct=1.):
    if not 10<=count<=500 or not 0<=ej_sigma_pct<=30 or not 0<=c_sigma_pct<=30:
        raise ValueError('Yield limits: 10–500 Monte Carlo samples, 0–30% sigma')
    validate(design)
    rng=np.random.default_rng(seed)
    outcomes=[]; frequency_by_qubit={q['id']:[] for q in design.get('qubits',[])}
    for _ in range(count):
        perturbed=copy.deepcopy(design)
        for e in perturbed['elements']:
            if e['kind']=='C': e['value']*=float(np.exp(rng.normal(-0.5*(c_sigma_pct/100)**2,c_sigma_pct/100)))
            if e['kind'] in ('JJ','SQUID'):e['ej_ghz']*=float(np.exp(rng.normal(-0.5*(ej_sigma_pct/100)**2,ej_sigma_pct/100)))
        result=solve_modes(perturbed)
        sample_pass=True
        for q in design.get('qubits',[]):
            assignment=result['qubit_assignments'].get(q['id'])
            f=assignment['frequency_ghz'] if assignment else float('nan')
            frequency_by_qubit[q['id']].append(f)
            if abs(f-q.get('target_ghz',f))*1000 > q.get('tolerance_mhz',250):sample_pass=False
        outcomes.append(sample_pass)
    stats={name:{'mean_ghz':float(np.mean(values)), 'sigma_mhz':float(np.std(values)*1e3),
                 'p05_ghz':float(np.percentile(values,5)), 'p95_ghz':float(np.percentile(values,95))}
           for name,values in frequency_by_qubit.items()}
    return {'analysis':'yield','fidelity':'parametric_monte_carlo','samples':count,'seed':seed,
            'yield_fraction':float(np.mean(outcomes)), 'qubit_statistics':stats,
            'assumptions':['Independent lognormal EJ and C variations only',
                           'Target-window yield; collisions, disorder correlations, defect losses and fabrication constraints omitted']}


def duffing(design, qubit=None, start_ghz=None, stop_ghz=None, points=201,
            linewidth_mhz=2., drive_mhz=0.1):
    result=solve_modes(design)
    assignments=result['qubit_assignments']
    if not assignments: raise ValueError('Assign at least one qubit')
    chosen=assignments.get(qubit or next(iter(assignments)))
    if chosen is None: raise ValueError('Unknown qubit')
    center=chosen['frequency_ghz']; K=chosen['anharmonicity_mhz']
    if start_ghz is None:start_ghz=center-0.03
    if stop_ghz is None:stop_ghz=center+0.03
    if not (0<start_ghz<stop_ghz<=100 and 2<=points<=501 and 0<linewidth_mhz<1e4 and 0<drive_mhz<1e4):
        raise ValueError('Duffing parameter bounds invalid')
    det=np.linspace(start_ghz,stop_ghz,points)*1000-center*1000
    nvals=[]; multi=[]
    for delta in det:
        # one-tone harmonic balance (Kerr/Duffing): n[(kappa/2)^2 + (delta+K*n)^2] = epsilon^2
        co=[K*K,2*delta*K,delta*delta+(linewidth_mhz/2)**2,-drive_mhz**2]
        roots=np.roots(co) if abs(K)>1e-14 else [drive_mhz**2/co[2]]
        good=sorted(float(x.real) for x in roots if abs(x.imag)<1e-7 and x.real>=0)
        nvals.append(good[0] if good else 0.)
        multi.append(len(good))
    return {'analysis':'duffing','fidelity':'one_mode_classical_harmonic_balance',
            'frequency_ghz':(det/1000+center).round(8).tolist(),
            'photon_number_low_branch':np.round(nvals,6).tolist(), 'real_root_count':multi,
            'assumptions':['One-mode rotating-wave Kerr/Duffing approximation, NOT ADS multi-JJ harmonic balance',
                           'Low-amplitude real root selected; bifurcation stability and quantum noise not calculated']}


def design_checks(design):
    validate(design)
    r=solve_modes(design)
    issues=[]
    assigned=r['qubit_assignments']
    for q in design.get('qubits',[]):
        row=assigned.get(q['id'])
        if row and abs(row['frequency_ghz']-q.get('target_ghz',row['frequency_ghz']))*1e3 > q.get('tolerance_mhz',500):
            issues.append({'severity':'warning','item':q['id'],'message':'Qubit frequency outside target tolerance'})
    for i,(name,a) in enumerate(assigned.items()):
        for other,b in list(assigned.items())[i+1:]:
            sep=abs(a['frequency_ghz']-b['frequency_ghz'])*1e3
            if sep < 50:issues.append({'severity':'warning','item':f'{name}/{other}','message':f'Frequency crowding: {sep:.1f} MHz'})
    if any(e['kind']=='R' for e in design['elements']):
        issues.append({'severity':'info','item':'resistors','message':'Dissipation included only in small-signal S-parameters, not eigenmodes'})
    return {'analysis':'design_checks','fidelity':'electrical_graph_precheck',
            'issues':issues,'pass':not any(x['severity']=='error' for x in issues),
            'qubit_assignments':assigned,
            'assumptions':['No geometric DRC, mask sign-off, fabrication qualification or full EM convergence test']}


def optimize(design, qubit=None, min_ej_ghz=4., max_ej_ghz=28.):
    """Single-parameter EJ optimization; returns a proposal, never changes persisted design."""
    validate(design)
    qubits=design.get('qubits',[])
    if not qubits: raise ValueError('Add a target qubit to optimize')
    q=next((q for q in qubits if q['id']==(qubit or qubits[0]['id'])),None)
    if q is None:raise ValueError('Unknown qubit')
    if not 0<min_ej_ghz<max_ej_ghz<=200:raise ValueError('EJ search bounds invalid')
    proposed=copy.deepcopy(design)
    element=next(x for x in proposed['elements'] if x['id']==q['junction'])
    initial=element['ej_ghz']
    target=q.get('target_ghz',5.)
    def objective(v):
        element['ej_ghz']=float(v)
        return abs(solve_modes(proposed)['qubit_assignments'][q['id']]['frequency_ghz']-target)
    old_err=objective(initial)
    solution=minimize_scalar(objective,bounds=(min_ej_ghz,max_ej_ghz),method='bounded',
                             options={'xatol':1e-5,'maxiter':120})
    element['ej_ghz']=float(solution.x)
    achieved=solve_modes(proposed)['qubit_assignments'][q['id']]['frequency_ghz']
    return {'analysis':'optimize','fidelity':'one_parameter_bounded_search', 'qubit':q['id'],
            'original_ej_ghz':initial, 'proposed_ej_ghz':float(solution.x),
            'before_error_mhz':old_err*1000,'after_error_mhz':abs(achieved-target)*1000,
            'predicted_ghz':achieved, 'target_ghz':target,
            'proposed_design':proposed,
            'assumptions':['Only selected EJ varied; no physical mask/junction geometry is generated from EJ',
                           'Analytical cost only; no EM re-solve, fabrication/design-rule or uncertainty constraints']}


def loss_budget(design, dielectric_q=1e6, conductor_q=2e7, radiation_q=1e8,
                quasiparticle_q=1e8):
    if any(type(x) not in (int,float) or not math.isfinite(x) or x<1 for x in
           (dielectric_q,conductor_q,radiation_q,quasiparticle_q)):
        raise ValueError('All externally supplied quality factors must be at least 1')
    q_total=1/sum(1/x for x in (dielectric_q,conductor_q,radiation_q,quasiparticle_q))
    rows=[]
    for m in solve_modes(design)['modes']:
        f=m['frequency_ghz']*1e9
        rows.append({'mode_index':m['index'],'frequency_ghz':m['frequency_ghz'],
                     'assumed_loaded_q':q_total,'estimated_t1_us':q_total/(2*pi*f)*1e6})
    return {'analysis':'loss_budget','fidelity':'user_supplied_q_budget', 'modes':rows,
            'q_inputs':{'dielectric':dielectric_q,'conductor':conductor_q,
                        'radiation':radiation_q,'quasiparticles':quasiparticle_q},
            'assumptions':['Quality factors are user assumptions, NOT derived from field participation',
                           'Independent inverse-Q addition, no Purcell, TLS saturation, temperature or packaging model']}


def analyze(design, analysis, options=None):
    validate(design)
    if analysis not in ANALYSES: raise ValueError('Unsupported analysis')
    options=options or {}
    if not isinstance(options,dict) or len(options)>20:raise ValueError('Invalid analysis options')
    options={k:v for k,v in options.items() if v is not None and v!=''}
    funcs={'modes':solve_modes, 'sparameters':sparameters, 'flux':flux_sweep,
           'dynamics':dynamics, 'yield':yield_analysis, 'duffing':duffing,
           'design_checks':design_checks, 'optimize':optimize, 'loss_budget':loss_budget}
    import inspect
    fn=funcs[analysis]
    allowed=set(inspect.signature(fn).parameters)-{'design'}
    if set(options)-allowed:raise ValueError('Unknown analysis option: '+str(set(options)-allowed))
    return fn(design,**options)
