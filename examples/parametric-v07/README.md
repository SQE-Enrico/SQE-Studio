# Parameter-driven QPU examples (SQE 0.7)

- `dolan-4q.json`: four explicitly placed floating transmons with capacitive nearest-neighbor links; GDS process markers for Dolan.
- `manhattan-2q.json`: two qubits, four-finger interdigitated coupler and Manhattan process-intent markers.
- `planar-9q.json`: nine qubits, six explicit nearest-neighbor coupling edges and a manually parametrized readout line.
- `*-export/`: pre-generated packages. All files carry **HOLD** status; they are **not** Palace solutions or fabrication-ready masks.

Generate from a bare Python source checkout with:

```
PYTHONPATH=src python scripts/export_physical_qpu.py --document examples/parametric-v07/manhattan-2q.json --out exports/manhattan2q
```

Modify the JSON freely, including `materials`, `stack`, junction process and `routes`. Change the chip dimensions or the geometry and use the generation error messages to locate DRC violations. Materials and fabrication processes are examples, not certified foundry rules.

`custom-2q.json`: template qubit definito nel progetto (`libraries.qubit_shapes`) e `custom_rects` coupler completamente parametrico; entrambi sono validati da DRC.
