# Open Quantum Design Lab 0.4.0 — acceptance and caveats

Test date: 2026-10-27. Test host: Linux container, Python 3.13. Test program is published with the code.

## Executed

- `PYTHONPATH=src python -m unittest discover -s tests -q`: **69 tests, OK, 4 skipped**. This includes 11 new Quantum Lab physics/API/worker contract tests.
- `PYTHONPATH=src python -m unittest discover -s tests -p test_quantumlab.py -q`: **11 tests, OK**.
- `node --check src/sqw/studio/static/quantumlab.js`: passed JavaScript syntax check.
- `PYTHONPATH=src python -m sqw doctor`: passed the Python environment diagnostic (native optional EM components separately reported as unavailable).
- An actual `Scheduler.tick` spawned `python -m sqw.studio.runner` as a child and completed `lab:modes` for a 4-qubit design: **succeeded**, four qubit assignments, persisted `lab/result.json`.
- `examples/quantumlab/run_examples.py` regenerated JSON, Touchstone v1 and a concept-only GDSII; tests inspect GDSII layers.

## Not executed or not qualified

- The `.cmd` / `.ps1` startup was **not run on Windows** in this environment. Native Windows acceptance, Authenticode installation behavior and Windows cancellation must be performed on a Windows 10/11 x64 system. Do not infer otherwise from the cross-platform tests.
- Chromium browser access to a local HTTP endpoint was restricted by this test environment. The API was exercised through direct authenticated WSGI requests and JavaScript syntax was checked; a full browser-rendered, click-through test is **pending**.
- No Palace, MPI, multi-qubit full-wave Maxwell FEM, MoM, FDTD, field EPR, black-box extraction, fluxonium/SNAIL multi-junction quantization, or production manufacturing checks were executed.
- No claim of numeric equivalence to Keysight ADS QuantumPro, license equivalence or sign-off for a real QPU.

## Essential Windows acceptance runbook

1. In a clean Windows 11 x64 workstation or VM, extract the ZIP and double-click `WINDOWS-FIRST-START.cmd` with internet available. Record the Python and Windows versions, hashes and pip resolved package set.
2. Confirm Python installer signature is accepted (or use already-installed Python 3.12), bootstrap completes, `sqw doctor` and **11 Quantum Lab tests** pass. Confirm loopback URL appears and login administrator setup succeeds.
3. Create a project, load the 4-transmon preset, save design, run `modes`, `sparameters`, `flux` (after selecting SQUID), `dynamics`, `yield`, `design_checks`, `optimize`, `loss_budget` and `duffing`.
4. Inspect numerical file hashes, download `network.s2p`, open it with an independent Touchstone viewer, export concept-only GDSII and inspect in KLayout; these are not full-wave EM or tape-out files.
5. Stop and restart the Web application; confirm the same SQLite project, revision and artifacts are preserved. Cancel a longer running job; check no worker process survives inadvertently.
6. Test a no-Python initial state, an already-installed Python state, a blocked network state and a mismatched Python interpreter; automatic success must never be asserted when dependencies fail.
7. Optional: provision WSL2 and a independently validated Linux Palace environment; run the *original* single-device FEM integration. Do not mislabel this as Quantum Lab full-array FEM support.

Details and honest coverage map: `docs/quantumlab.md` and `docs/windows.md`.
