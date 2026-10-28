"""Read-only Gmsh/Palace consistency checks for the fixed reference QPU.

No physical qualification is implied. Only authentic solver artifacts with hashes
recorded by verify_solve() may be used for energy comparisons.
"""
from __future__ import annotations

from collections import Counter
import csv
import math
from pathlib import Path
import re

from .io import read_json, sha256, write_json


def _msh22_groups(path: Path) -> dict:
    """Stream MSH 2.2 ASCII elements; keep counts, not mesh vertices/elements."""
    names = {}
    counts = Counter()
    total = 0
    element_types_2d = {2, 3, 9, 10, 16, 20, 21, 22, 23, 24, 25}
    element_types_3d = {4, 5, 6, 7, 11, 12, 13, 14, 17, 18, 19, 29, 30, 31, 32, 33, 34, 35}
    with path.open('r', encoding='utf-8', errors='strict') as stream:
        for line in stream:
            header = line.strip()
            if header == '$MeshFormat':
                fmt = next(stream).split()
                if len(fmt) < 2 or fmt[0] != '2.2' or fmt[1] != '0':
                    raise ValueError('FEM audit requires ASCII Gmsh MSH 2.2')
            elif header == '$PhysicalNames':
                n = int(next(stream))
                if not 0 <= n <= 256:
                    raise ValueError('Unexpected Gmsh physical-group count')
                for _ in range(n):
                    row = next(stream).strip()
                    match = re.fullmatch(r'(\d+)\s+(\d+)\s+"([^"]{1,128})"', row)
                    if match is None:
                        raise ValueError('Invalid MSH physical-name record')
                    dim, tag, name = int(match[1]), int(match[2]), match[3]
                    if (dim, tag) in names:
                        raise ValueError('Duplicate MSH physical tag')
                    names[(dim, tag)] = name
            elif header == '$Elements':
                n = int(next(stream))
                if not 0 < n < 40_000_000:
                    raise ValueError('Invalid MSH element count')
                total = n
                for _ in range(n):
                    row = next(stream).split()
                    if len(row) < 4:
                        raise ValueError('Truncated MSH element')
                    elem_type, ntags = int(row[1]), int(row[2])
                    if not 1 <= ntags <= 64 or len(row) < 3 + ntags + 1:
                        raise ValueError('MSH elements lack physical attributes')
                    dim = 2 if elem_type in element_types_2d else 3 if elem_type in element_types_3d else None
                    if dim:
                        counts[(dim, int(row[3]))] += 1
                break
    if total <= 0 or not names:
        raise ValueError('Mesh lacks elements or physical names')
    return {'physical_names': names, 'element_counts': counts, 'total_elements': total}


def geometry_boundary_audit(out: Path) -> dict:
    """Check names, material coverage and electrode/ground tags in the real mesh.

    Physical-name agreement alone does not prove that each surface is the correct
    geometric face or that OCC topology is free of defects.
    """
    out = Path(out)
    contract = read_json(out / 'contract.json')
    geometry = read_json(out / 'geometry.json')
    mesh = read_json(out / 'mesh.json')
    config = read_json(out / 'electrostatic.json')
    if sha256(out / 'device.msh') != mesh['mesh_sha256'] or \
            mesh['geometry_sha256'] != contract['geometry_sha256'] or \
            geometry['geometry_sha256'] != contract['geometry_sha256']:
        raise ValueError('Geometry/mesh integrity mismatch')
    groups = _msh22_groups(out / 'device.msh')
    names, counts = groups['physical_names'], groups['element_counts']
    tags = geometry['physical_tags']
    failures, warnings, listed = [], [], []
    expected = list(tags.items())
    if len({int(tag) for _, tag in expected}) != len(expected):
        failures.append('Duplicate physical attribute numbers in geometry')
    for name, tag in expected:
        dim = 3 if name in ('air', 'silicon') else 2
        n = counts.get((dim, int(tag)), 0)
        actual_name = names.get((dim, int(tag)))
        listed.append({'name': name, 'dimension': dim, 'attribute': int(tag),
                       'mesh_elements': n, 'name_matches': actual_name == name})
        if not n or actual_name != name:
            failures.append('Missing/mismatched MSH physical group: ' + name)
    material_tags = [int(x) for item in config['Domains']['Materials'] for x in item['Attributes']]
    if set(material_tags) != {int(tags['air']), int(tags['silicon'])} or len(material_tags) != 2:
        failures.append('Dielectric material attributes do not match volume groups')
    boundary = config['Boundaries']
    ground = set(map(int, boundary['Ground']['Attributes']))
    terminals = boundary['Terminal']
    assigned = [int(t) for row in terminals for t in row['Attributes']]
    ids = [int(row['Index']) for row in terminals]
    intended = [int(tags[name]) for name in contract['terminal_order']]
    if ids != list(range(1, len(ids)+1)) or assigned != intended:
        failures.append('Palace terminal order differs from the physical contract')
    if set(assigned) & ground or set(assigned) != set(int(tags[k]) for k in geometry['terminals']):
        failures.append('Palace boundary terminals overlap ground or omit a conductor')
    if ground != {int(tags['ground']), int(tags['outer'])}:
        failures.append('Ground/outer boundary attributes are inconsistent')
    for name in ('ground', 'outer'):
        if counts.get((2, int(tags[name])), 0) < 1:
            failures.append('No boundary elements assigned to ' + name)
    untagged = sum(value for (dim,tag),value in counts.items() if dim == 2 and tag == 0)
    if untagged:
        warnings.append('MSH contains unlabelled surface elements; check unintended open boundaries')
    warnings.append('Named mesh groups cannot establish geometrical connectivity or correct OCC face ownership.')
    result = {'schema_version': 1, 'source': 'source_geometry_and_actual_gmsh_mesh',
              'mesh_sha256': mesh['mesh_sha256'],
              'configuration_sha256': sha256(out / 'electrostatic.json'),
              'surface_groups': listed, 'terminal_order': contract['terminal_order'],
              'terminal_count': len(terminals), 'physical_element_count': groups['total_elements'],
              'failures': failures, 'warnings': warnings, 'preflight_pass': not failures,
              'scientific_qualification': False}
    write_json(out / 'geometry-boundary-audit.json', result)
    return result


