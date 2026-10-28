"""SQE nominal circuit -> JosephsonCircuits.jl compatible Julia netlist.

This is an EXPORT, not a performed harmonic-balance simulation. Native JJ
branches retain their nonlinear Josephson identity (Lj). No SQUID is silently
collapsed to one branch, and no EM extraction is inferred from nominal C/L.
"""
from __future__ import annotations

import math
from pathlib import Path
from scipy.constants import h, pi, physical_constants

from .io import digest, write_json
from .quantumlab import validate

PHI0 = physical_constants['mag. flux quantum'][0]


def export_design(design, output):
    validate(design)
    if any(el['kind'] == 'SQUID' for el in design['elements']):
        raise ValueError('SQUID needs explicit loop/arms and magnetic flux constraints; nonlinear JosephsonCircuits export refuses a single effective JJ')
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    nodes = validate(design)
    nodeids = {'0': '0', **{name: str(i+1) for i, name in enumerate(nodes)}}
    mapping = []
    totals = {'C':0, 'L':0, 'R':0, 'Lj':0, 'P':0}
    branches = []
    def add(kind, a, b, value, origin):
        totals[kind] += 1
        name = kind + str(totals[kind])
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f'{origin}: converted SI value invalid')
        branches.append((name, a, b, value, kind))
        mapping.append({'sqe_id': origin, 'julia_component': name, 'type':kind,
                        'nodes':[a,b], 'value_si':value})
    for el in design['elements']:
        kind=el['kind'];a=nodeids[el['a']];b=nodeids[el['b']]
        if kind == 'C':add('C',a,b,el['value']*1e-15,el['id'])
        elif kind == 'L':add('L',a,b,el['value']*1e-9,el['id'])
        elif kind == 'R':add('R',a,b,el['value'],el['id'])
        elif kind == 'JJ':
            lj=PHI0**2/(4*pi*pi*h*el['ej_ghz']*1e9)
            add('Lj',a,b,lj,el['id'])
    # A port is a *physical* capacitive tap plus 50 Ohm line termination;
    # it is not a free port directly shorting the resonator node.
    for number, port in enumerate(design.get('ports',[]), start=1):
        external=str(len(nodes)+number)
        add('C',nodeids[port['node']],external,port['coupling_ff']*1e-15,port['id']+'.coupling')
        add('R',external,'0',port['z0_ohm'],port['id']+'.termination')
        add('P',external,'0',float(number),port['id'])
    # Official JosephsonCircuits examples use Symbolics @variables and a
    # Tuple{String,String,String,Num}[] with circuitdefs for numeric parameters.
    lines = ['# Generated from the immutable SQE circuit snapshot. RESEARCH / NOMINAL ONLY.',
             '# JosephsonCircuits.jl uses SI units and angular frequency (rad/s).',
             '# This file defines a physical nonlinear-JJ circuit; it DOES NOT run HB.',
             'using JosephsonCircuits',
             '@variables ' + ' '.join(x[0] for x in branches if x[4] != 'P'),
             'circuit = Tuple{String,String,String,Num}[]']
    for name, a, b, value, kind in branches:
        # All strings are generated identifiers and mapped integer node IDs.
        rhs = name if kind != 'P' else str(int(value))
        lines.append(f'push!(circuit, ("{name}", "{a}", "{b}", {rhs}))')
    lines.append('circuitdefs = Dict(')
    lines.extend(f'    {name} => {value:.17g},' for name,a,b,value,kind in branches if kind != 'P')
    lines.extend([')', '', '# Example only (uncomment to solve in a qualified Julia runtime):',
                  '# ws = 2*pi .* collect(range(4e9, 8e9, length=81))',
                  '# result = JosephsonCircuits.hblinsolve(ws, circuit, circuitdefs)',
                  '# A driven nonlinear solve requires explicitly defined pump sources.',
                  'println("JosephsonCircuits circuit prepared: ", length(circuit), " branches")'])
    text='\n'.join(lines)+'\n'
    (out/'circuit.jl').write_text(text,encoding='utf-8')
    record={'schema_version':1,'engine_target':'JosephsonCircuits.jl',
      'state':'EXPORTED_NOT_SIMULATED','model':'nominal_circuit_no_EM_extraction',
      'design_sha256':digest(design),'nodes':nodeids,'elements':mapping,
      'units':'SI', 'squid_policy':'refuse_incomplete_nonlinear_flux_topology',
      'limitations':['Never treat nominal elements as Palace-extracted values',
      'No pump, noise, gain, Floquet analysis or harmonic-balance result was computed',
      'External Julia runtime and JosephsonCircuits.jl are required to execute',
      'Port coupling represented by declared shunt-capacitor/tap model; distributed RF effects absent']}
    write_json(out/'josephsoncircuits-contract.json',record)
    return record
