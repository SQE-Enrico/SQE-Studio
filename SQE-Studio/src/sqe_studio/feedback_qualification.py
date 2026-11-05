"""One-archive EDA feedback path for the local Tk desktop qualifier.

No saved projects, installed solver trees or home data are collected. The same
normal production worker and Results read-only parsers are exercised in private
temporary workspaces. Only explicit reviewed research inputs can start Palace.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

SCHEMA = 'sqe.eda-feedback-qualification.v1'
MAX_SUBREPORT_SIZE = 48_000_000


def _checked_members(path: Path) -> dict[str, bytes]:
    """Reject path tricks, symlinks, bombs and altered content before reuse."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SUBREPORT_SIZE:
        raise ValueError('Missing, linked or oversized qualification ZIP')
    with zipfile.ZipFile(path, 'r') as z:
        names = z.namelist()
        if (not names or len(names) > 160 or len(names) != len(set(names)) or
            'INTEGRITY.json' not in names):
            raise ValueError('Missing, duplicate or excessive subreport members')
        for info in z.infolist():
            name = info.filename
            if (len(name) > 255 or not name or name.endswith('/') or
                name.startswith('/') or name.startswith('./') or
                '\\' in name or ':' in name or '\x00' in name or
                any(part in ('', '.', '..') for part in name.split('/')) or
                info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000 or
                info.file_size > MAX_SUBREPORT_SIZE):
                raise ValueError('Unsafe subreport member')
        if sum(info.file_size for info in z.infolist()) > MAX_SUBREPORT_SIZE:
            raise ValueError('Qualification report exceeds safe combination budget')
        if z.getinfo('INTEGRITY.json').file_size > 64_000:
            raise ValueError('Unbounded hash inventory')
        hashes = json.loads(z.read('INTEGRITY.json'))['files']
        if (not isinstance(hashes, dict) or set(hashes) != set(names) - {'INTEGRITY.json'} or
            any(not isinstance(digest, str) or len(digest) != 64 or
                any(c not in '0123456789abcdef' for c in digest) for digest in hashes.values())):
            raise ValueError('Incomplete or malformed subreport hash inventory')
        result = {name: z.read(name) for name in names}
        if z.testzip() is not None or any(
                hashlib.sha256(result[n]).hexdigest() != digest for n, digest in hashes.items()):
            raise ValueError('Subreport checksum mismatch')
        return result


def _failure_subreport(phase: str, error: Exception, *private_paths: str) -> tuple[dict, dict[str, bytes]]:
    """Exception gate, NOT a simulated test result or solver observation."""
    from .qualification import _safe_log
    message = _safe_log(type(error).__name__ + ': ' + str(error)[:1000],
                        (str(Path.home()), os.environ.get('USERPROFILE', ''), *private_paths))
    doc = {'schema': 'sqe.qualification-exception.v1', 'profile': phase,
           'rc_status': 'BLOCKED_NOT_RELEASE_CANDIDATE',
           'counts': {'PASS': 0, 'FAIL': 1, 'BLOCKED': 0},
           'stages': [{'id': phase + '_exception', 'status': 'FAIL',
                       'reason': 'Qualification stage raised; no native result accepted',
                       'exception_type': type(error).__name__}],
           'scientific_qualification': 'NOT_ESTABLISHED', 'fabrication': 'HOLD'}
    files = {'QUALIFICATION.json': (json.dumps(doc, indent=2, sort_keys=True) + '\n').encode(),
             'SUMMARY.md': ('# ' + phase + ' qualification failed\n\n' + message +
                            '\nNo completed scientific result is claimed.\n').encode()}
    files['INTEGRITY.json'] = (json.dumps({'schema': 'sqe.qualification-file-hashes.v1',
              'files': {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}},
              sort_keys=True) + '\n').encode()
    return doc, files


def _validate_phase_report(document: dict, files: dict[str, bytes]) -> None:
    """Status in the returned object must match the SHA-checked report bytes."""
    on_disk = json.loads(files['QUALIFICATION.json'])
    if (not isinstance(on_disk, dict) or
        any(on_disk.get(k) != document.get(k) for k in ('schema', 'profile', 'counts', 'rc_status')) or
        on_disk.get('rc_status') != 'BLOCKED_NOT_RELEASE_CANDIDATE' or
        not isinstance(on_disk.get('counts'), dict) or
        set(on_disk['counts']) != {'PASS','FAIL','BLOCKED'} or
        any(type(v) is not int or v < 0 for v in on_disk['counts'].values())):
        raise ValueError('Returned phase statuses differ from integrity-verified report evidence')


