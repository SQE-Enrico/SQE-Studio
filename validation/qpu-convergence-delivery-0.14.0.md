# SQE Studio v0.14.0 — Delivery and QA record

## Scope delivered

- New isolated Web scientific profiles: QPU C convergence (two electrostatic h-refinements), QPU Modes (two eigenmode refinements).
- Uses a fixed reference single-transmon geometry without reading user designs.
- Verifies Palace solver record hashes and original mesh/configuration/output checksums before numerical postprocessing.
- Compares raw Maxwell C and projected differential C with 1% default numerical criterion; values remain available when acceptance fails.
- Includes an index-only eigenfrequency comparison and explicit WARN/UNVERIFIED mode-identity status; no field-overlap matching.
- Requests one ParaView field frame at L0 and reports an inventory of fields and bounded numeric summaries from actual, hashed Palace CSV outputs. Raw 3D ParaView fields are not rendered in the Web UI.
- Web diagnostic ZIP includes stage status, bounded logs, numerical results and SHA-256 integrity manifest.
- Keeps the old Quick / Standard / Numerical / Full diagnostic profiles.

## Development QA results

Selected individual unittest suites passed, no reported test failures:

| Suite | Tests |
| --- | ---: |
| QPU convergence v0.14 | 10 |
| Numerical validation v0.13 | 8 |
| Benchmark profiles v0.12 | 10 |
| Scientific diagnostics v0.11 | 6 |
| Palace quality | 7 |
| Physical QPU | 10 |
| Parametric QPU | 15 |
| Quantum Lab | 11 |
| Studio diagnostics API | 4 |
| Studio bootstrap API | 4 |
| Studio main API | 15 |
| Diagnostic collector | 8 |
| Qualification | 6 |
| Physics | 12 |

**Total: 126 targeted tests passed.** Four extra optional reference tests were skipped. JavaScript syntax (`node --check`), Python compilation and Bash syntax checks passed.

The v0.14 scientific profile was run end-to-end through the report collector in a development environment without installed Palace/Gmsh. Geometry export succeeded; unavailable native/solver stages were correctly SKIP, never falsely PASS. Two real ZIP archives were opened and integrity-checked. Other tests use synthetic **mock fixtures only** to assess parsing/provenance and cannot constitute real FEM solver validation.

## Not yet tested

- Execution of the new two-level QPU FEM solves using Palace 0.16.0 on the target Windows 11 + Ubuntu/WSL2 workstation.
- Whether Palace on the target hardware accepts and writes the new optional one-frame ParaView fields for the fixed QPU geometry.
- Browser visual QA on the target Windows system.
- Full historical regression suite as one concurrent-worker batch: prior releases had intermittent process-lifecycle stalls, so only targeted suites are claimed above.

## First workstation acceptance

Run the Web **QPU C convergence** diagnostic only; download and review the ZIP, then share it for debugging. Do not run QPU Modes or Full concurrently. If QPU C completes, inspect both C matrices and relative changes; if convergence fails, preserve the numerical values and solver log. Mode comparisons remain optional and *informational* until actual mode identity tracking is implemented.
