from pathlib import Path
from sqw import circuit, config, geometry, workflow
from sqw.io import read_json, write_json

out = Path('build/modules/04')
cfg = config.load('configs/demo.toml')
data = read_json('examples/data/synthetic_extraction.json')
assert data['geometry_sha256'] == geometry.build(cfg)['geometry_sha256']
params = circuit.parameters(cfg,data)
write_json(out/'parameters.json',params)
workflow.compare(out/'parameters.json','examples/data/synthetic_reference.csv',out/'comparison.json')
print('Synthetic comparison only:',out/'comparison.json')
