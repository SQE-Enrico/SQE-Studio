"""Ensure metadata-only probe never imports scientific engines or reveals paths."""
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
p = ROOT/'tools/upstream_inventory_probe.py'
s = importlib.util.spec_from_file_location('probe', p)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)


def test_probe_only_allowlisted_metadata():
    calls = []
    def version(pkg):
        calls.append(pkg)
        if pkg=='pyvista':
            return '0.49.1'
        raise importlib.metadata.PackageNotFoundError(pkg)
    result=m.collect(version)
    assert result['scientific_validation']=='NOT_ESTABLISHED'
    assert result['package_metadata']['PyVista']=={'status':'INSTALLED_METADATA_ONLY','version':'0.49.1'}
    assert result['package_metadata']['VTK']['status']=='NOT_INSTALLED'
    assert calls==list(m.PACKAGES.values())
    assert 'location' not in json.dumps(result).lower()


def test_invalid_metadata_cannot_leak_path():
    def version(pkg):
        return '/home/user/project/file.vtu'
    result=m.collect(version)
    assert set(x['status'] for x in result['package_metadata'].values())=={'UNKNOWN'}
    assert '/home/user' not in json.dumps(result)


def test_probe_cli_is_valid_json_without_import():
    result=subprocess.run([sys.executable,str(p)], capture_output=True,text=True,check=True)
    doc=json.loads(result.stdout)
    assert doc['schema']==m.SCHEMA
    assert set(doc['package_metadata'])==set(m.PACKAGES)
