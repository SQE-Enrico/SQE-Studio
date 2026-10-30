# Windows 11 Qualification: field findings and targeted stabilization

**Status: Experimental, NOT a Release Candidate.** Source: the fifth laptop
qualification report of 2026-10-30. Logs are user-supplied and do not establish
independent experimental, EM, or foundry validation.

## Evidence before patch

- Regression: 255 passed, 10 failed, 7 skipped (previous: 244/17/7).
- Comprehensive gate result: 4 PASS, 6 FAIL, 6 BLOCKED.
- Deep Chromium test genuinely runs, but two assertions fail: obsolete EM
  adapter-mode text and nonexistent Playwright `Locator.is_focused()` method.
- Quantum Metal 0.9.0 GDS renderer reads `options.path_filename` internally;
  the previous adapter set this to `None` even though an export target was passed.
- On Windows, native job progress updates can encounter WinError 5 while
  replacing a concurrently opened `PROGRESS.json`; failure to record a terminal
  scheduler state left jobs appearing queued/running.
- Installed wheel verification misread Windows-formatted Core Metadata line
  endings as a version mismatch. The wheel install itself completed.
- Julia executable was present, but its active project lacked the
  `JosephsonCircuits` Julia package. An executable alone is not a native RF port.
- scqubits 4.3.1 / installed SciPy generated `csc_array` inside scqubits
  `HilbertSpace.diag_hamiltonian`; the existing interaction-only sparse shim
  does not address this upstream internal conversion. **Still unqualified.**

## Implemented corrections

1. Give Quantum Metal's native renderer exactly the same controlled output
   `path_filename` as its `export_to_gds` argument. Keep native GDS byte and
   layer/cell inspection and fabrication HOLD.
2. Write native scheduler status through unique temp files, bounded retries
   only for Windows sharing violations, and atomic replacement. Never truncate
   the previous completed JSON. Terminal scheduling errors now transition to
   FAIL rather than leaving a run permanently active. Native scientific
   artifacts are not replaced by fixtures.
3. Read built-wheel Core Metadata through the standard email header parser,
   validating distribution name/version and exact installed `server.py` bytes.
4. Update browser tests to inspect the current truthful `native_conditional`
   EM adapter state and standard DOM focus semantics. No UI safety gate waived.
5. Detect the actual JosephsonCircuits Julia package for native tests.
   Missing packages produce explicit skipped/**BLOCKED** qualification,
   not false native PASS or unjustified scientific FAIL.

## Work still required for RC

- Rerun comprehensive qualification on Windows, including GDS structural
  readback and scheduler concurrency/atomic-progress tests.
- Resolve scqubits/SciPy internal sparse-array compatibility with an upstream-
  supported package combination or a reviewed, versioned local adapter.
  Verify eigenenergy spectra and matrix equivalence against a reference.
- Install and qualify JosephsonCircuits.jl for the selected Julia environment,
  then execute real RF/HB native tests. Do not install silently.
- SQDMetal/Gmsh/Palace eigenmode, kinetic sheet, EPR/quantization, optimizer
  feedback and native browser EDA design-loop acceptance remain incomplete.
- Independent measurements, PDK, DRC/LVS and foundry approval are absent.
  **Fabrication status HOLD.**

The product must remain a unified design/simulation/optimization EDA workflow;
qualification tooling is independent of native design tasks and must not
substitute synthetic solver output.
