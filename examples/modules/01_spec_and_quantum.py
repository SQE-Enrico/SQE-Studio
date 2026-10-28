from pathlib import Path
from sqw import circuit, config, geometry
from sqw.io import write_json

cfg = config.load('configs/demo.toml')
geo = geometry.build(cfg)
out = Path('build/modules/01')
write_json(out/'electrical_target.json',circuit.synthesize(cfg))
params = circuit.parameters(cfg,circuit.surrogate(cfg,geo))
write_json(out/'forward_parameters.json',params)
print(f"Forward f01 = {params['f01_GHz']:.6f} GHz; target = {cfg['targets']['f01_GHz']:.6f} GHz")
