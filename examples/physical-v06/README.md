# Unified Physical QPU demonstration (v0.6)

`one-transmon/` and `four-transmon/` were generated with:

```bash
python scripts/export_physical_qpu.py --size 1 --out examples/physical-v06/one-transmon
python scripts/export_physical_qpu.py --size 4 --out examples/physical-v06/four-transmon
```

They include **actual exported files** from the parameter source: geometry in µm,
GDSII/HOLD annotated layout, nominal circuit, QGeometry manifest, Palace JSON,
and a checksum contract. They intentionally do **not** include a `.msh`, Palace CSV
or fabricated measurement. Generating meshes/solutions is the function of the
native FEM workflow after Gmsh+Palace setup.

Important: 4-cell sample has **no intentional interqubit coupling**. Every C/L
in the nominal circuit is user-declared starting data, not a Palace extraction.
These files are only starting examples and must not be used as fabrication masks.
