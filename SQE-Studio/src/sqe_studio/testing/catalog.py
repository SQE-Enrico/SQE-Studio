"""Small versioned catalog, independent of the UI and scientific engines."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from pathlib import Path


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    dependencies: tuple[str, ...]
    timeout_s: int
    purpose: str
    heavy: bool = False


TASKS = (
    Task('integrity', 'Source, contracts and cycle identity', (), 45, 'software'),
    Task('targeted', 'Integration, provenance and negative tests', ('integrity',), 240, 'software'),
    Task('http', 'Saved project / authenticated HTTP workflow', ('integrity',), 45, 'software'),
    Task('regression', 'Full portable software regression', ('integrity',), 1800, 'software'),
    Task('browser', 'Real browser workflow', ('http',), 150, 'software'),
    Task('cad', 'Native Quantum Metal / GDS', ('integrity',), 240, 'native'),
    Task('quantum', 'Native quantum basis curves and references', ('http', 'targeted'), 240, 'native'),
    Task('extraction', 'Capacitance fixture → native scqubits / conditional quantization', ('http', 'targeted'), 240, 'native_quantum_from_em_fixture'),
    Task('rf', 'Native Josephson linear / harmonic balance', ('integrity',), 600, 'native'),
    Task('fields', 'Upstream SQDMetal / VTK reader compatibility (no Palace)', ('integrity', 'targeted'), 150, 'native_software_fixture'),
    Task('field_compare', 'VTK cross-mesh sampling / analytic complex MAC (no Palace)', ('integrity', 'targeted'), 300, 'native_software_fixture'),
    Task('em', 'Palace single-mesh smoke / field diagnostics', ('integrity',), 1000, 'native', True),
    Task('em_convergence', 'Palace two-mesh fields and scalar diagnostics', ('integrity', 'field_compare'), 1900, 'native', True),
    Task('packaging', 'Fresh wheel and isolated HTTP installation', ('integrity',), 240, 'software'),
)
BY_ID = {t.id: t for t in TASKS}
PROFILES = {
    'recommended': ('targeted', 'http'),
    'extraction': ('targeted', 'http', 'extraction'),
    'quick': ('targeted', 'http'),
    'cad': ('targeted', 'cad'),
    'quantum': ('targeted', 'http', 'quantum'),
    'rf': ('targeted', 'http', 'rf'),
    'fields': ('targeted', 'fields'),
    'field_compare': ('targeted', 'http', 'field_compare'),
    'two_mesh_fields': ('targeted', 'http', 'field_compare', 'em_convergence'),
    'field_em': ('targeted', 'fields', 'em'),
    'em': ('targeted', 'em'),
    'convergence': ('targeted', 'em_convergence'),
    'milestone': ('regression', 'http', 'browser', 'cad', 'quantum', 'rf', 'fields', 'em', 'packaging'),
}
LABELS = {
    'recommended': 'Recommended · modular software and HTTP',
    'extraction': 'Extraction · saved source to scqubits (EM fixture; no Palace)',
    'quick': 'Quick · software and HTTP', 'cad': 'CAD / GDS',
    'quantum': 'Quantum · basis curves and references', 'rf': 'RF / JPA',
    'fields': 'Fields · SQDMetal / VTK (no Palace)',
    'field_compare': 'Quick fields · analytic VTK / MAC (no Palace)',
    'two_mesh_fields': 'Field comparison · Palace (two meshes)',
    'field_em': 'Field outputs · SQDMetal + Palace (one mesh)',
    'em': 'EM · one-mesh smoke', 'convergence': 'EM · two-mesh diagnostic',
    'milestone': 'Milestone · full software and native families',
}


def catalog():
    return [asdict(t) for t in TASKS]


def resolve_selection(selected):
    if type(selected) not in (list, tuple) or not selected or len(selected) > len(TASKS):
        raise ValueError('Select at least one known test family')
    if any(type(i) is not str or i not in BY_ID for i in selected) or len(set(selected)) != len(selected):
        raise ValueError('Unknown or duplicate test family')
    requested = set(selected)
    # The two-mesh task includes the coarse run; do not run it twice.
    superseded = {'em'} if {'em', 'em_convergence'} <= requested else set()
    chosen = requested - superseded
    def include(name):
        for parent in BY_ID[name].dependencies:
            if parent not in chosen:
                chosen.add(parent)
                include(parent)
    for name in tuple(chosen):
        include(name)
    ordered = [t.id for t in TASKS if t.id in chosen]
    return {'requested': [t.id for t in TASKS if t.id in requested],
            'resolved': ordered,
            'automatic_prerequisites': [i for i in ordered if i not in requested],
            'superseded': sorted(superseded)}


def load_plan(root: Path):
    path = Path(root) / 'automatic_test_plan.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32000:
        raise ValueError('Missing or unsafe test plan')
    raw = path.read_bytes()
    doc = json.loads(raw)
    if (type(doc) is not dict or doc.get('schema') != 'sqe.automatic-test-plan.v2'
            or doc.get('milestone') != 'M20' or doc.get('version') != 1
            or doc.get('default_profile') != 'recommended'
            or doc.get('wall_budget_s') != 3600 or doc.get('packaging_reserve_s') != 120
            or doc.get('native_concurrency') != 1
            or doc.get('recommended_tasks') != list(PROFILES['recommended'])
            or doc.get('task_ids') != list(BY_ID)):
        raise ValueError('Test plan does not match this runtime')
    return doc, sha256(raw).hexdigest()
