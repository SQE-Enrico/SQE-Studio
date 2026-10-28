# Training and validation pathway

This optional path helps a new researcher learn the platform through concrete research and validation milestones.

1. **Electrical model:** reproduce the exact transmon spectrum, understand E/h versus angular frequency, and check charge-basis convergence and anharmonicity.
2. **Shared geometry:** edit pad/CPW/readout inputs, compare native/QPDK GDS and inspect conductor ownership, die boundaries and layer polarity.
3. **Process definition:** enter actual die/wafer rules, junction dimensions and accessory geometry. Identify which inputs are calibrated, assumed or unqualified.
4. **Numerical reference problems:** run the independent capacitor calculation, then qualify native Palace against capacitor and cavity limits.
5. **Chip meshing and solves:** verify boundaries/ports, converge the intended modes, identify the readout field and preserve raw-to-normalized provenance.
6. **Quantum and experimental interpretation:** compare dressed spectra, dispersive conventions and expected readout/time-domain traces. Separate coherence assumptions from geometry-derived quantities.
7. **Reference-device validation:** reconstruct an independently measured device, retain uncertainty and distinguish calibration from held-out validation.
8. **Reviewable handoff:** consolidate software/scientific checkpoints, integrate the laboratory process cell, inspect final GDS and complete laboratory DRC/job-deck review.

The browser guides ordinary work; the source, CLI, Python modules and macro mechanism remain available for advanced research. Use small reviewable changes, record discrepancies and preserve failed numerical experiments as useful evidence. Coherence prediction, multi-qubit topology providers, optimization and cluster integration can be added as independent research modules with explicit contracts and validation.
