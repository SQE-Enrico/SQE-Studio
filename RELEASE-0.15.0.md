# SQE Studio 0.15.0 — Multi-Engine Quantum EDA Refactor

**Date:** 2026-10-28. **Delivery:** complete source release; no third-party
engines or proprietary ADS code bundled.

**New:** an independent, topology-neutral `sqw ecosystem` CLI can compose
QuantumLab, scqubits, Quantum Metal, SQDMetal's Palace adapter and
JosephsonCircuits.jl through a versioned workflow document. It includes
opt-in solver execution, safe input references, snapshots, SHA-256 integrity,
plugins, and three test/reference projects. The existing Studio Web UI and
Palace numerical audit are preserved.

**Start here:** [New multi-engine guide](docs/ecosystem-workflow.md),
[three example projects](examples/ecosystem/README.md),
[technical acceptance and limitations](validation/ecosystem-delivery-0.15.0.md).

**Validated:** locally executed 1Q three-stage reference; historical suite of
172 passed / 4 skipped with a completed run after initial adapter
implementation; focused 35-test Palace/QPU suite passed; final 11 new adapter
contract tests passed. External SQDMetal/scqubits/Julia/Gmsh/Palace binaries
were not installed or scientifically validated on the build host.

**No parity claim:** This release lays the architectural groundwork for a
broader open-source alternative to ADS QuantumPro. It does **not** provide
commercial-grade RF EM/CAD accuracy, multi-physics verification, comprehensive
DRC/LVS, pumped nonlinear gain/noise workflows or fabrication signoff.
