"""Adversarial checks against a genuinely completed native source."""
from copy import deepcopy
from pathlib import Path

from .native_transmon import reference_declaration


def verify_guards(session):
    current = session.request(f'/api/projects/{session.pid}')
    base = {'expected_revision': current['head'], 'action': 'preview',
            'declaration': reference_declaration()}
    checks = []
    def rejected(name, payload, *, csrf=True, expected=(409,)):
        status, result = session.response(session.extraction_url, payload, csrf=csrf)
        if status not in expected:
            raise ValueError('NATIVE_SOURCE_GUARD_DID_NOT_REJECT: ' + name + ': ' + str(status))
        checks.append({'id': name, 'status': 'PASS', 'observed_http_status': status})
    rejected('missing_csrf', base, csrf=False, expected=(403,))
    rejected('stale_expected_revision', {**base, 'expected_revision': '0'*32})
    units = deepcopy(base)
    units['declaration']['josephson']['unit'] = 'MHz'
    rejected('wrong_josephson_units', units, expected=(409, 422))
    wrong_cj = deepcopy(base)
    wrong_cj['declaration']['junction_capacitance_convention'] = 'INCLUDED_IN_MAXWELL_MATRIX'
    rejected('junction_double_counting', wrong_cj, expected=(409, 422))
    changed = deepcopy(current['model'])
    changed['layout']['components'][0]['x_mm'] += .01
    revision = session.request(f'/api/projects/{session.pid}/commit',
        {'expected_revision': current['head'], 'model': changed})['revision']
    rejected('changed_geometry', {**base, 'expected_revision': revision})
    current_revision = session.request(f'/api/projects/{session.pid}/commit',
        {'expected_revision': revision, 'model': current['model']})['revision']
    base['expected_revision'] = current_revision
    info = session.server.app.store.run(session.owner, session.pid, session.source_run)
    csv = Path(info['path']) / 'output/sqe_em/outputFiles/terminal-C.csv'
    original = csv.read_bytes()
    try:
        # Deliberate corruption of this test-owned native source; never resign it.
        csv.write_bytes(original + b'\n')
        rejected('altered_native_csv', base)
    finally:
        csv.write_bytes(original)  # Preserve the exact original native evidence.
    session.request(session.extraction_url, base)
    checks.append({'id': 'unchanged_physical_context_reusable_after_study_only_revision',
                   'status': 'PASS'})
    return checks
