# SQE Studio — 2026-10-30 Windows field-test fixes

Release classification: **EXPERIMENTAL — NOT RELEASE CANDIDATE**.

This revision responds to the Windows 11 fifth qualification report. It contains
source/GUI/launcher from the previous complete RC stabilization archive plus
bounded corrections. It does not change frozen foundation contracts, solver
physics, numerical coefficients, or PDK/foundry gates.

## Field evidence before these corrections

- Previous report: regression 244 passed, 17 failed, 7 skipped.
- Fifth report: regression 255 passed, 10 failed, 7 skipped; gate outcomes
  4 PASS, 6 FAIL, 6 BLOCKED.
- Native dependencies: Quantum Metal 0.9.0, scqubits 4.3.1 and Gmsh 4.15.2
  detected, as well as Playwright 1.64.1 and Julia executable; SQDMetal/Palace
  and the JosephsonCircuits Julia package not detected.

## Verified fixes in this source

- Native Quantum Metal GDS renderer receives a valid controlled output filename
  as both `path_filename` and the export argument. Native GDS inspection and
  fabrication HOLD remain intact.
- Windows scheduler JSON writing uses bounded sharing-lock retries with atomic
  replacement and unique temporary names; persistent failure explicitly sets
  terminal FAIL rather than leaving a job queued/running indefinitely.
- Wheel provenance parses package METADATA across LF/CRLF; still verifies
  exact wheel bytes in `server.py` after isolated installation.
- Real-browser regression assertions use current adapter state and supported
  Playwright DOM focus semantics. Security and review gates remain unchanged.
- Julia native tests require the actual `JosephsonCircuits.jl` package.
  Missing package means native test SKIPPED/BLOCKED, not PASS.

## Host verification

- Full pytest suite: **263 passed, 13 skipped, 0 failed** on Linux/Python 3.13.
  Native test suites not available on this host remain skipped.
- Two independent Python wheels with fixed `SOURCE_DATE_EPOCH` are byte-identical.
- Offline isolated wheel installation and precise wheel/source provenance: PASS.
- Installed wheel real HTTP smoke: PASS (authentication, CSRF, CPW project,
  revision, UI resources, logout).
- Source inventory including frozen contracts verified by
  `tools/verify_release_source.py`.
- Real Chromium deep browser acceptance and native solver tests on Windows:
  NOT EXECUTED here. These must be established by the next laptop report.

## Unresolved blockers for a real integrated EDA release candidate

1. scqubits 4.3.1 and the installed SciPy produce a `csc_array` from inside
   HilbertSpace's own bare-hamiltonian path, not only in coupling operator
   callables. Existing adapter compatibility is insufficient. Requires a
   scientifically reviewed version matrix or local adapter approach and native
   spectrum comparison; no numerical alteration or global upstream monkeypatch
   was introduced in this update.
2. JosephsonCircuits.jl package must be explicitly installed/validated in the
   selected Julia project before native RF/HB smoke can pass.
3. SQDMetal/Palace reviewed EM, kinetic sheet, EPR quantum extraction and
   multi-engine objective-driven design iteration remain unqualified.
4. Windows native GDS, browser and job concurrency must be rerun, and physical
   independent benchmarks plus PDK/DRC/LVS and foundry approval remain absent.

**Never substitute fixture tests for native EM/RF/quantum evidence. Fabrication HOLD.**
