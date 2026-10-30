"""Extended product provenance is separate from the unchanged historical foundation lock."""
from pathlib import Path
import importlib.util


def test_extended_source_inventory_and_frozen_contracts():
    root = Path(__file__).resolve().parents[2]
    tool = root/'tools/verify_release_source.py'
    spec = importlib.util.spec_from_file_location('verify_extended_release_source', tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = module.verify(root)
    assert manifest['status'] == 'EXPERIMENTAL_NOT_SCIENTIFICALLY_QUALIFIED'
    assert 'src/sqe_studio/eda/use_cases.py' in manifest['files']
    assert 'docs/DEVELOPER_PRINCIPLES.md' in manifest['files']
    assert 'src/sqe_studio/eda/capabilities.py' in manifest['files']
    assert 'docs/LITERATURE_WORKFLOW_LAPTOP.md' not in manifest['files']
    assert 'scripts/laptop_resonator.py' not in manifest['files']
