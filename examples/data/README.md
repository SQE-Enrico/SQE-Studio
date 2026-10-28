# Public synthetic fixtures

`synthetic_extraction.json` is generated from the demo's uncalibrated analytical surrogate, with the exact demo geometry hash. It is not a real FEM extraction. `synthetic_reference.csv` repeats its predicted scalar values to demonstrate the comparison interface. Agreement is therefore intentional software closure, not independent scientific validation.

`palace_contract/` contains formatted synthetic examples of the Palace capacitance/eigenmode CSV contract. They exercise parsing and units. They have no mesh, solver log or successful native-solve record, so they cannot pass the production FEM import route as actual solver evidence.

Put real restricted measurements in ignored `data/private/`; preserve raw-data provenance and use independently measured uncertainties as described in `docs/benchmark.md`.
