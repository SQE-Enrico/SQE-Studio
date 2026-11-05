"""Bounded MPI rank selection for Palace. Resource hints are NOT solver benchmarks."""
from __future__ import annotations
import os
import platform
import re
import shutil
import subprocess

MAX_MPI_RANKS = 16


def _resource_probe():
    """Return best-effort WSL CPU + RAM availability; never change WSL settings."""
    state = {'source': 'unknown', 'logical_cpus': None,
             'memory_total_gb': None, 'memory_available_gb': None}
    if platform.system() == 'Windows' and os.environ.get('SQE_PALACE_BACKEND') == 'wsl':
        launcher = shutil.which('wsl.exe')
        distro = os.environ.get('SQE_PALACE_WSL_DISTRO', '')
        if not launcher or (distro and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', distro)):
            return state
        prefix = [launcher, *(['-d', distro] if distro else []), '--exec']
        try:
            cpu = subprocess.run(prefix + ['/usr/bin/nproc'], capture_output=True,
                                 text=True, timeout=8, check=False)
            mem = subprocess.run(prefix + ['/usr/bin/cat', '/proc/meminfo'], capture_output=True,
                                 text=True, timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return state
        if cpu.returncode == 0 and cpu.stdout.strip().isdigit():
            count = int(cpu.stdout.strip())
            if 1 <= count <= 1024:
                state['logical_cpus'] = count
        if mem.returncode == 0:
            for tag, field in (('MemTotal', 'memory_total_gb'), ('MemAvailable','memory_available_gb')):
                match = re.search(r'^'+tag+r':\s*(\d+)\s+kB', mem.stdout, re.M)
                if match:
                    state[field] = round(int(match.group(1)) / (1024 ** 2), 2)
        state['source'] = 'WSL2_probed_not_memory_enforced'
    else:
        state['logical_cpus'] = os.cpu_count()
        state['source'] = 'host_cpu_only_no_memory_measurement'
    return state


def mpi_plan(requested='auto', resources=None):
    """Choose a conservative count; explicit ranks still require operator risk review.

    MPI is distributed memory: rank increases need not decrease wall time and
    can substantially increase RAM pressure. OpenMP stays at one thread.
    """
    if resources is None:
        resources = _resource_probe()
    count = resources.get('logical_cpus')
    available = resources.get('memory_available_gb')
    if type(count) is not int or not 1 <= count <= 1024:
        count = None
    if type(available) not in (int,float) or not 0 < available < 100000:
        available = None
    if requested == 'auto':
        # Conservative laptop policy based on WSL available memory, not just CPU.
        # No speedup guarantee; prior fine mesh used ~6.8 GB with two ranks.
        ceiling = (8 if available is not None and available >= 30 else
                   6 if available is not None and available >= 22 else
                   4 if available is not None and available >= 12 else 2)
        ranks = min(ceiling, count or 2, MAX_MPI_RANKS)
    elif type(requested) is int and 1 <= requested <= MAX_MPI_RANKS:
        ranks = requested
        if count is not None and ranks > count:
            raise ValueError('Requested MPI ranks exceed visible WSL/host logical CPUs')
    else:
        raise ValueError('Palace ranks must be auto or integer 1..16')
    return {'requested': requested, 'mpi_ranks': ranks, 'omp_threads':1,
            'resources': resources, 'policy': 'conservative_ranks_by_available_WSL_RAM' if requested == 'auto' else 'operator_selected_MPI_ranks',
            'ram_not_enforced': True, 'speedup_not_guaranteed': True,
            'hint': 'Palace -np uses MPI processes; WSL .wslconfig and memory bandwidth may limit scaling.'}
