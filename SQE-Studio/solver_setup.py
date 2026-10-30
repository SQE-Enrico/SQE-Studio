"""Local desktop-only bindings for installed Julia and Palace executables.

This does not install engines, edit projects, or infer scientific validity.
Only a user-approved Windows settings file under LOCALAPPDATA is touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import threading

SCHEMA = 'sqe.local-solver-settings.v1'
_DISTRO = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')


def settings_path(*, base: Path | None = None) -> Path:
    location = Path(base) if base is not None else Path(
        os.environ.get('LOCALAPPDATA') or (Path.home() / '.config'))
    return location / 'SQE-Studio' / 'solver-settings.json'


def validate(doc: dict) -> dict:
    if not isinstance(doc, dict) or set(doc) != {'schema','backend','palace_binary','wsl_distro','julia_project'}:
        raise ValueError('Unexpected local solver configuration')
    if doc['schema'] != SCHEMA:
        raise ValueError('Unsupported local solver settings version')
    backend, binary, distro, project = (doc[x] for x in ('backend','palace_binary','wsl_distro','julia_project'))
    if backend not in ('none','native','wsl') or any(not isinstance(v,str) for v in (binary,distro,project)):
        raise ValueError('Invalid local solver settings')
    if backend == 'none' and (binary or distro):
        raise ValueError('No Palace backend selected')
    if backend == 'native':
        if not binary or not Path(binary).is_absolute() or not Path(binary).is_file():
            raise ValueError('Select an existing absolute Palace executable')
        if distro:
            raise ValueError('WSL distribution applies to WSL Palace only')
    if backend == 'wsl':
        linux = PurePosixPath(binary)
        if not binary.startswith('/') or '..' in linux.parts or '\\' in binary or '\x00' in binary or '\n' in binary:
            raise ValueError('Palace WSL path must be an absolute Linux executable path')
        if distro and not _DISTRO.fullmatch(distro):
            raise ValueError('Invalid WSL distribution name')
    if project:
        path = Path(project)
        if not path.is_absolute() or not path.is_dir() or not any((path/p).is_file() for p in ('Project.toml','JuliaProject.toml')):
            raise ValueError('Select an existing Julia project containing Project.toml')
    return dict(doc)


def defaults() -> dict:
    return dict(schema=SCHEMA, backend='none', palace_binary='', wsl_distro='', julia_project='')


def load_settings(*, base: Path | None = None) -> dict:
    path = settings_path(base=base)
    if not path.exists():
        return defaults()
    return validate(json.loads(path.read_text(encoding='utf-8')))


def save_settings(doc: dict, *, base: Path | None = None) -> Path:
    content = validate(doc)
    path = settings_path(base=base)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.pending')
    try:
        pending.write_text(json.dumps(content, sort_keys=True, indent=2)+'\n', encoding='utf-8')
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)
    return path


def apply_settings(doc: dict) -> None:
    settings = validate(doc)
    # Only known environment variables are controlled. Never accept shell text.
    for key in ('SQE_PALACE_BACKEND','SQE_PALACE_BINARY','SQE_PALACE_WSL_BINARY','SQE_PALACE_WSL_DISTRO'):
        os.environ.pop(key, None)
    if settings['backend'] != 'none':
        os.environ['SQE_PALACE_BACKEND'] = settings['backend']
        key = 'SQE_PALACE_BINARY' if settings['backend'] == 'native' else 'SQE_PALACE_WSL_BINARY'
        os.environ[key] = settings['palace_binary']
        if settings['wsl_distro']:
            os.environ['SQE_PALACE_WSL_DISTRO'] = settings['wsl_distro']
    if settings['julia_project']:
        os.environ['JULIA_PROJECT'] = settings['julia_project']
    # Preserve user-selected JULIA_PROJECT when no explicit SQE binding exists.


def install_isolated_julia_package(*, base: Path | None = None, runner=None, julia=None):
    """Consent MUST be obtained by GUI before calling this function.

    Installs one published package into a distinct SQE Julia project. It does
    not modify a user's default Julia project, and never invokes a shell.
    Julia's package manager uses the network; the package/depot is local-only.
    """
    executable = julia or shutil.which('julia')
    if not executable:
        raise RuntimeError('Julia executable is not on PATH')
    project = settings_path(base=base).parent / 'julia-project'
    project.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop('JULIA_PROJECT', None)
    env['JULIA_PKG_PRECOMPILE_AUTO'] = '0'
    run = runner or subprocess.run
    args = [str(executable),'--startup-file=no','--history-file=no',
            '--project='+str(project), '-e',
            'using Pkg; Pkg.add("JosephsonCircuits"); '
            'Base.find_package("JosephsonCircuits") === nothing && error("Package unavailable")']
    try:
        outcome = run(args, shell=False, capture_output=True, text=True,
                      timeout=1800, check=False, env=env,
                      creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Julia package installation failed or timed out: '+type(exc).__name__) from exc
    if outcome.returncode != 0:
        raise RuntimeError('Julia package installation failed (exit '+str(outcome.returncode)+'): '+
                           (outcome.stderr or outcome.stdout or '')[-1200:])
    doc=load_settings(base=base)
    doc['julia_project']=str(project)
    save_settings(doc,base=base)
    return project


def settings_dialog(parent,on_busy=None):
    """Explicit local configuration, no HTTP API or solver installation."""
    import tkinter as tk
    from tkinter import filedialog, messagebox
    window = tk.Toplevel(parent)
    window.title('SQE Studio - Installed scientific solvers')
    window.geometry('790x505')
    frame = tk.Frame(window,padx=16,pady=12)
    frame.pack(fill='both',expand=True)
    tk.Label(frame,text='Connect installed Julia / Palace',font=('Segoe UI',13,'bold')).pack(anchor='w')
    tk.Label(frame,text=('Point SQE to the engines already installed on this machine. '
      'Palace in WSL uses a Linux executable path and optional distro name. '
      'This does not install or run scientific simulations.'),wraplength=745,justify='left').pack(anchor='w',pady=8)
    current = load_settings()
    backend = tk.StringVar(value=current['backend'])
    binary = tk.StringVar(value=current['palace_binary'])
    distro = tk.StringVar(value=current['wsl_distro'])
    project = tk.StringVar(value=current['julia_project'])
    modes=tk.Frame(frame);modes.pack(anchor='w')
    for value,title in [('none','Palace not configured'),('native','Palace native executable'),('wsl','Palace in WSL2')]:
        tk.Radiobutton(modes,text=title,value=value,variable=backend).pack(side='left',padx=7)
    tk.Label(frame,text='Palace executable (Windows full path or WSL Linux /path/to/palace):').pack(anchor='w')
    row=tk.Frame(frame);row.pack(fill='x')
    tk.Entry(row,textvariable=binary).pack(side='left',fill='x',expand=True)
    tk.Button(row,text='Browse native...',command=lambda:binary.set(filedialog.askopenfilename(parent=window) or binary.get())).pack(side='left',padx=4)
    def discover_wsl():
        launcher = shutil.which('wsl.exe')
        if not launcher:
            messagebox.showwarning('Palace WSL discovery','wsl.exe was not found on Windows PATH.',parent=window)
            return
        name=distro.get().strip()
        if name and not _DISTRO.fullmatch(name):
            messagebox.showerror('Palace WSL discovery','Invalid distribution name.',parent=window)
            return
        # No shell evaluation or arbitrary user commands. Spack-built Palace
        # may not be on PATH in a non-interactive WSL session: manual path remains supported.
        command=[launcher,*(['-d',name] if name else []),'--exec','/usr/bin/which','palace']
        try:
            outcome=subprocess.run(command,capture_output=True,text=True,timeout=20,check=False,
                                   shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError,subprocess.TimeoutExpired) as exc:
            messagebox.showerror('Palace WSL discovery',type(exc).__name__,parent=window)
            return
        found=outcome.stdout.strip()
        if outcome.returncode==0 and found.startswith('/') and '\n' not in found:
            binary.set(found);backend.set('wsl')
            messagebox.showinfo('Palace found','WSL Palace executable path was detected. Save and restart to verify --version.',parent=window)
        else:
            messagebox.showwarning('Palace not on WSL PATH',
              'A Palace executable was not found on this distro PATH. If Palace was installed with Spack, '
              'it may require an activated Spack environment; enter its absolute Linux executable path manually.',parent=window)
    tk.Button(row,text='Find in WSL',command=discover_wsl).pack(side='left',padx=4)
    tk.Label(frame,text='WSL distribution (optional, blank = default; e.g. Ubuntu):').pack(anchor='w',pady=(7,0))
    tk.Entry(frame,textvariable=distro).pack(fill='x')
    tk.Label(frame,text='Existing Julia project (optional; blank = default installed Julia environment):').pack(anchor='w',pady=(7,0))
    row2=tk.Frame(frame);row2.pack(fill='x')
    tk.Entry(row2,textvariable=project).pack(side='left',fill='x',expand=True)
    tk.Button(row2,text='Browse project...',command=lambda:project.set(filedialog.askdirectory(parent=window) or project.get())).pack(side='left',padx=4)
    tk.Label(frame,text=('Julia packages must be present in the selected project/depot. '
       'An installed Julia executable does not imply that JosephsonCircuits.jl is installed.'),
       justify='left',wraplength=740).pack(anchor='w',pady=9)
    def save():
        if state['busy']:
            return
        doc=dict(schema=SCHEMA,backend=backend.get(),palace_binary=binary.get().strip(),
                 wsl_distro=distro.get().strip(),julia_project=project.get().strip())
        try:
            save_settings(doc)
        except (OSError,ValueError) as exc:
            messagebox.showerror('Solver settings',str(exc),parent=window)
            return
        messagebox.showinfo('Solver settings saved',
            'Restart SQE Studio, then run Comprehensive qualification. '
            'Palace --version and native Julia package checks will be recorded separately from EM/quantum results.',
            parent=window)
        window.destroy()
    state = {'busy':False}
    install_button = None
    def install_clicked():
        if state['busy']:
            return
        if not messagebox.askyesno('Install scientific Julia dependency',
                'Install the official JosephsonCircuits.jl package into a NEW, isolated SQE Julia project?\n'
                'This downloads Julia dependencies and writes only to SQE Julia project and package cache.\n'
                'Your existing Julia projects are not changed. This does NOT qualify RF physics.',parent=window):
            return
        state['busy']=True
        install_button.configure(state='disabled')
        if on_busy:
            on_busy(True)
        def worker():
            try:
                result = install_isolated_julia_package()
                error = None
            except Exception as exc:
                result = None
                error = str(exc)
            def finish():
                state['busy']=False
                if on_busy:on_busy(False)
                install_button.configure(state='normal')
                if error:
                    messagebox.showerror('Julia package install',error[:1300],parent=window)
                else:
                    project.set(str(result))
                    messagebox.showinfo('Julia package installed',
                       'Isolated SQE Julia project prepared. Restart SQE, then run Comprehensive qualification. '
                       'The actual JosephsonCircuits native tests must still pass.',parent=window)
            window.after(0,finish)
        threading.Thread(target=worker,daemon=False,name='sqe-julia-package-setup').start()
    install_button=tk.Button(frame,text='Install JosephsonCircuits.jl into isolated SQE Julia project...',
                             command=install_clicked)
    install_button.pack(anchor='w',pady=3)
    def safe_close():
        if not state['busy']:
            window.destroy()
    window.protocol('WM_DELETE_WINDOW',safe_close)
    row3=tk.Frame(frame);row3.pack(anchor='w',pady=8)
    tk.Button(row3,text='Save and restart SQE',command=save).pack(side='left',padx=5)
    tk.Button(row3,text='Cancel',command=safe_close).pack(side='left',padx=5)
    return window
