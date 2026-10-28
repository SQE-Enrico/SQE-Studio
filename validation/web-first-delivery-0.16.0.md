# SQE Studio v0.16.0 — delivery validation and known limitations

**Build date:** 2026-10-28. **Language:** English for all new code, user-facing
pages, reports and documentation. Historical scientific model symbols and
units retain their usual mathematical notation.

## Checks performed in the release build environment

- Full Python unittest discovery: **187 tests run**, **4 skipped**, **0 failures**.
- New browser API tests exercise login/CSRF/admin/localhost permissions,
  multi-step run execution, failed execution, project ZIP import, malicious ZIP
  rejection, per-job archives, diagnostic fallback ZIPs, and checksum manifests.
- JavaScript syntax: new experiment page, modified diagnostic page, and
  modified Studio workspace passed `node --check`.
- The bundled native-1q example completes modes, RF S-parameters, and
  JosephsonCircuits netlist export in the local Web runner. The output SHA-256
  manifest was independently checked by the regression tests.
- The v0.14 Palace/QPU convergence and geometry-audit fixtures and tests remain
  in the release, together with the three v0.15 example workflows.

## Not validated in this build environment

- Windows 11 double-click first launch and graphical browser interaction were
  not executed on a clean target Windows workstation.
- Real external Quantum Metal/SQDMetal/Palace/Julia FEM or nonlinear solves
  were not numerically benchmarked here; absent optional packages are reported
  as unavailable, not silently installed.
- SQDMetal to SQE capacitance/eigenmode node/port extraction, field-overlap
  tracking, device loss, full nonlinear harmonic balance, industrial DRC/LVS
  and foundry signoff are not implemented or validated.
- Support ZIP integrity does not establish solver convergence or ADS
  QuantumPro equivalence.

## Operator instructions

Start the application by double-clicking `WINDOWS-FIRST-START.cmd`. From the
browser select Research Experiments, choose the native one-qubit project, run
it, inspect the results, and download its support ZIP. For the complete
regression suite, use the **Run all regression test files (long-running)**
checkbox under Tests & Diagnostics. For ordinary Studio job failures, open the
job's detail and select **Download job ZIP for troubleshooting**.

Reports are local until manually downloaded. ZIPs may contain research designs
and raw solver logs; review them before sharing. No project data is bundled
with the source release.
