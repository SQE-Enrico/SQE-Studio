import argparse
from pathlib import Path
from sqw import config, em, geometry

p = argparse.ArgumentParser()
p.add_argument('--mesh',action='store_true')
args = p.parse_args()
out = Path('build/modules/03/em')
cfg = config.load('configs/demo.toml')
geo = geometry.build(cfg)
em.export_configs(cfg,geo,out)
if args.mesh:
    print(em.mesh(cfg,geo,out))
print(f"Palace inputs: {out}. Review geometry and run solves explicitly.")
