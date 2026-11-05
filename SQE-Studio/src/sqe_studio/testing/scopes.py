"""Implementation files that make each selected test result comparable."""
from pathlib import Path

PREFIX='src/sqe_studio/'
BASE=('src/sqe_studio/testing/*.py','automatic_test_plan.json')
HTTP=('src/sqe_studio/http_api/*.py',PREFIX+'server.py',PREFIX+'web_assets.py',
      PREFIX+'web/*.js',PREFIX+'web/*.json',PREFIX+'web/modules/*.js',
      PREFIX+'contracts.py',PREFIX+'store.py')
EXTRACTION=HTTP+(PREFIX+'interop/*.py',PREFIX+'adapters/*.py',PREFIX+'worker.py',
                 PREFIX+'jobs.py',PREFIX+'orchestration/*.py')
PATTERNS={
 'transmon_chain':EXTRACTION+('src/sqe_studio/transmon_design.py',
                            'src/sqe_studio/design_library.py',
                            'tests/fixtures/palace_spheres_0_16/**/*'),
 'integrity':('tools/verify_release_source.py','tools/science_first_gate.py',
              PREFIX+'governance.py','config/core_hashes.json','config/core_changes.json',
              'docs/SINGLE_TRANSMON.md','DEVELOPMENT_POLICY.json'),
 'targeted':(PREFIX+'**/*.py','tests/core/test_current_*.py',
             'tests/quantum/test_basis_references.py','tests/fields/test_reader_contracts.py',
             'tests/fields/test_field_comparison.py','tests/extraction/test_conditional_transmon.py',
             'tests/fixtures/em/dev74-recorded-reference.zip')+HTTP,
 'http':HTTP+('scripts/qualification_installed_smoke.py',),
 'browser':HTTP+('scripts/browser_local_smoke.py','tests/ui/test_browser.py'),
 'extraction':EXTRACTION+('tests/extraction/test_conditional_transmon.py',),
 'quantum':(PREFIX+'adapters/scqubits_adapter.py',PREFIX+'eda/scientific_references.py'),
 'rf':(PREFIX+'adapters/josephson_adapter.py',PREFIX+'interop/native_rf_evidence.py'),
 'cad':(PREFIX+'adapters/quantum_metal_adapter.py',PREFIX+'design_library.py',
        PREFIX+'transmon_design.py'),
 'fields':(PREFIX+'eda/upstream_vtk_probe.py',PREFIX+'interop/native_field.py'),
 'field_compare':(PREFIX+'eda/upstream_field_compare.py',PREFIX+'interop/native_field.py'),
 'em':(PREFIX+'native_em_qualification.py',PREFIX+'adapters/sqdmetal_palace_adapter.py'),
 'em_convergence':(PREFIX+'native_em_qualification.py',PREFIX+'adapters/sqdmetal_palace_adapter.py',
                   PREFIX+'eda/upstream_field_compare.py',PREFIX+'interop/em_convergence.py'),
 'regression':('tests/**/*.py','scripts/portable_regression.py',PREFIX+'**/*.py'),
 'packaging':('pyproject.toml','scripts/verify_installed_wheel.py',
              'scripts/qualification_installed_smoke.py',PREFIX+'**/*'),
}


def scope_files(root,task_id):
    root=Path(root);paths=set()
    for pattern in BASE+PATTERNS[task_id]:
        matches=[p for p in root.glob(pattern) if p.is_file() and '__pycache__' not in p.parts]
        # A missing literal is included so its MISSING_OR_LINKED marker survives.
        paths.update(matches or ([root/pattern] if not any(c in pattern for c in '*?[') else []))
    # Path ordering is case-insensitive on Windows. Hash the same relative
    # POSIX-name order on every host, including uppercase root policy files.
    return sorted(paths,key=lambda path:path.relative_to(root).as_posix())
