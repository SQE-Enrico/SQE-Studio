#!/usr/bin/env python3
"""Public, allowlisted Python distribution metadata for SCIENCE-FIRST review.

No library is imported. No home directory, package location, user project,
command output or path is printed. Metadata installed != import == scientific run.
Run with the *managed scientific Python interpreter* to assess that interpreter.
"""
from __future__ import annotations

import importlib.metadata as metadata
import json
import platform

SCHEMA = 'sqe.science-first-installed-package-inventory.v1'
# Whitelist only reviewed upstream names. Current interpreter only.
PACKAGES = {
    'SQDMetal': 'SQDMetal',
    'Quantum Metal': 'quantum-metal',
    'Gmsh': 'gmsh',
    'PyVista': 'pyvista',
    'VTK': 'vtk',
    'scqubits': 'scqubits',
    'NumPy': 'numpy',
    'SciPy': 'scipy',
    'pyEPR': 'pyEPR',
    'QuTiP': 'qutip',
}


def collect(version_getter=metadata.version):
    result = {}
    for label, package in PACKAGES.items():
        try:
            version = version_getter(package)
        except metadata.PackageNotFoundError:
            result[label] = {'status': 'NOT_INSTALLED', 'version': None}
        except (OSError, ValueError):
            result[label] = {'status': 'UNKNOWN', 'version': None}
        else:
            # Package metadata can be surprising: no arbitrary paths or text.
            import re
            if isinstance(version, str) and re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z._+!-]{0,79}', version):
                result[label] = {'status': 'INSTALLED_METADATA_ONLY', 'version': version}
            else:
                result[label] = {'status': 'UNKNOWN', 'version': None}
    return {'schema': SCHEMA, 'python_version': platform.python_version(),
            'package_metadata': result,
            'julia_and_palace': 'EXTERNAL_RUNTIME_REVIEW_REQUIRED',
            'scientific_validation': 'NOT_ESTABLISHED'}


def main():
    print(json.dumps(collect(), sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
