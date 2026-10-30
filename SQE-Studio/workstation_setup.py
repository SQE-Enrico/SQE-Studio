"""Opt-in, Windows-only scientific workstation bootstrap for SQE Studio.

A desktop administrative helper, not an HTTP endpoint or a simulation path.
Never silently downloads engines or modifies system Python or user projects.
"""
from __future__ import annotations

import hashlib
import json
import re
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from sqdmetal_source import acquire_source, extract_checked, UpstreamSourceError
from typing import Callable

PYTHON_VERSION = (3, 11)
# These are reviewed package candidates, NOT a qualified solver stack.
PACKAGES = {
    'test_tools': ('setuptools==80.9.0', 'wheel==0.45.1', 'build==1.3.0', 'pytest>=8,<10'),
    'scqubits': ('scqubits==4.3.1',),
    'gmsh': ('gmsh==4.15.2',),
    'quantum_metal': ('quantum-metal==0.9.0',),
    'browser': ('playwright>=1.55,<2', 'pytest-playwright>=0.6,<1'),
}
# SQDMetal is installed from a pinned official GitHub source snapshot or an
# explicitly selected local source folder; never from an unpinned pip URL.
INSTALL_GROUPS = (*PACKAGES, 'sqdmetal')
SETUP_OPTIONS = (
    ('test_tools','Build + pytest (needed for wheel and software tests)'),
    ('scqubits','scqubits 4.3.1 (quantum spectra)'),
    ('gmsh','Gmsh 4.15.2 (mesh API, not Palace)'),
    ('quantum_metal','Quantum Metal 0.9.0 (geometry/GDS; needs native tests)'),
    ('sqdmetal','SQDMetal (Gmsh / Palace bridge; automatic official source or local folder)'),
    ('browser','Playwright + Chromium (browser automation; downloads a browser)'),
)


def _local_base(base: Path | None) -> Path:
    if base is None:
        if os.name != 'nt':
            raise RuntimeError('Managed setup supports Windows only')
        value = os.environ.get('LOCALAPPDATA')
        if not value:
            raise RuntimeError('LOCALAPPDATA is unavailable')
        return Path(value)
    return Path(base)


def _project_digest(project: Path) -> str:
    return hashlib.sha256(str(project.resolve()).casefold().encode('utf-8')).hexdigest()


def _environments_base(base: Path | None) -> Path:
    return _local_base(base) / 'SQE-Studio' / 'environments'