def qualify_eda_feedback(source: Path, output: Path, *, em_options: dict | None,
                         notify=None) -> dict:
    """Comprehensive software + optional mesh-pair native readout, one shareable ZIP.

    `solve` is mandatory; a second/third mesh remains an explicit user opt-in.
    Real missing dependencies are BLOCKED in the native report, never fake PASS.
    """
    from .native_em_qualification import _option_check
    from .qualification import qualify, sha

    if not isinstance(em_options, dict):
        raise ValueError('EDA feedback requires explicit reviewed native EM settings')
    if not {'reviewer', 'acknowledged', 'solve', 'refine'} <= em_options.keys() or not em_options.keys() <= {
        'reviewer','acknowledged','solve','refine','third_mesh','memory_budget_gb','time_budget_seconds','mpi_ranks'}:
        raise ValueError('Unrecognized native EM feedback settings')
    if em_options['solve'] is not True:
        raise ValueError('EDA feedback requires a real native Palace solve; use Native EM reference for deck-only')
    # Validate physical consent and resource limits *before* running software.
    options = {'reviewer':em_options['reviewer'], 'acknowledged':em_options['acknowledged'],
               'solve':em_options['solve'], 'refine':em_options['refine'],
               'third_mesh':em_options.get('third_mesh',False),
               'memory_budget_gb':em_options.get('memory_budget_gb',8.0),
               'time_budget_seconds':em_options.get('time_budget_seconds',840),
               'mpi_ranks':em_options.get('mpi_ranks','auto')}
    _option_check(**options)

    root = Path(source).resolve(strict=True)
    target = Path(output).expanduser().absolute()
    if (not (root/'src/sqe_studio/server.py').is_file() or
        not (root/'src/sqe_studio/worker.py').is_file() or
        target.suffix.lower() != '.zip' or target.is_symlink() or
        target.is_relative_to(root)):
        raise ValueError('A valid extracted SQE source and report path outside it are required')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Verify the destination BEFORE expensive software/native probes.
    if target.exists() or target.is_symlink() or target.with_name(target.name+'.partial').exists():
        raise FileExistsError('Existing qualification evidence must not be overwritten')
    say = notify or (lambda message: None)
    with tempfile.TemporaryDirectory(prefix='sqe-eda-feedback-') as scratch:
        temporary = Path(scratch)
        say('PHASE_START software')
        say('Part 1/2: software, security, browser, installed tools and packaging qualification')
        try:
            software = qualify(root, temporary/'software.zip', profile='comprehensive', notify=say)
            software_files = _checked_members(temporary/'software.zip')
            _validate_phase_report(software, software_files)
        except Exception as exc:
            software, software_files = _failure_subreport('software', exc, str(root), str(temporary))
            say('FAIL: software_exception - preserving independent phase evidence')
        say('PHASE_END software')
        say('PHASE_START native_em')
        say('Part 2/2: reviewed native Gmsh/Palace run and production Results reader; no substitute solver')
        try:
            native = qualify(root, temporary/'em.zip', profile='native_em', em_options=options, notify=say)
            em_files = _checked_members(temporary/'em.zip')
            _validate_phase_report(native, em_files)
        except Exception as exc:
            native, em_files = _failure_subreport('native_em', exc, str(root), str(temporary))
            say('FAIL: native_em_exception - preserving completed software evidence')
        say('PHASE_END native_em')
        # A fixed, bounded summary of SHA-checked stage statuses. Do not equate
        # a software PASS with physical validation, or infer a native solve from
        # the presence of a partial output file or an old report.
        def status_at(document, group, key):
            stages = document.get(group, ())
            if not isinstance(stages, list):
                return 'NOT_REPORTED'
            for stage in stages[:80]:
                if isinstance(stage, dict) and stage.get('id') == key:
                    status = stage.get('status')
                    return status if status in ('PASS', 'FAIL', 'BLOCKED') else 'NOT_REPORTED'
            return 'NOT_REPORTED'
        coverage = {
            'source_integrity': status_at(software, 'gates', 'source_integrity'),
            'authenticated_browser': status_at(software, 'gates', 'browser_real_http'),
            'source_wheel_build': status_at(software, 'gates', 'source_wheel_build'),
            'installed_wheel': status_at(software, 'gates', 'installed_wheel'),
            'installed_assets': status_at(software, 'gates', 'installed_assets'),
            'native_palace_solve': status_at(native, 'stages', 'native_palace_solve'),
            'native_palace_refinement': status_at(native, 'stages', 'native_palace_refinement'),
            'mesh_convergence': status_at(native, 'stages', 'mesh_convergence'),
            'complex_field_mode_identity': 'BLOCKED',
            'em_epr_hamiltonian_transfer': 'BLOCKED',
            'fabrication': 'HOLD',
        }
        report = {
            'schema':SCHEMA,
            'finished_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'profile':'eda_feedback',
            'diagnostic_coverage':coverage,
            'software':{'schema':software['schema'],'counts':software['counts'],
                        'rc_status':software['rc_status']},
            'native_em':{'schema':native['schema'],'counts':native['counts'],
                         'rc_status':native['rc_status']},
            'counts':{s:software['counts'][s]+native['counts'][s] for s in ('PASS','FAIL','BLOCKED')},
            'tested_paths':{'software':'software/QUALIFICATION.json',
                            'native_em':'em/QUALIFICATION.json',
                            'results':'em/native/*-results-screen.json',
                            'comparison':'em/native/results-cross-run-comparison.json (when two real runs are available)'},
            'scientific_qualification':'NOT_ESTABLISHED',
            'automatic_mode_matching':'BLOCKED_NO_COMPLEX_FIELD_OVERLAP',
            'fabrication':'HOLD',
            'rc_status':'BLOCKED_NOT_RELEASE_CANDIDATE',
            'limitations':['Production read-only Results functions are called against temporary verified native output, not against a saved user project.',
                           'Real browser UI flow is tested separately by Comprehensive; no native GUI click-through is claimed.',
                           'Exception-only fallback entries are FAIL diagnostics, never successful native solver runs.',
                           'Mode-index comparison does not establish matching eigenmodes or Q convergence.',
                           'No saved user projects or native field/mesh blobs are copied into this shareable report.'],
        }
        summary = ['# SQE Studio — unified EDA feedback', '',
                   '**Experimental / NOT RELEASE CANDIDATE**', '',
                   'Software checks: '+str(software['counts']),
                   'Native EM checks: '+str(native['counts']),
                   'Combined gates: '+str(report['counts']), '',
                   'Bounded SHA-checked gate coverage (NOT a physics approval):',
                   *(key+': '+value for key,value in coverage.items()), '',
                   'The native phase uses the unchanged production Gmsh/Palace worker under reviewed research assumptions.',
                   'Verified production Results readers extract real signed port data, if solver files are available.',
                   'Two meshes enable a numerical-only comparison; **no mode identity, field overlap or scientific convergence is claimed**.',
                   'The software/browser phase and the native worker phase have separate results and provenance.', '',
                   'See `software/SUMMARY.md`, `em/SUMMARY.md` and `em/native/*-results-screen.json`.',
                   'Inspect sanitized logs and identifiers before sending this ZIP to another party.', '']
        members = {'QUALIFICATION.json':(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode(),
                   'SUMMARY.md':('\n'.join(summary)+'\n').encode()}
        members.update({'software/'+k:v for k,v in software_files.items()})
        members.update({'em/'+k:v for k,v in em_files.items()})
        members['INTEGRITY.json'] = (json.dumps({'schema':'sqe.qualification-file-hashes.v1',
                     'files':{k:sha(v) for k,v in sorted(members.items())}},
                     indent=2,sort_keys=True)+'\n').encode()
        partial = target.with_name(target.name+'.partial')
        if target.exists() or target.is_symlink() or partial.exists():
            raise FileExistsError('Existing qualification evidence must not be overwritten')
        try:
            with zipfile.ZipFile(partial,'x',zipfile.ZIP_DEFLATED,compresslevel=8) as z:
                for k,v in sorted(members.items()):
                    z.writestr(k,v)
            if _checked_members(partial).keys() != members.keys():
                raise ValueError('Unified report could not be verified')
            os.link(partial, target)
        finally:
            partial.unlink(missing_ok=True)
        say('Unified EDA feedback ZIP saved. Native scientific release gates remain blocked.')
        return report
