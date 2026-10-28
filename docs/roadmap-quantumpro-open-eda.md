# Open Quantum EDA roadmap — incremental and verifiable

The goal is a Web-first, open-source design and simulation experience approaching the practical superconducting-QPU design workflows of Keysight ADS QuantumPro. This is **not** a claim of numerical parity or access to proprietary implementations. Every milestone requires reproducible tests, explicit scientific fidelity labels, and documented blockers.

| Stage | Objective | Acceptance gate |
| --- | --- | --- |
| R1 · 0.8 | Palace convergence contracts; JosephsonCircuits.jl netlist export | Fixed scientific contracts, provenance, honest solver limitations |
| R1.5 · 0.9 | Windows software/hardware diagnostic capture | Portable diagnostic ZIP and privacy review |
| **R1.6 · 0.10** | **Clean English Web control center** | Browser diagnosis, admin ACL/CSRF, persistent results, zero secret distribution, clean startup |
| R2 | Real Palace on Windows/WSL2 | Reference electrostatic solve, raw output, independent accuracy comparison |
| R3 | FEM quality and RF ports | Mesh studies, mode tracking, port calibration, bounded numeric error reports |
| R4 | Physical 3D stack-up | Multiple real metal layers, interfaces, kinetic inductance, boundary models |
| R5 | Interactive CAD Web editor | Placement, selection, editing, schematic-to-layout consistency |
| R6 | Constraint-driven CPW routing | Obstacles, bends, meanders, ground clearance, DRC and LVS checks |
| R7 | Network extraction | Consistent C/L matrices and connectivity with uncertainty estimates |
| R8 | Hamiltonian extraction | EPR and black-box/multi-JJ quantization with verified mode mapping |
| R9 | Loss and coupling | g/χ/ZZ, Purcell and participation budgets using authentic FEM fields |
| R10 | Physical tunable couplers | Loop geometries, flux bias and JJ networks, validated bias sweeps |
| R11 | Process-aware junctions | Dolan/Manhattan masks, shadow evaporation models and process calibration |
| R12 | JosephsonCircuits.jl execution | Versioned Julia API, harmonic-balance benchmark, nonlinear EM/circuit co-simulation |
| R13 | Quantum time dynamics | Pulses, multilevel Hamiltonians, leakage, gates and control cross-talk |
| R14 | Packaging and assembly | Bumps, via, cavity/package fields and loss pathways |
| R15 | Multi-user server/HPC | Worker isolation, distributed dispatch, reproducible project migration |

Each stage should be achievable in small feature releases. Keep parametric user-defined geometries rather than hardcoding one processor family. A local single-machine installation and a future server must share the same scientific input/output model.

**Immediate next test:** from the browser, run standard and extended workstation diagnostics; then qualify real Palace on the installed Ubuntu/WSL2 workstation. Only after the solver output is verifiable should automated C/L, EPR or quantum parameter extraction be called accurate.
