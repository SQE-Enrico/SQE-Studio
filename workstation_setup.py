"""Opt-in, Windows-only scientific workstation bootstrap for SQE Studio.

A desktop administrative helper, not an HTTP endpoint or a simulation path.
Never silently downloads engines or modifies system Python or user projects.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
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


def managed_root(project: Path, *, base: Path | None = None) -> Path:
    """Separate source extractions get separate, user-local environments."""
    if base is None:
        if os.name != 'nt':
            raise RuntimeError('Managed setup supports Windows only')
        base_string = os.environ.get('LOCALAPPDATA')
        if not base_string:
            raise RuntimeError('LOCALAPPDATA is unavailable')
        base = Path(base_string)
    canonical = str(project.resolve()).casefold().encode('utf-8')
    identity = hashlib.sha256(canonical).hexdigest()[:16]
    return base / 'SQE-Studio' / 'environments' / identity


def managed_python(project: Path, *, base: Path | None = None) -> Path | None:
    location = managed_root(project, base=base)
    marker = location / 'ready.json'
    python = location / 'venv' / 'Scripts' / 'python.exe'
    if not (marker.is_file() and python.is_file()):
        return None
    try:
        doc = json.loads(marker.read_text(encoding='utf-8'))
        if doc.get('source_path_sha256') != hashlib.sha256(
                str(project.resolve()).casefold().encode('utf-8')).hexdigest():
            return None
        if doc.get('python_version') != '3.11':
            return None
    except (OSError, ValueError, TypeError):
        return None
    return python


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


def install_selected(project: Path, selected: list[str], notify: Callable[[str], None],
                     *, run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                     python_311: list[str] | None = None,
                     base: Path | None = None) -> dict:
    """Explicitly consented packages in a private venv, one category at a time.

    No arbitrary input is passed as a shell command. No cloning, admin elevation,
    license bypass, Palace download, or Julia project modification is attempted.
    The core environment remains usable even if an optional solver fails.
    """
    if not selected or any(key not in PACKAGES for key in selected) or len(set(selected)) != len(selected):
        raise ValueError('Select one or more known installation groups')
    if os.name != 'nt' and base is None:
        raise RuntimeError('This installer is for Windows 11')
    command = python_311 if python_311 is not None else find_python_311()
    if not command:
        raise RuntimeError('Python 3.11 x64 is required. Install it from python.org, then reopen this window.')
    location = managed_root(project, base=base)
    location.mkdir(parents=True, exist_ok=True)
    pyexe = location / 'venv' / 'Scripts' / 'python.exe'
    def execute(args: list[str], label: str, timeout: int) -> tuple[bool,str]:
        notify('Running '+label+' (may download packages from PyPI)')
        try:
            outcome = run(args, shell=False, capture_output=True, text=True, timeout=timeout, check=False,
                          env={**{k:v for k,v in os.environ.items() if k not in ('PIP_INDEX_URL','PIP_EXTRA_INDEX_URL','PIP_FIND_LINKS')},
                               'PIP_CONFIG_FILE':os.devnull,'PYTHONNOUSERSITE':'1','PIP_DISABLE_PIP_VERSION_CHECK':'1'})
            # Do not copy logs into user project or transmit them anywhere.
            return outcome.returncode == 0, (outcome.stdout or '')[-2500:]+'\n'+(outcome.stderr or '')[-2500:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, type(exc).__name__
    if not pyexe.is_file():
        ok, detail = execute(command+['-m','venv',str(location/'venv')], 'Python 3.11 isolated environment', 120)
        if not ok:
            raise RuntimeError('Creating Python 3.11 environment failed: '+detail[-500:])
    # A marker is written only after the bootstrap has a usable build/test environment.
    marker = location/'ready.json'
    results = {}
    for category in selected:
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
                'source_path_sha256':hashlib.sha256(str(project.resolve()).casefold().encode()).hexdigest(),
                'note':'Installation not native scientific qualification'},indent=2)+'\n',encoding='utf-8')
        if category == 'browser' and ok:
            browser_ok,browser_log = execute([str(pyexe),'-m','playwright','install','chromium'],
                                              'Playwright Chromium browser',900)
            if not browser_ok:
                results[category] = {'status':'FAILED','message':'Browser download failed; Python package may be installed'}
                notify(browser_log[-1000:])
    return {'environment':str(location),'groups':results,'activated':managed_python(project,base=base) is not None}


def setup_dialog(parent, project: Path, on_busy: Callable[[bool], None] | None = None):
    """Purely local Tk desktop setup; no HTTP hooks and no installation by default."""
    import tkinter as tk
    from tkinter import messagebox, scrolledtext
    import queue
    import threading
    import webbrowser
    window = tk.Toplevel(parent)
    window.title('SQE Studio - Prepare workstation')
    window.geometry('780x650')
    window.minsize(660,510)
    frame = tk.Frame(window,padx=15,pady=12)
    frame.pack(fill='both',expand=True)
    tk.Label(frame,text='Prepare a separate Python 3.11 scientific environment',
             font=('Segoe UI',14,'bold')).pack(anchor='w')
    tk.Label(frame,text=('Detected SQE launcher: Python '+platform.python_version()+'; '+
              'Windows solver stacks should use an isolated 64-bit Python 3.11 runtime. '+
              'Nothing will be installed until you choose packages and confirm.'),
             wraplength=730,justify='left').pack(anchor='w',pady=8)
    status = 'Python 3.11 x64 detected' if find_python_311() else 'Python 3.11 x64 NOT FOUND'
    tk.Label(frame,text=status,fg=('green' if status.endswith('detected') else '#a03228')).pack(anchor='w')
    options = [
        ('test_tools','Build + pytest (needed for wheel and software tests)'),
        ('scqubits','scqubits 4.3.1 (quantum spectra)'),
        ('gmsh','Gmsh 4.15.2 (mesh API, not Palace)'),
        ('quantum_metal','Quantum Metal 0.9.0 (geometry/GDS; needs native tests)'),
        ('browser','Playwright + Chromium (browser automation; downloads a browser)'),
    ]
    selected = {}
    for key,label in options:
        variable = tk.BooleanVar(value=(key=='test_tools'))
        selected[key]=variable
        tk.Checkbutton(frame,text=label,variable=variable).pack(anchor='w')
    tk.Label(frame,text=('SQDMetal is source-distributed and requires reviewed Python 3.11 dependencies. '+
          'Palace is not officially packaged for native Windows; WSL2 configuration needs manual review. '+
          'Julia/JosephsonCircuits is configured separately. No science result is certified by installation.'),
          wraplength=730,justify='left').pack(anchor='w',pady=9)
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
                        append('Completed setup. Relaunch SQE Studio to use the managed Python 3.11 environment; then rerun Comprehensive qualification.')
                        messagebox.showinfo('SQE workstation setup','Setup operation completed. Review the results, close SQE Studio and reopen it before rerunning Comprehensive.',parent=window)
        except queue.Empty:pass
        if window.winfo_exists():window.after(200,poll)
    def start():
        keys=[key for key,v in selected.items() if v.get()]
        if not keys:
            messagebox.showwarning('Choose packages','Select at least one package category.',parent=window);return
        if 'test_tools' not in keys and managed_python(project) is None:
            messagebox.showwarning('Bootstrap first','Select Build + pytest for the first setup.',parent=window);return
        if not find_python_311():
            messagebox.showerror('Python 3.11 not found',
                'Install 64-bit Python 3.11 from python.org first, then reopen this window. No changes were made.',parent=window);return
        message='This installs '+', '.join(keys)+' into a separate user-local Python 3.11 environment. Packages and Chromium may be downloaded from public package repositories. No system Python will be modified. Proceed?'
        if not messagebox.askyesno('Approve workstation downloads',message,parent=window):return
        button.configure(state='disabled');running['value']=True
        if on_busy:on_busy(True)
        append('Starting explicitly approved package setup...')
        def worker():
            try:
                result=install_selected(project,keys,lambda s:events.put(('line',s)))
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
