# Reproducible four-qubit and QPU examples

Generated with `python examples/quantumlab/run_examples.py` using `sqw.quantumlab` (NumPy + SciPy). There are electrical design JSON files for 1, 4 and 16 transmons, mode/weak-anharmonicity predictions, 4-QPU S-parameter curves and standard Touchstone v1 `.s2p`, a fixed-seed process spread example, electrical preflight, and a SQUID flux sweep.

**Every simulation here is a reduced-order model.** `QPU-04-CONCEPT-ONLY.gds` is an illustrative shape library and **must not** be used as a fabrication mask or presented as a layout whose EM topology is proven equal to the netlist. The `.s2p` is computed from lumped circuit equations, not from Maxwell full-wave EM. The exported numbers are demonstration reference outputs, not measured material or foundry data.

Use **Quantum Design Lab** in the Web UI to create new projects, edit/commit a netlist, run the persistent worker job and download versioned scientific result artifacts.
