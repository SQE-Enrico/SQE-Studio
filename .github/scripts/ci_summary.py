"""Render bounded SQE test evidence into a GitHub Actions job summary."""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import re
import zipfile


def cell(value):
    return html.escape(str(value), quote=False).replace('|', '\\|').replace('`', '&#96;').replace('\r', ' ').replace('\n', ' ')[:300]


def read_latest(root):
    path = root / 'qualification-reports/local-latest.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64000:
        raise ValueError('No usable local test summary')
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or data.get('schema') != 'sqe.local-development-check.v1'
            or type(data.get('exit_code')) is not int):
        raise ValueError('Invalid local test summary')
    return data


def read_details(root, name):
    if not isinstance(name, str) or not re.fullmatch(r'SQE-RC14_12-report-[0-9]{4,}\.zip', name):
        raise ValueError('No safe numbered test report')
    path = root / 'qualification-reports' / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000_000:
        raise ValueError('Numbered report unavailable')
    with zipfile.ZipFile(path) as archive:
        entry = archive.getinfo('QUALIFICATION.json')
        if entry.file_size > 2_000_000:
            raise ValueError('Detailed report exceeds summary budget')
        data = json.loads(archive.read(entry))
    if not isinstance(data, dict) or not isinstance(data.get('tasks'), list):
        raise ValueError('Invalid detailed report')
    return data


def render(root, environment):
    lines = ['# SQE software checks', '']
    repository = environment.get('GITHUB_REPOSITORY', '')
    revision = environment.get('GITHUB_SHA', '')
    run_id = environment.get('GITHUB_RUN_ID', '')
    if re.fullmatch(r'[\w.-]+/[\w.-]+', repository) and re.fullmatch(r'[0-9a-f]{40}', revision):
        lines.append(f'Source: [{revision[:12]}](https://github.com/{repository}/commit/{revision})')
        if run_id.isdecimal():
            lines.append(f'[Run and downloadable reports](https://github.com/{repository}/actions/runs/{run_id}#artifacts)')
    lines.extend(['Platform: ' + cell(environment.get('SQE_CI_OS', 'local')) +
                  ' / Python ' + cell(environment.get('SQE_CI_PYTHON', 'unknown')), ''])
    try:
        latest = read_latest(root)
    except (OSError, ValueError):
        lines.extend(['**INCOMPLETE: no usable test result was produced.**',
                      'Check the failing setup/test step for diagnostics.', ''])
        return '\n'.join(lines)
    code = latest['exit_code']
    result = 'PASS' if code == 0 and latest.get('source_stable') is True else (
        'FAIL' if code == 1 else 'BLOCKED / INCOMPLETE')
    lines.extend(['**Result: ' + result + '**', 'Profile: ' + cell(latest.get('profile', 'unknown')),
                  'Source stable during tests: ' + cell(latest.get('source_stable', False)), '',
                  '| Local check | Status | Seconds |', '|---|---|---:|'])
    for step in latest.get('steps', [])[:32]:
        lines.append('| ' + ' | '.join(cell(step.get(key, '-')) for key in ('id', 'status', 'duration_s')) + ' |')
    try:
        details = read_details(root, latest.get('automatic_test_report'))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        lines.extend(['', '**Detailed numbered report unavailable.**', ''])
    else:
        lines.extend(['', 'Report: ' + cell(latest['automatic_test_report']), '',
                      '| Automatic Test family | Status | Seconds |', '|---|---|---:|'])
        for task in details['tasks'][:32]:
            lines.append('| ' + ' | '.join(cell(task.get(key, '-')) for key in ('id', 'status', 'duration_s')) + ' |')
        regression = next((row for row in details['tasks'] if row.get('id') == 'regression'), {})
        log = '\n'.join(row.get('log', '') for row in regression.get('substeps', []))
        groups = re.findall(r'^GROUP (\w+) exit=(\d+) elapsed_s=([\d.]+) passed=(\d+|NONE) skipped=(\d+)', log, re.MULTILINE)
        if groups:
            lines.extend(['', '| Regression domain | Exit | Passed | Skipped | Seconds |', '|---|---:|---:|---:|---:|'])
            for name, exit_code, seconds, passed, skipped in groups:
                lines.append(f'| {cell(name)} | {exit_code} | {passed} | {skipped} | {seconds} |')
    lines.extend(['', 'Skipped and excluded families remain explicit; availability differs between cloud and scientific workstations.',
                  '**Scientific qualification: NOT_ESTABLISHED. Fabrication: HOLD.**', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, default=os.environ.get('GITHUB_STEP_SUMMARY'))
    args = parser.parse_args()
    content = render(args.root, os.environ)
    if args.output:
        with args.output.open('a', encoding='utf-8', newline='\n') as target:
            target.write(content)
    else:
        print(content)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
