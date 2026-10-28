import argparse
from pathlib import Path
from sqw import cad, config, geometry

p = argparse.ArgumentParser()
p.add_argument('--qpdk',action='store_true')
args = p.parse_args()
out = Path('build/modules/02')
out.mkdir(parents=True,exist_ok=True)
geo = geometry.build(config.load('configs/demo.toml'))
geometry.save(geo,out/'geometry.json')
cad.write_gds(geo,out/'device.gds','qpdk' if args.qpdk else 'native')
geometry.preview(geo,out/'layout.png')
print(cad.inspect_gds(out/'device.gds'))
