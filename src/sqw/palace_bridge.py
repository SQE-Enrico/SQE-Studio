"""Palace launch adapter: native Linux executable or user-owned WSL2/Spack install.

No user-controlled shell commands. Paths are translated by wslpath; the backend
is configured by the machine administrator, never by a Web request.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

WSL_DISTRO_RE = re.compile(r'^[a-zA-Z0-9_.-]{1,64}$')
BACKENDS = ('auto', 'native', 'wsl')


def backend():
    value = os.getenv('SQE_PALACE_BACKEND', 'auto').lower()
    if value not in BACKENDS:
        raise ValueError('SQE_PALACE_BACKEND must be auto, native or wsl')
    return 'wsl' if value == 'auto' and os.name == 'nt' else ('native' if value == 'auto' else value)


def distro():
    value = os.getenv('SQE_WSL_DISTRO', 'Ubuntu')
    if not WSL_DISTRO_RE.fullmatch(value):
        raise ValueError('Invalid SQE_WSL_DISTRO; use a simple installed distribution name')
    return value


def wsl_path(path, *, invoke=subprocess.run):
    source = str(Path(path).resolve())
    result = invoke(['wsl.exe', '-d', distro(), '--exec', 'wslpath', '-a', '-u', source],
                    text=True, capture_output=True, timeout=20, check=True)
    translated = result.stdout.strip()
    if not translated.startswith('/') or '\n' in translated:
        raise RuntimeError('WSL did not return a valid Linux path')
    return translated


def command(out, problem, ranks, executable='palace', *, invoke=subprocess.run):
    if backend() == 'native':
        exe = shutil.which(executable) or (str(Path(executable).resolve()) if Path(executable).is_file() else None)
        if not exe:
            raise FileNotFoundError('Palace not installed on this worker; run WINDOWS-PALACE-SETUP.cmd or install Palace on Linux')
        if exe.endswith('.bin'):
            mpi = shutil.which('mpiexec') if ranks > 1 else None
            if ranks > 1 and not mpi:
                raise FileNotFoundError('mpiexec is required for parallel Palace .bin')
            return ([mpi, '-n', str(ranks)] if mpi else []) + [exe, problem + '.json'], exe
        return [exe, '-np', str(ranks), problem + '.json'], exe
    if os.name != 'nt':
        raise RuntimeError('WSL backend is available only from Windows; configure native Palace on Linux')
    if not shutil.which('wsl.exe'):
        raise FileNotFoundError('wsl.exe unavailable; use WINDOWS-PALACE-SETUP.cmd')
    linux_out = wsl_path(out, invoke=invoke)
    # No untrusted project text enters bash. Windows paths converted by wslpath.
    # Run in the Linux filesystem instead of on DrvFS for MPI performance.
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'palace-wsl-run.sh'
    if not script.is_file():
        raise FileNotFoundError('WSL Palace runner not found in installation')
    linux_script = wsl_path(script, invoke=invoke)
    return ['wsl.exe', '-d', distro(), '--', 'bash', linux_script, linux_out,
            problem + '.json', str(ranks)], 'WSL2:' + distro() + ':Spack:palace'


def readiness(executable='palace'):
    result = {'backend': backend(), 'platform': platform.system(), 'configured_distro': distro(),
              'install_guide': 'docs/palace-windows.md', 'qualified': False,
              'message': '', 'gmsh_available': False, 'quantum_metal_available': False}
    try:
        from importlib.util import find_spec
        result['gmsh_available'] = find_spec('gmsh') is not None
        result['quantum_metal_available'] = find_spec('qiskit_metal') is not None
    except (ImportError, ValueError):
        pass
    if result['backend'] == 'native':
        exe = shutil.which(executable) or (str(Path(executable)) if Path(executable).is_file() else None)
        result['installed'] = bool(exe)
        result['message'] = ('Palace executable found; a benchmark is still required before qualification' if exe
                             else 'Palace not found on PATH; install via Spack or native source build')
        return result
    if os.name != 'nt':
        result.update(installed=False, message='WSL is Windows-only')
        return result
    if not shutil.which('wsl.exe'):
        result.update(installed=False, message='WSL missing: run Windows guided installation')
        return result
    # Quick bounded probe; never spawn a build or install from an HTTP GET.
    probe = 'test -x "$HOME/.sqe/palace/bin/palace" || { test -f "$HOME/.sqe/spack/share/spack/setup-env.sh" && source "$HOME/.sqe/spack/share/spack/setup-env.sh" && spack find --format "{name}" palace 2>/dev/null | grep -qx palace; }'
    try:
        done = subprocess.run(['wsl.exe', '-d', distro(), '--', 'bash', '-lc', probe],
                              text=True, capture_output=True, timeout=12, check=False)
        result['installed'] = done.returncode == 0
        result['message'] = ('Palace installation detected in WSL; run a solver benchmark for qualification'
                             if result['installed'] else 'Palace not yet installed inside WSL. Launch WINDOWS-PALACE-SETUP.cmd')
    except (OSError, subprocess.TimeoutExpired) as exc:
        result.update(installed=False, message=f'WSL probe failed: {type(exc).__name__}')
    return result
