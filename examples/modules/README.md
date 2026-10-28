# Small module examples

Run from the repository root after bootstrap. All examples are in English and save output under ignored `build/modules/`.

| Script | Dependencies | Result |
|---|---|---|
| `01_spec_and_quantum.py` | Core | Inverse targets, geometric extraction and forward spectrum |
| `02_layout.py` | Core; optional `--qpdk` | GDSII and geometry preview |
| `03_mesh_and_palace.py` | Core for export; Gmsh with `--mesh` | Palace configs and optional real mesh |
| `04_import_and_compare.py` | Core | Synthetic import and reference comparison |
| `05_measurements.py` | Core | S21, spectroscopy, Rabi, Ramsey, T1 |
| `06_energy_participation.py` | Core | EPR single-mode physical limit and two-mode Kerr example |
| `07_process_and_wafer.py` | Core | Rectangular die, overlap-junction candidate and hierarchical wafer GDS |

For example `python examples/modules/02_layout.py`, or `python examples/modules/03_mesh_and_palace.py --mesh` after installing Gmsh. The mesh example does not run Palace silently; use the explicit solve stages in the FEM guide.
