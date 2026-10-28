# Three end-to-end examples

All commands are run from the repository root after bootstrap. Change output directory names when repeating a complete run.

## 1. Fully executable analytical demonstration

```bash
sqw run --config configs/demo.toml --out build/demo
```

Inspect `report.html`, `parameters.json`, `layout/device.gds`, `experiment/measurements.png` and the CSV files. The checked-in `examples/results/demo/` contains a completed run for inspection before installation.

The sequence is inverse electrical specification → layout → Palace input export → analytical surrogate extraction → quantum parameters → measurement traces → report. No FEM mesh or solve is claimed in this route. The positive-metal mask and the circuit calculations are real generated artifacts; their physical accuracy depends on the stated model.

Try copying the TOML file, increasing `layout.pad_width_um` by 20, then running to a new output directory. The surrogate produces a changed differential capacitance and qubit frequency, while the GDS and geometry hash change coherently. Compare `specification.json` (design goal) with `parameters.json` (forward prediction). Do not replace a forward result by the target when they disagree.

## 2. Imported data and benchmark loop

```bash
sqw run --mode imported --extraction examples/data/synthetic_extraction.json \
  --out build/imported
sqw compare --parameters build/imported/parameters.json \
  --reference examples/data/synthetic_reference.csv --out build/comparison.json
```

The imported matrix is synthetic and belongs to the unchanged demo geometry. Its provenance remains `synthetic_fixture`; it is never renamed as a real Palace solve. The reference values provide a software demonstration of residuals and uncertainty handling. `within_3sigma` refers only to this illustrative comparison.

Real measured reference-chip data replaces this fixture only after the lab supplies geometry, process and independent measurements. See [benchmarking](benchmark.md).

## 3. Full open-source FEM chain

Follow [the staged FEM tutorial](fem.md) to identify the readout mode before using `sqw run --mode fem`. That route adds a Gmsh mesh and real Palace electrostatic/eigenmode solves before the same downstream parameter and experiment stages. If a solve fails, the run remains failed and does not produce a surrogate replacement.

## Tolerances

```bash
sqw tolerance --config configs/demo.toml --samples 50 --seed 123 --out build/tolerance
```

The demonstration samples independent Gaussian variations of EJ (5%), pad width (1 µm) and qubit coupler gap (0.3 µm). Every sample rebuilds geometry and recalculates the surrogate circuit. The CSV contains f01, alpha, g and chi. These distributions are teaching assumptions; they are not extracted process yield. Replace their values and correlations using metrology.

## Python module examples

Run `python examples/modules/01_spec_and_quantum.py` and the other scripts described in [their index](../examples/modules/README.md). Outputs go to ignored `build/modules/` directories. The mesh example requires Gmsh; the other core examples run with the scientific environment alone.

`examples/workflow.ipynb` provides the same core science as a notebook. Optionally install `python -m pip install -e '.[notebooks]'`, launch `jupyter lab` from the repository root, and select the `.venv` Python kernel. Notebook packages are an optional candidate environment; the delivered numerical cells were executed as Python during validation.
