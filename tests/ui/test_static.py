from pathlib import Path

def test_product_does_not_ship_duplicate_workspaces():
    root=Path(__file__).resolve().parents[2]
    assets=list((root/'src/sqe_studio/web').iterdir())
    assert {p.name for p in assets}=={'index.html','app.js','style.css'}
    body=(root/'src/sqe_studio/web/app.js').read_text()
    assert 'Quantum Metal' in body and 'Revision history' in body
    assert 'Research v3 design loop' not in body
    assert 'SQE-owned' not in body

def test_no_gds_writer_or_internal_solver():
    root=Path(__file__).resolve().parents[2]
    py=(root/'src/sqe_studio').rglob('*.py')
    for f in py:
        if f.name=='quantum_metal_adapter.py':
            assert 'QGDSRenderer' in f.read_text()
        assert 'gdstk' not in f.read_text() and 'gdspy' not in f.read_text()
