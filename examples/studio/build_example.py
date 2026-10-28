"""Rebuild transferable public examples without shipping any account credentials.

Run from the repository root: python examples/studio/build_example.py
Only temporary local account state is created. Capsules contain research state.
"""
from contextlib import redirect_stdout
from pathlib import Path
import secrets
import shutil
import tempfile

from sqw.studio.server import Application
from sqw.studio.settings import Settings
from sqw.studio.runner import execute


def main():
    out = Path('examples/projects')
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        app = Application(Settings(Path(temporary)))
        password = secrets.token_urlsafe(32)
        app.auth.setup(app.auth.setup_token(), 'example@example.org', 'Example researcher', password)
        _, _, user = app.auth.login('example@example.org', password, 'example-builder')
        project = app.projects.create(user, 'Al-on-Si research example')
        state = app.projects.detail(user, project)
        doc = state['document']
        doc['notes'] = (
            'Public synthetic example: Al transmon on high-resistivity Si, 20 mK, '
            '4–12 GHz design band. Analytical capacitance surrogate; no measured '
            'device or native Palace chip result. Process dimensions are illustrative. '
            'Review results yourself after importing; no fabrication approval is included.'
        )
        app.projects.save(user, project, doc, state['draft_version'])

        def run(target, note, baseline=None):
            revision = app.projects.revise(user, project, note)
            job = app.jobs.enqueue(user, project, revision, target, baseline_id=baseline)
            folder = Path(temporary) / 'jobs' / job
            folder.mkdir(parents=True)
            with (folder / 'worker.log').open('w') as log, redirect_stdout(log):
                execute(app.store, job)
            assert app.store.one('SELECT state FROM jobs WHERE id=?', (job,))['state'] == 'succeeded'
            return job

        initial = run('report', 'Initial analytical circuit and expected measurements')
        state = app.projects.detail(user, project)
        doc['config']['experiment']['T1_intrinsic_us'] = 90.
        doc['notes'] += ' Second branch changes intrinsic T1 from 50 to 90 µs and reuses prior compatible stages.'
        app.projects.save(user, project, doc, state['draft_version'])
        changed = run('report', 'Change T1; reuse layout and quantum model', initial)
        run('fabrication', 'Chip and wafer process candidates; laboratory review required', changed)
        shutil.copy2(app.projects.export(user, project), out / 'al-si-research.sqe.zip')

        # A second capsule demonstrates an intentionally unfinished new project.
        draft_project = app.projects.create(user, 'Unfinished device study')
        state = app.projects.detail(user, draft_project)
        partial = state['document']
        partial['config']['targets']['f01_GHz'] = None
        partial['notes'] = 'Work in progress. Choose f01 before calculation. This incomplete draft is intentionally saved.'
        app.projects.save(user, draft_project, partial, state['draft_version'])
        shutil.copy2(app.projects.export(user, draft_project), out / 'unfinished-study.sqe.zip')
    print('Wrote complete and intentionally unfinished project capsules to', out)


if __name__ == '__main__':
    main()
