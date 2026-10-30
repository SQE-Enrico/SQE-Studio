# RC stabilization update — Windows 11 field qualification

**Status: experimental, NOT RELEASE CANDIDATE.** This update responds to the
October 30, 2026 laptop qualification evidence. Do not present a passed source
suite or browser smoke as evidence of validated cross-engine physics.

## What changed

- **Quantum Metal QNet/QGeometry:** the native route adapter now verifies each
  terminal pin's `net_id` matches its corresponding route `start` or `end` pin.
  Quantum Metal assigns separate QNet IDs to these endpoint pairs; demanding
  the *same* ID at both terminals incorrectly rejects a valid route. Any absent
  or mismatched endpoint still blocks the QDesign and GDS. This does **not**
  establish physical GDS connectivity, DRC or fabrication suitability.
- **scqubits composite:** a narrowly scoped callable wrapper converts SciPy
  sparse `sparray` output to `csc_matrix` with identical values and the same
  subsystem binding. The parameter mapping, coupling strength, eigenvalue
  model, and energy units are unchanged. Native scqubits 4.3.x compatibility
  must be rechecked on the laptop, including convergence and energy differences.
- **Windows UTF-8:** static GUI tests read explicitly as UTF-8. Palace kinetic
  deck writes now use the exact bytes whose SHA-256 was recorded; no newline
  translation or weakened artifact checks.
- **Browser revision acceptance:** the test waits for the asynchronous saved
  revision, and checks the displayed revision against the authenticated
  project's server-reported head rather than merely observing a pre-existing
  `Specifications` screen.
- **Native job lifecycle:** the scheduler releases the exclusive laptop slot
  before exposing a terminal state, preventing a retry from racing cleanup.
  Worker failures remain fail-closed; validation and engine output are not forged.
- **Packaging:** the qualification forces installation of the freshly built
  wheel into an isolated virtual environment, verifies its installed location
  and exact `server.py` hash, then executes a real HTTP/authentication/UI smoke.
- **Diagnostics:** failures in the temporary test workspace now append bounded,
  sanitized native worker `FAILURE.json`, `LIFECYCLE_FAILURE.json`,
  `VALIDATION_FAILURE.json`, `engine.log`, and Julia stdout/stderr to the report.
  No personal projects or non-test home folders are inspected.
- **Native-presence test:** no longer assumes scqubits is absent; it accepts a
  *completed* run only with a verified, revision-bound native manifest.

## Laptop verification — no terminal required

1. Back up the current `SQE-Studio` folder; do **not** delete the existing
   Python 3.11 scientific environment, Chromium or solver installations.
2. Extract the full ZIP into a **new folder**; start with
   **Launch SQE Studio.pyw**. If the environment is not automatically selected,
   use **Reconnect existing scientific environment** in the launcher.
3. Choose **Qualify this laptop → Comprehensive** and save the generated ZIP.
4. Inspect the share ZIP for paths or private information, then provide it to
   developers. The report contains evidence SHA-256 hashes.

**Do not rerun the installer unless the next report specifically identifies
missing tools.** Playwright/Chromium already passed on the reported laptop.

## Release acceptance still missing

- Windows-native rerun of the full integrated regression, full browser tests,
  the new QM 0.9.0 net checks, real scqubits composite spectrum, isolated wheel
  check and Julia native error diagnostics.
- Resolve JosephsonCircuits.jl failures using the *recorded native stderr*,
  not guessed dependency changes. SQDMetal/Palace remain unavailable; their
  full reviewed eigenmode mesh/deck/solve and convergence have not been executed.
- Qualify EPR, kinetic inductance, RF cross-engine maps and objective-driven
  geometry optimization with real native outputs and independent references.
- Independent PDK/DRC/LVS and foundry signoff: **HOLD**.

## Primary upstream references

- Quantum Metal design nets and route connections:
  https://qiskit-community.github.io/qiskit-metal/tut/quick-topics/Managing-pins.html
- scqubits 4.3.1 HilbertSpace interaction parsing:
  https://scqubits.readthedocs.io/en/v4.3.1/_modules/scqubits/core/hilbert_space.html
- scqubits operator conversion and sparse matrix support:
  https://scqubits.readthedocs.io/en/latest/_modules/scqubits/utils/spectrum_utils.html
