"""Generate deterministic, strictly reduced-order QPU demonstration results.

Usage from repository root: python examples/quantumlab/run_examples.py
This never runs, or pretends to run, a full-wave field solver.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqw.quantumlab import analyze, preset
from sqw.lab_layout import candidate

HERE = Path(__file__).resolve().parent


def save(name: str, obj: object) -> None:
    (HERE / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> None:
    for count in (1, 4, 16):
        design = preset(count)
        save(f'QPU-{count:02d}-design.json', design)
        result = analyze(design, 'modes')
        save(f'QPU-{count:02d}-modes.json', result)
    design = preset(4)
    r = analyze(design, 'sparameters', {'start_ghz': 4.0, 'stop_ghz': 9.0, 'points': 201})
    text = r.pop('touchstone')
    (HERE / 'QPU-04-lumped-network.s2p').write_text(text, encoding='ascii')
    save('QPU-04-sparameters.json', r)
    save('QPU-04-yield.json', analyze(design, 'yield', {'count': 80, 'seed': 20261027}))
    save('QPU-04-design-checks.json', analyze(design, 'design_checks'))
    design['elements'][1].update(kind='SQUID', asymmetry=.15, flux_phi0=0)
    save('QPU-04-SQUID-flux.json', analyze(design, 'flux', {'points': 61}))
    candidate(preset(4), HERE / 'QPU-04-CONCEPT-ONLY.gds')
    print('Examples generated. All FEM/EDA/fabrication claims: NOT QUALIFIED.')


if __name__ == '__main__':
    main()
