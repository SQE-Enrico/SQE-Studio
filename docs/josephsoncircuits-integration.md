# JosephsonCircuits.jl — planned nonlinear circuit engine

SQE Studio uses the open-source Julia package **JosephsonCircuits.jl**, developed by Kevin O'Brien and collaborators, as its planned nonlinear Josephson circuit solver. The package is intended for multi-tone harmonic balance, driven nonlinear circuit response, and small-signal behavior around driven states. It is separate from the Palace FEM field solver.

## Currently available

- An explicit, provenance-preserving SI netlist export from representable JJ circuit branches in the physical QPU package.
- A dedicated optional Julia environment installer: `WINDOWS-JOSEPHSONCIRCUITS-SETUP.cmd`.
- Runtime/optional package readiness detection in Extended diagnostics.
- Conservative rejection of an unspecified effective SQUID instead of silently flattening it into a fictitious single junction.

## Not yet integrated

The Web worker cannot yet launch, validate and visualize a true JosephsonCircuits.jl harmonic-balance run. No automatic EM S-parameter/macromodel-to-Julia transfer has been qualified. Julia package versions and APIs must be pinned and regression tested before relying on them for device-design decisions.

## Milestone R12

Add tested Julia inputs and outputs, a nonlinear reference circuit with independently checked results, explicit pump and frequency grids, controlled numerical tolerances, versioned interchange, and Web plots of harmonics/gain/noise where physically justified. A successful import or exported netlist alone is not a solver qualification.

## Update 0.15.0

The optional `sqw ecosystem` adapter now supports a *real Julia process
invocation* for a bounded linear frequency sweep via `hblinsolve`, with raw
complex S output and explicit `--allow-solvers`; see
[the v0.15.0 workflow](ecosystem-workflow.md). This is separate from the Web
worker and **not** a nonlinear pumped HB solver or a qualified measurement.
The earlier export-only behavior remains the safe default.
