# Remaining competitive gaps

The working isolated-transmon chain is a useful foundation. The following
capabilities remain unresolved, ordered by engineering impact.

1. **Coupled transmon/readout:** integrate a saved native eigenmode/EPR case,
   expose supported readback and exercise the actual UI. Do not promote mode
   indices or raw participation tables into independently identified modes.
2. **Numerical confidence:** complete mesh, domain and material sensitivity for
   the same chip, with predeclared tolerances and uncertainty. Preserve quantum
   basis checks as a separate numerical test.
3. **Complete engineering editing:** move beyond symbolic canvases where needed:
   direct schematic wiring, layout manipulation, measurement, layers, stable
   nets/junctions and reusable hierarchy.
4. **Fresh native iteration and persistence:** GUI geometry modification,
   affected-study rerun, source-bound comparison, export/reopen and restart.
5. **Full-wave EM and fields:** independently referenced CPW/driven cases,
   physical mode tracking, all relevant field exports and a practical viewer.
6. **Coupled qubits and quantization:** explicit multi-island native identities,
   validated two-transmon reduction, EPR/black-box transfer and coupled spectra.
7. **Circuit co-simulation and nonlinear response:** supported equivalent
   networks, schematic-to-Julia workflow, real operating points and harmonic
   convergence. Broader envelope/transient bundle parity is not implemented.
8. **Superconducting materials:** validated film/sheet models, kinetic
   inductance and loss handling with provenance and matched PEC controls.
9. **Useful optimization:** resource-configured native exploration and
   mode-consistent physical objectives, without automatic scoring of ambiguous
   eigenmode indices.
10. **Interoperability and automation:** GDS import/edit round trip, fabrication
    rule checks, public reproducible API examples and engineering report export.
11. **Complete product test inventory:** execute outstanding controls, error,
    recovery, cancellation, responsive and restart scenarios. Explicitly track
    native tools and stages that have not been exercised.
12. **Extended targets:** OASIS, distributed/HPC execution, packaging/cavity
    models, larger assemblies, amplifier scale and yield analysis.

See the [capability matrix](QUANTUMPRO_COMPETITOR_MATRIX.md) for implementation
and confidence status, and the [execution plan](QUANTUMPRO_DEVELOPMENT_PLAN.md)
for acceptance evidence. No complete parity or physical qualification is claimed.
