"""Generate explicit process candidates from the same scientific device model."""
import argparse
from pathlib import Path
from sqw import workflow
from sqw.studio.process import document, resolve, export

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, default=Path('build/modules/07'))
args = parser.parse_args()

doc = document()
doc['process'].update(chip_width_um=7000., chip_height_um=6500., text='SQE EXAMPLE')
cfg, _ = resolve(doc)
out = args.out
workflow.stage('layout', cfg, out / 'run')
workflow.stage('quantize', cfg, out / 'run')
review = export(doc, out / 'run', out / 'fabrication')
print(f"{review['die_count']} dies; {review['status']}")
print(out / 'fabrication/wafer_candidate.gds')