def _environment_marker(location: Path) -> dict | None:
    """Read a known, path-bound local marker. Never import code to discover it."""
    try:
        doc = json.loads((location / 'ready.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(doc, dict) or doc.get('schema') != 'sqe.local-python-runtime.v1':
        return None
    if doc.get('python_version') != '3.11':
        return None
    ident = location.name
    if not re.fullmatch(r'[a-f0-9]{16}', ident):
        return None
    digest = doc.get('source_path_sha256')
    if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest) or digest[:16] != ident:
        return None
    if not (location / 'venv' / 'Scripts' / 'python.exe').is_file():
        return None
    return doc


def _bind_file(project: Path, base: Path | None) -> Path:
    return _local_base(base) / 'SQE-Studio' / 'bindings' / (_project_digest(project)[:16] + '.json')


def _bound_location(project: Path, base: Path | None) -> Path | None:
    try:
        doc = json.loads(_bind_file(project, base).read_text(encoding='utf-8'))
        ident = doc.get('environment_id')
        if (doc.get('schema') != 'sqe.local-runtime-binding.v1' or
                doc.get('source_path_sha256') != _project_digest(project) or
                not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{16}', ident)):
            return None
        location = _environments_base(base) / ident
        if location.is_symlink() or _environment_marker(location) is None:
            return None
        return location
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def managed_root(project: Path, *, base: Path | None = None) -> Path:
    """Explicit local bindings survive source-folder moves; never auto-bind another project."""
    bound = _bound_location(project, base)
    return bound if bound is not None else _environments_base(base) / _project_digest(project)[:16]


def managed_python(project: Path, *, base: Path | None = None) -> Path | None:
    location = managed_root(project, base=base)
    if location.is_symlink():
        return None
    return location / 'venv' / 'Scripts' / 'python.exe' if _environment_marker(location) else None


def environment_inventory(project: Path, *, base: Path | None = None) -> dict:
    """Metadata-only local discovery; no package import, subprocess or path disclosure."""
    location = _environments_base(base)
    items = []
    selected = managed_root(project, base=base)
    if location.is_dir():
        for candidate in sorted(location.iterdir()):
            if candidate.is_symlink() or not candidate.is_dir() or not re.fullmatch('[a-f0-9]{16}', candidate.name):
                continue
            marker = _environment_marker(candidate)
            items.append({'id':candidate.name, 'ready':marker is not None,
                          'python_exists':(candidate/'venv'/'Scripts'/'python.exe').is_file(),
                          'selected':candidate == selected,
                          'current_project':candidate.name == _project_digest(project)[:16]})
    return {'active_python': str(sys.version_info.major)+'.'+str(sys.version_info.minor),
            'managed_selected':managed_python(project,base=base) is not None,
            'candidates':items}


def bind_existing_environment(project: Path, environment_id: str, *, base: Path | None = None,
                              probe=None) -> Path:
    """Explicit desktop re-link. Probe the interpreter, not a solver, before trusting it.

    The existing venv, its original ready marker, and installed packages are not modified.
    """
    if not isinstance(environment_id, str) or not re.fullmatch('[a-f0-9]{16}', environment_id):
        raise ValueError('Unrecognized local environment identity')
    location = _environments_base(base) / environment_id
    if location.is_symlink() or _environment_marker(location) is None:
        raise ValueError('Selected environment has no valid ready marker and Python 3.11')
    python = location / 'venv' / 'Scripts' / 'python.exe'
    run = probe if probe is not None else subprocess.run
    try:
        result = run([str(python), '-I', '-c',
                      'import json,struct,sys;print(json.dumps({"version":list(sys.version_info[:2]),"bits":struct.calcsize("P")*8}))'],
                     capture_output=True, text=True, check=False, timeout=20,
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        facts = json.loads(result.stdout.strip())
        if result.returncode != 0 or facts != {'version':[3, 11], 'bits':64}:
            raise ValueError('The existing environment does not run Python 3.11 x64')
    except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError) as exc:
        raise ValueError('Cannot validate the selected Python 3.11 environment') from exc
    dest = _bind_file(project, base)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {'schema':'sqe.local-runtime-binding.v1',
               'source_path_sha256':_project_digest(project), 'environment_id':environment_id}
    temp = dest.with_suffix('.pending')
    try:
        temp.write_text(json.dumps(payload,indent=2)+'\n', encoding='utf-8')
        os.replace(temp, dest)
    finally:
        temp.unlink(missing_ok=True)
    return python


def reconnect_dialog(parent, project: Path):
    """Opt-in GUI to reuse a previously installed Python 3.11 environment."""
    import tkinter as tk
    from tkinter import messagebox
    window = tk.Toplevel(parent)
    window.title('SQE Studio - Reconnect scientific environment')
    window.geometry('700x370')
    frame = tk.Frame(window, padx=14, pady=12)
    frame.pack(fill='both', expand=True)
    tk.Label(frame,text='Reuse a previously installed scientific Python 3.11',
             font=('Segoe UI',13,'bold')).pack(anchor='w')
    tk.Label(frame,text=('Only a local environment with a valid setup marker can be selected. '
           'SQE checks the Python executable before connecting it. Nothing is reinstalled, '
           'and solver results still need native qualification.'),
           wraplength=650,justify='left').pack(anchor='w',pady=10)
    inventory = environment_inventory(project)
    candidates = [it for it in inventory['candidates'] if it['ready']]
    if not candidates:
        tk.Label(frame,text=('No ready Python 3.11 environment was found. An incomplete setup may '
              'have created an environment without successfully installing Build + pytest. '
              'Use Prepare scientific environment to inspect its installation result.'),
              wraplength=640,justify='left').pack(anchor='w',pady=12)
    else:
        chosen = tk.StringVar(value=next((it['id'] for it in candidates if it['selected']),candidates[0]['id']))
        for it in candidates:
            suffix = ' (already selected)' if it['selected'] else ' (existing installation)'
            tk.Radiobutton(frame,text='Environment '+it['id']+suffix,
                           variable=chosen,value=it['id']).pack(anchor='w')
        def connect():
            if not messagebox.askyesno('Reuse installed environment',
                    'Connect this SQE Studio extraction to the existing Python 3.11 installation?\n'
                    'The source code, packages and projects will not be changed.',parent=window):
                return
            try:
                bind_existing_environment(project,chosen.get())
            except ValueError as exc:
                messagebox.showerror('Unable to reconnect',str(exc),parent=window)
                return
            messagebox.showinfo('Environment reconnected',
                'Close SQE Studio and reopen it. Then run Comprehensive qualification.',parent=window)
            window.destroy()
        tk.Button(frame,text='Reconnect selected environment',command=connect).pack(anchor='w',pady=12)
    tk.Button(frame,text='Close',command=window.destroy).pack(anchor='w',pady=8)
    return window


def find_python_311() -> list[str] | None:
    """Do not auto-download a Python interpreter or rely on the current Python 3.15."""
    if os.name != 'nt':
        return None
    commands = ([sys.executable] if sys.version_info[:2] == PYTHON_VERSION else []) + [['py', '-3.11']]
    for candidate in commands:
        args = candidate if isinstance(candidate, list) else [candidate]
        try:
            result = subprocess.run(args + ['-c',
                'import sys,struct;print(str(sys.version_info.major)+"."+str(sys.version_info.minor)+" "+str(struct.calcsize("P")*8))'],
                capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0 and result.stdout.strip() == '3.11 64':
                return args
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def validate_sqdmetal_source(project: Path, source: Path) -> Path:
    """Validate the operator-selected upstream source BEFORE installing any group.

    This verifies package shape, not provenance: the operator must review and
    approve the upstream commit and its dependencies. Never auto-clone or use
    an arbitrary URL as executable install input.
    """
    import tomllib
    try:
        source = Path(source).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError('Choose an existing extracted SQDMetal source folder') from exc
    if not source.is_dir() or not (source / 'SQDMetal' / 'PALACE' / 'Eigenmode_Simulation.py').is_file():
        raise ValueError('Select an extracted SQDMetal upstream source directory, not the SQE project')
    config = source / 'pyproject.toml'
    if not config.is_file() or config.stat().st_size > 64_000:
        raise ValueError('SQDMetal upstream pyproject.toml missing or unsafe')
    try:
        metadata_doc = tomllib.loads(config.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('SQDMetal pyproject metadata cannot be parsed') from exc
    if metadata_doc.get('project', {}).get('name', '').casefold() != 'sqdmetal':
        raise ValueError('Selected source does not declare the SQDMetal distribution')
    project = Path(project).resolve()
    if source == project or project in source.parents:
        raise ValueError('Do not install source code from inside the SQE application tree')
    return source


def install_selected(project: Path, selected: list[str], notify: Callable[[str], None],
                     *, base: Path | None = None, python_311: list[str] | None = None,
                     run=subprocess.run, sqdmetal_source: Path | None = None,
                     sqdmetal_refresh: bool = False) -> dict:
    """Install operator-approved groups in isolated Python 3.11, one at a time.

    SQDMetal's default acquires a fixed Git commit ZIP over HTTPS from the
    official repository, checks its integrity, then installs it with pip.
    Once pinned, the same immutable source is reused unless the operator
    explicitly requests an upstream update. Local folder is an advanced mode.
    No shell, arbitrary Git URL, Palace download, or Julia edit.
    """
    if not selected or any(key not in INSTALL_GROUPS for key in selected) or len(set(selected)) != len(selected):
        raise ValueError('Select one or more known installation groups')
    if os.name != 'nt' and base is None:
        raise RuntimeError('This installer is for Windows 11')
    # Validate optional advanced local source BEFORE any package installation.
    if 'sqdmetal' in selected and sqdmetal_source is not None:
        sqdmetal_source = validate_sqdmetal_source(project, sqdmetal_source)
    if sqdmetal_refresh and 'sqdmetal' not in selected:
        raise ValueError('An upstream refresh requires SQDMetal to be selected')
    if sqdmetal_refresh and sqdmetal_source is not None:
        raise ValueError('Cannot refresh the official source while using a local folder')
    existing = managed_python(project, base=base)
    command = python_311 if python_311 is not None else (None if existing else find_python_311())
    if not existing and not command:
        raise RuntimeError('Python 3.11 x64 is required. Install it from python.org, then reopen this window.')
    # A source acquisition failure must never become a success, or partially
    # install unrelated selected packages in this batch.
    upstream = None
    if 'sqdmetal' in selected and sqdmetal_source is None:
        upstream = acquire_source(_local_base(base)/'SQE-Studio'/'sources'/'sqdmetal',
                                  notify, refresh=sqdmetal_refresh)
    location = managed_root(project, base=base)
    location.mkdir(parents=True, exist_ok=True)
    pyexe = location / 'venv' / 'Scripts' / 'python.exe'
    def execute(args: list[str], label: str, timeout: int) -> tuple[bool,str]:
        notify('Running '+label+' (may download packages from PyPI)')
        try:
            outcome = run(args, shell=False, capture_output=True, text=True, timeout=timeout, check=False,
                          env={**{k:v for k,v in os.environ.items() if k not in ('PIP_INDEX_URL','PIP_EXTRA_INDEX_URL','PIP_FIND_LINKS')},
                               'PIP_CONFIG_FILE':os.devnull,'PYTHONNOUSERSITE':'1','PIP_DISABLE_PIP_VERSION_CHECK':'1'})
            return outcome.returncode == 0, (outcome.stdout or '')[-2500:]+'\n'+(outcome.stderr or '')[-2500:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, type(exc).__name__
    if not pyexe.is_file():
        ok, detail = execute(command+['-m','venv',str(location/'venv')], 'Python 3.11 isolated environment', 120)
        if not ok:
            raise RuntimeError('Creating Python 3.11 environment failed: '+detail[-500:])
    marker = location/'ready.json'
    results = {}
    for category in selected:
        if category == 'sqdmetal':
            # Uses the same approved source installer as the former standalone dialog.
            # A new environment first needs a successful test_tools bootstrap.
            if managed_python(project, base=base) is None:
                results[category] = {'status':'FAILED', 'message':'Prepare Build + pytest first to activate scientific Python 3.11'}
                notify('SQDMetal: failed - scientific Python 3.11 is not ready')
                continue
            if upstream is None:
                outcome = install_local_sqdmetal(project, sqdmetal_source, notify, base=base, run=run)
                message = outcome['reason']+'; operator-selected local source (SHA not pinned by SQE)'
            else:
                try:
                    with tempfile.TemporaryDirectory(prefix='sqe-sqdmetal-install-') as tmp:
                        source = extract_checked(upstream,Path(tmp))
                        # Reuse the same official shape checks as a local folder.
                        outcome = install_local_sqdmetal(project, source, notify, base=base, run=run)
                except (OSError, ValueError, RuntimeError) as exc:
                    outcome = {'status':'FAILED','reason':'Verified source could not be extracted or installed: '+str(exc)[:300]}
                message = (outcome['reason']+'; official sqdlab/SQDMetal commit '+upstream['commit']+
                           '; archive sha256='+upstream['archive_sha256'])
            ok = outcome['status'] == 'INSTALLED_UNQUALIFIED'
            results[category] = {'status':outcome['status'], 'message':message}
            notify('SQDMetal: '+('installed, native qualification required' if ok else 'failed; see log'))
            continue
        args = [str(pyexe),'-m','pip','install','--no-input','--disable-pip-version-check', '--index-url','https://pypi.org/simple', *PACKAGES[category]]
        ok, detail = execute(args,category,1200)
        results[category] = {'status':'INSTALLED_UNVERIFIED' if ok else 'FAILED',
                             'message':('Packages installed; native qualification still required' if ok
                                        else 'Installation failed; review the local setup log')}
        notify(category+(': installed; run qualification next' if ok else ': failed (details below)'))
        if not ok:
            notify(detail[-1100:])
        if category == 'test_tools' and ok:
            marker.write_text(json.dumps({
                'schema':'sqe.local-python-runtime.v1',
                'python_version':'3.11',
                'source_path_sha256':(_environment_marker(location) or {}).get('source_path_sha256',_project_digest(project)),
                'note':'Installation not native scientific qualification'},indent=2)+'\n',encoding='utf-8')
        if category == 'browser' and ok:
            browser_ok,browser_log = execute([str(pyexe),'-m','playwright','install','chromium'],
                                              'Playwright Chromium browser',900)
            if not browser_ok:
                results[category] = {'status':'FAILED','message':'Browser download failed; Python package may be installed'}
                notify(browser_log[-1000:])
    return {'environment':str(location),'groups':results,'activated':managed_python(project,base=base) is not None}


def install_local_sqdmetal(project: Path, source: Path, notify: Callable[[str], None],
                           *, base: Path | None = None, run=subprocess.run) -> dict:
    """Opt-in installation of user-selected upstream source into existing managed Python.

    No git execution, no direct URL install, no Palace installation, no shell.
    An upstream source tree is executable third-party code: the GUI requires
    explicit review/consent. This is not a scientific qualification.
    """
    python = managed_python(project, base=base)
    if python is None:
        raise ValueError('Connect a prepared scientific Python 3.11 environment first')
    source = validate_sqdmetal_source(project, source)
    notify('Installing selected SQDMetal source into the prepared Python 3.11 only')
    cmd = [str(python), '-m', 'pip', 'install', '--no-input',
           '--disable-pip-version-check', str(source)]
    env = {k: v for k, v in os.environ.items() if k not in (
           'PIP_INDEX_URL', 'PIP_EXTRA_INDEX_URL', 'PIP_FIND_LINKS')}
    env.update(PIP_CONFIG_FILE=os.devnull, PYTHONNOUSERSITE='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
    try:
        result = run(cmd, shell=False, capture_output=True, text=True,
                     timeout=1200, check=False, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'status': 'FAILED', 'reason': type(exc).__name__}
    notify('SQDMetal pip exit code: '+str(result.returncode))
    if result.returncode != 0:
        # Local desktop diagnostic only; user decides what to share.
        notify(((result.stdout or '') + '\n' + (result.stderr or ''))[-2000:])
        return {'status': 'FAILED', 'reason': 'pip installation failed'}
    return {'status': 'INSTALLED_UNQUALIFIED',
            'reason': 'Run Comprehensive native SQDMetal API gate, then reviewed mesh/deck and Palace solve'}


def setup_dialog(parent, project: Path, on_busy: Callable[[bool], None] | None = None):
    """Purely local Tk desktop setup; no HTTP hooks and no installation by default."""
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, filedialog
    import queue
    import threading
    import webbrowser
    window = tk.Toplevel(parent)
    window.title('SQE Studio - Prepare workstation')
    window.geometry('820x700')
    window.minsize(660,510)
    frame = tk.Frame(window,padx=15,pady=12)
    frame.pack(fill='both',expand=True)
    tk.Label(frame,text='Prepare a separate Python 3.11 scientific environment',
             font=('Segoe UI',14,'bold')).pack(anchor='w')
    tk.Label(frame,text=('Detected SQE launcher: Python '+platform.python_version()+'; '+
              'Windows solver stacks should use an isolated 64-bit Python 3.11 runtime. '+
              'Nothing will be installed until you choose packages and confirm.'),
             wraplength=730,justify='left').pack(anchor='w',pady=8)
    connected = managed_python(project) is not None
    available = connected or bool(find_python_311())
    status = ('Managed scientific Python 3.11 connected' if connected else
              'Python 3.11 x64 detected' if available else 'Python 3.11 x64 NOT FOUND')
    tk.Label(frame,text=status,fg=('green' if available else '#a03228')).pack(anchor='w')
    selected = {}
    for key,label in SETUP_OPTIONS:
        variable = tk.BooleanVar(value=(key=='test_tools' and managed_python(project) is None))
        selected[key]=variable
        tk.Checkbutton(frame,text=label,variable=variable).pack(anchor='w')
    tk.Label(frame,text=('SQDMetal: the default downloads the official GitHub source at an exact Git commit, '
          'verifies the ZIP and saves its SHA-256/pin for repeat installs. GitHub source code and dependencies '
          'are third-party code, not independently security-audited by SQE. First use requires Internet; '
          'subsequent installs reuse the verified cache. Palace WSL2 and Julia are unchanged.'),
          wraplength=730,justify='left').pack(anchor='w',pady=7)
    sqd_source = tk.StringVar(value='')
    sqd_mode = tk.StringVar(value='official')
    sqd_refresh = tk.BooleanVar(value=False)
    source_frame = tk.Frame(frame)
    tk.Label(source_frame,text='SQDMetal source acquisition').pack(anchor='w')
    modes = tk.Frame(source_frame);modes.pack(anchor='w')
    tk.Radiobutton(modes,text='Automatic official GitHub source (pinned and SHA-256 verified)',
                   variable=sqd_mode,value='official').pack(anchor='w')
    tk.Radiobutton(modes,text='Local source folder (advanced / offline)',
                   variable=sqd_mode,value='local').pack(anchor='w')
    local_line = tk.Frame(source_frame)
    tk.Entry(local_line,textvariable=sqd_source,state='readonly').pack(side='left',fill='x',expand=True)
    tk.Button(local_line,text='Choose folder',command=lambda:sqd_source.set(
        filedialog.askdirectory(parent=window) or sqd_source.get())).pack(side='left',padx=4)
    refresh_box = tk.Checkbutton(source_frame,text='Explicitly update the saved official Git revision',variable=sqd_refresh)
    tk.Button(source_frame,text='View official repository',command=lambda:webbrowser.open(
        'https://github.com/sqdlab/SQDMetal')).pack(anchor='w')
    def display_sqd_source(*_):
        if selected['sqdmetal'].get():
            source_frame.pack(fill='x',pady=6)
        else:
            source_frame.pack_forget()
        local_line.pack_forget()
        refresh_box.pack_forget()
        if selected['sqdmetal'].get():
            if sqd_mode.get() == 'local':
                local_line.pack(fill='x',pady=4)
            else:
                refresh_box.pack(anchor='w')
    selected['sqdmetal'].trace_add('write',display_sqd_source)
    sqd_mode.trace_add('write',display_sqd_source)
    display_sqd_source()
    log = scrolledtext.ScrolledText(frame,height=12,wrap='word')
    log.pack(fill='both',expand=True)
    events=queue.Queue()
    running={'value':False}
    controls=tk.Frame(frame);controls.pack(pady=8)
    def append(text):
        log.insert('end',text+'\n');log.see('end')
    def poll():
        try:
            while True:
                kind,info=events.get_nowait()
                if kind=='line':append(info)
                else:
                    running['value']=False;button.configure(state='normal')
                    if on_busy:on_busy(False)
                    if kind=='error':
                        append('Setup stopped: '+info)
                        messagebox.showerror('SQE workstation setup',info,parent=window)
                    else:
                        for group, outcome in info['groups'].items():
                            append(group+': '+outcome['status']+' - '+outcome['message'])
                        failed=[k for k,v in info['groups'].items() if v['status']=='FAILED']
                        if failed:
                            append('Setup PARTIAL / FAILED: '+', '.join(failed)+'. Review the log; do not count these as installed.')
                            messagebox.showwarning('Setup incomplete', 'Failed groups: '+', '.join(failed)+'. See the log.',parent=window)
                        else:
                            append('Selected packages installed; native engine qualification is still required. Restart SQE Studio.')
                            messagebox.showinfo('SQE workstation setup','Selected installation groups completed. Restart SQE Studio and run Comprehensive qualification.',parent=window)
        except queue.Empty:pass
        if window.winfo_exists():window.after(200,poll)
    def start():
        keys=[key for key,v in selected.items() if v.get()]
        if not keys:
            messagebox.showwarning('Choose packages','Select at least one package category.',parent=window);return
        if 'test_tools' not in keys and managed_python(project) is None:
            messagebox.showwarning('Bootstrap first','Select Build + pytest for the first setup.',parent=window);return
        if managed_python(project) is None and not find_python_311():
            messagebox.showerror('Python 3.11 not found',
                'Install 64-bit Python 3.11 from python.org first, then reopen this window. No changes were made.',parent=window);return
        source_dir = None
        refreshing = 'sqdmetal' in keys and sqd_mode.get() == 'official' and sqd_refresh.get()
        if 'sqdmetal' in keys and sqd_mode.get() == 'local':
            if not sqd_source.get():
                messagebox.showwarning('SQDMetal source required', 'Choose a local SQDMetal source folder, or use automatic official download.',parent=window);return
            try:
                source_dir = validate_sqdmetal_source(project, Path(sqd_source.get()))
            except ValueError as exc:
                messagebox.showerror('Invalid SQDMetal source',str(exc),parent=window);return
        origin = ('SQDMetal: install operator-selected local source code. ' if source_dir else
                  'SQDMetal: download an official GitHub Git-commit ZIP over HTTPS (or reuse the saved pinned ZIP); '
                  'record its SHA-256 and install third-party source code and declared PyPI dependencies. '
                  'The source is not independently audited by SQE. ' if 'sqdmetal' in keys else '')
        message=('Install '+', '.join(keys)+' in the user-local scientific Python 3.11? '
                 +origin+('You explicitly chose to update the pinned Git revision. ' if refreshing else '')+
                 'Packages may be downloaded. Existing package versions may change due to dependencies. '
                 'No system Python, Palace or Julia will be modified. Continue?')
        if not messagebox.askyesno('Approve workstation downloads',message,parent=window):return
        button.configure(state='disabled');running['value']=True
        if on_busy:on_busy(True)
        append('Starting explicitly approved package setup...')
        def worker():
            try:
                result=install_selected(project,keys,lambda s:events.put(('line',s)),
                                        sqdmetal_source=source_dir, sqdmetal_refresh=refreshing)
                events.put(('done',result))
            except Exception as exc:
                events.put(('error',str(exc)[:700]))
        threading.Thread(target=worker,daemon=True).start()
    button=tk.Button(controls,text='Install selected packages',command=start)
    button.pack(side='left',padx=5)
    tk.Button(controls,text='Get Python 3.11',command=lambda:webbrowser.open('https://www.python.org/downloads/')).pack(side='left',padx=5)
    tk.Button(controls,text='Close',command=lambda: None if running['value'] else window.destroy()).pack(side='left',padx=5)
    window.protocol('WM_DELETE_WINDOW',lambda: None if running['value'] else window.destroy())
    window.after(200,poll)
    return window
