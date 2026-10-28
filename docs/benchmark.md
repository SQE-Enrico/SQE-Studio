# Validate against the laboratory reference chip

Measured-device qualification starts from a reference chip with known geometry, fabrication and characterization. No such laboratory dataset is distributed here. The repository supplies a synthetic example and an explicit import contract so that a real reference can be incorporated with its provenance.

## Information to obtain

Record the reference die dimensions and GDS layer map; substrate thickness and material assumptions; Al deposition and junction process; intended and measured junction resistance/Ic; resonator geometry; sample holder, bond wires and grounding; cryostat/line calibration; independent f01, f12, readout frequency, linewidth, coupling, chi and temperature estimates. Include measurement date, analysis method, uncertainty, raw data reference and any excluded data.

Reconstruct the device using `geometry.py` or a reviewed new geometry provider that emits the same JSON contract. The current router is a single-device teaching example; it is not a universal GDS-to-simulation importer. Arbitrary laboratory layouts require conductor identification and a suitable polygon/mesh adapter.

## Comparison CSV

Columns are `parameter,value,unit,sigma,kind`. Parameter names match scalar keys in `parameters.json`, with units matching their suffix, for example:

```csv
parameter,value,unit,sigma,kind
f01_GHz,5.012,GHz,0.005,measured
anharmonicity_MHz,-252.0,MHz,3.0,measured
readout_bare_GHz,7.18,GHz,0.01,measured
```

These numbers illustrate formatting only. A measured low-power cavity resonance is typically a **dressed** resonance; choose `readout_g_GHz` when comparing that quantity. A reported readout state separation corresponds to `2*chi_exact_MHz`; convert it deliberately or extend the comparison schema. Never compare a dressed quantity against a bare one silently.

Run `sqw compare --parameters RUN/parameters.json --reference data/private/reference.csv --out RUN/comparison.json`. The comparison records residuals in measurement-sigma units and the input file hash. It does not include model uncertainty automatically. Agreement within three measurement sigmas is illustrative, not an acceptance certificate. Use an uncertainty budget that includes fabrication spread and modeling error.

## Keep calibration distinct from validation

Use a subset of measured devices to calibrate epsilon_eff, sheet inductance, interface assumptions, Jc and geometric surrogate coefficients. Freeze them, then compare against independent devices or withheld parameters. Fitting EJ from the same measured f01 later used for validation is not an independent frequency prediction.

Mesh convergence, solver regression against a known capacitor/cavity, energy consistency, quantum basis convergence and measured-device agreement are separate checks. Preserve failures and systematic offsets; they are useful research evidence. Add a versioned qualification note with the exact solver/build/lock, run hashes, approved process layer map and the reviewer.
