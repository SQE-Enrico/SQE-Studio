from pathlib import Path
from sqw import circuit, config, experiment, geometry

cfg = config.load('configs/demo.toml')
geo = geometry.build(cfg)
params = circuit.parameters(cfg,circuit.surrogate(cfg,geo))
out = Path('build/modules/05')
print(experiment.simulate(cfg,params,out))
print(out/'measurements.png')