def _palace_csv(path: Path, required: str) -> list[dict]:
    with path.open('r', newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream, skipinitialspace=True)
        fields = [k.strip() for k in (reader.fieldnames or [])]
        if len(fields) != len(set(fields)) or required not in fields or 'i' not in fields:
            raise ValueError('Unexpected Palace energy CSV columns')
        values = []
        for row in reader:
            cleaned = {k.strip(): v for k,v in row.items() if k is not None}
            idx = float(cleaned['i'])
            energy = float(cleaned[required])
            if not math.isfinite(idx) or idx != int(idx) or idx < 1 or \
                    not math.isfinite(energy) or energy < 0:
                raise ValueError('Invalid Palace energy record')
            values.append({'terminal_index': int(idx), 'energy_J': energy})
    return values


def energy_consistency(out: Path, name: str, matrix_ff) -> dict:
    """Unit-voltage check against Palace's electric energy, per terminal.

    This is an independent output consistency diagnostic, not convergence and
    not proof of physically correct boundary conditions. Never adjust units
    automatically to force agreement.
    """
    from .physical_qpu import verify_solve
    record = verify_solve(out, name)
    file = Path(out) / name / 'domain-E.csv'
    entry = name + '/domain-E.csv'
    if not file.is_file() or record.get('outputs_sha256', {}).get(entry) != sha256(file):
        return {'status': 'NOT_AVAILABLE', 'reason': 'Verified domain-E.csv unavailable'}
    try:
        rows = _palace_csv(file, 'E_elec (J)')
    except ValueError as exc:
        return {'status':'NOT_COMPARABLE', 'reason':str(exc), 'source_sha256':sha256(file)}
    size = len(matrix_ff)
    if len(rows) != size or sorted(r['terminal_index'] for r in rows) != list(range(1,size+1)):
        return {'status': 'INCONCLUSIVE', 'reason': 'Energy rows do not match the number of terminals'}
    comparisons = []
    for row in rows:
        i = row['terminal_index']-1
        cap_f = float(matrix_ff[i][i]) * 1e-15
        if not math.isfinite(cap_f) or cap_f <= 0:
            raise ValueError('Invalid capacitance diagonal for energy audit')
        predicted = 0.5 * cap_f  # Palace drives each terminal to +1 V.
        observed = row['energy_J']
        comparisons.append({'terminal_index':i+1, 'predicted_0p5_CV2_J':predicted,
                            'palace_electric_energy_J':observed,
                            'ratio_observed_to_predicted':observed/predicted,
                            'relative_difference': abs(observed-predicted)/predicted})
    maximum = max(item['relative_difference'] for item in comparisons)
    return {'status': 'CONSISTENT' if maximum <= 0.05 else 'MISMATCH_REQUIRES_INVESTIGATION',
            'max_relative_difference': maximum, 'per_terminal': comparisons,
            'source_sha256': sha256(file),
            'assumption': 'Unit voltage each terminal in turn; stored energy = 0.5 * Cii * (1 V)^2',
            'note': 'Mismatch is a reported scientific issue; no ad hoc rescaling is applied.'}
