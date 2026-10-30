# Windows workstation setup — user-approved Python 3.11 sidecars

**Status:** experimental toolchain preparation, **not scientific qualification** and **not an automatic native Palace installer**. The EDA design and simulation interfaces are unchanged. The installer is a separate local desktop-administrative action, never an authenticated HTTP API, job payload or design action.

## Why this exists

The first user qualification report, dated October 30, 2026, recorded **Windows 11, Python 3.15.1**, 2 PASS, 1 FAIL and 13 BLOCKED. `source_wheel_build` failed because `setuptools.build_meta` was missing. The active Python also lacked `pytest`, `playwright`, Quantum Metal, SQDMetal, Gmsh, scqubits and Palace. Julia was present, but no native JosephsonCircuits computation was demonstrated. That report did **not** show that an attempted automatic solver installation had failed: the original qualifier never installed solver dependencies.

Upstream Quantum Metal documents Python 3.10–3.14 for its modern distribution. SQDMetal's current source specifies **Python >=3.11,<3.12**, which is why SQE Studio chooses 64-bit **Python 3.11** for the experimental Windows sidecar instead of modifying the user's 3.15 Python. The new version of Quantum Metal is distributed as `quantum-metal` (while the SQE adapter still imports `qiskit_metal`). The SQDMetal source must be compatibility-reviewed against SQE's adapter and Quantum Metal before running EM jobs.

## No-terminal setup (Windows 11)

1. Download and extract the **new SQE Studio package**. Do **not** overwrite an old source folder or remove user-data directories. Double-click `Launch SQE Studio.pyw` (the launcher can initially be associated with Python 3.15).
2. Click **Prepare scientific environment**. If it says that **Python 3.11 x64** is missing, use the **Get Python 3.11** button to visit the official Python website, install an official 64-bit Python 3.11 interpreter with the Windows Python launcher, close SQE Studio and reopen it. The tool never installs an interpreter or modifies global PATH.
3. Leave **Build + pytest** selected. You may explicitly select **scqubits**, **Gmsh**, **Quantum Metal** and/or **Playwright + Chromium**. Installing packages **requires an Internet connection, explicit confirmation, and trust in public package indexes and downloaded browser binaries**. The setup only writes a user-local environment under `%LOCALAPPDATA%/SQE-Studio/environments/`; it does not install as Administrator, import designs or change the system Python.
4. Close SQE Studio and double-click `Launch SQE Studio.pyw` again. When the managed environment's core bootstrap has succeeded, the launcher switches to its Python 3.11 interpreter. Choose **Qualify this laptop → Comprehensive** and save a **new** qualification ZIP to share.
5. If an optional installation fails, check the setup dialog message; rerun with that single package checked. Failure to install a package is not a failure of a solver's numerical output. A module import or distribution install also never equals successful native computation.

## Scientific toolchain boundaries

| Component | Setup policy | Native qualification required |
|---|---|---|
| Python build backend / pytest | User-approved pip packages in Python 3.11 | Installed package/HTTP and software regression tests |
| Playwright + Chromium | Optional explicit download; policies may block Chromium | Real browser/HTTP acceptance |
| scqubits | Optional pinned candidate | Eigenvalue/basis/convergence, controlled independent circuit parameters |
| Quantum Metal | Optional pinned candidate | Native QDesign and actual GDS generation; validate API against current release |
| Gmsh | Optional pinned candidate | Reviewed surface tags/mesh with material/port/boundary mapping |
| SQDMetal | Explicitly approved, official Git-commit ZIP download with SHA-256 archive pin; advanced local source alternative | Verify commit/dependencies, actual native API, mesh/deck and Palace solve |
| Palace | **No native Windows installer** | Use a manually qualified WSL2/Linux binary and explicit cross-OS path/mount mapping; converge mesh |
| JosephsonCircuits.jl | **No automatic Julia environment rewrite** | Use an isolated, reviewed Julia Project/Manifest and native RF tests |

The optional Python pins are reviewed candidates, not a hash-locked, reproducible full scientific stack. The project continues to block EM→Hamiltonian/EPR extraction, kinetic-sheet mapping and geometry optimization until the actual interfaces are validated; a successful installation cannot change these scientific gates.

## Developer security and release requirements

- Do not call pip, curl, winget, Julia package installation, git clone or powershell from project files, worker jobs or HTTP endpoints. Provisioning must be a **local administrative action with explicit user consent**.
- Never weaken authentication, revision, PDK/DRC/LVS, scientific units, modes, physical surface/port/mesh review or artifact hashes to get a green report.
- Never silently fall back from an unavailable native solver to a fixture or synthetic result. Distinguish *installed*, *importable*, *native executed* and *scientifically validated* in both GUI and evidence.
- Maintain user-local toolchain separation; never rewrite Python 3.15's packages, the source inventory, any user's existing project or the original foundation lock.
- New RC candidates require a fresh Windows qualification ZIP, with all software/browser gates passing and honest blocked statuses for unfinished physical interfaces, then separately reviewed native benchmark convergence and measurements.

## Upstream references

- Quantum Metal installation: https://qiskit-community.github.io/qiskit-metal/installation.html
- SQDMetal source requirements and installation: https://github.com/sqdlab/SQDMetal/blob/main/pyproject.toml and https://github.com/sqdlab/SQDMetal
- scqubits packaging: https://pypi.org/project/scqubits/
- Palace Windows FAQ: https://awslabs.github.io/palace/stable/faq/
- Playwright browser installation: https://playwright.dev/python/docs/browsers
- JosephsonCircuits.jl: https://josephsoncircuits.org/stable/

## Desktop launcher failure after preparing the scientific environment

**If double-clicking `Launch SQE Studio.pyw` does nothing:** Windows hides the
traceback of `.pyw` programs. Use the updated launcher in this release; it
**supervises** the Python 3.11 child and, if that child exits unsuccessfully,
shows an error and tries the original interpreter in limited mode. It never
uninstalls dependencies or changes user designs. If even the corrected launcher
fails to appear, double-click **`Troubleshoot SQE Studio.cmd`** from the same
folder; its console remains open with startup diagnostics. The launcher also
writes `%LOCALAPPDATA%\\SQE-Studio\\launcher-errors.log` (review before sharing).

**Emergency recovery with the previous launcher:** In Windows Explorer, open
`%LOCALAPPDATA%\\SQE-Studio\\environments`, find the environment corresponding
to the SQE extraction you are launching, and rename `ready.json` to
`ready.disabled.json`. Do not delete the `venv` folder. This disables automatic
runtime switching for that folder and allows the original Python to open SQE
without re-installing anything. Renaming it back enables the managed runtime.
The selection marker is source-folder-specific; a different extraction path
will not automatically reuse that Python environment.

If the old launcher then works, this is evidence of a managed-startup issue,
**not** proof that a solver installation failed. Solver runs still require
native engine qualification and scientific validation.

## Recovery: qualification still uses Python 3.15 after environment setup

A missing `launcher-errors.log` is **not** evidence of a successful Python 3.11
startup. The launcher only writes that file when a startup error is raised.
An environment that is missing its `ready.json` marker or is still bound to a
previous source extraction may be silently absent from runtime selection in
older builds. These cases are **not solver failures**.

The corrected desktop launcher displays its active interpreter. If it shows
Python 3.15 and a prepared environment exists, choose **Reconnect existing
scientific environment**. Select the prepared environment, review and confirm
the re-link, then close and reopen SQE Studio. The app validates that the
selected executable is Python 3.11 x64 before creating a local binding. It
never copies a virtual environment, installs new packages or edits `ready.json`.

If the GUI says no prepared environment is available, **do not delete or
reinstall anything**. An environment may be incomplete (`venv/Scripts/python.exe`
exists, but `ready.json` is absent), or a package bootstrap may have failed.
Use **Prepare scientific environment** to review the status, and share a new
Comprehensive qualification ZIP if further diagnostics are needed. The new
report includes counts of ready/incomplete environments. Do not send `venv`
folders, local projects, access tokens or browser profiles.

If the qualification fails `source_integrity`, inspect the dedicated
`logs/source_integrity.txt`. The corrected verifier includes *relative*
added/missing/modified source paths (capped to 30 per category); it never
silently repairs source inventory or rewrites the historical foundation lock.
Preserve old evidence and extract a clean release ZIP into an empty source
folder to distinguish residual files from changed released code.

A successful re-link only establishes which Python environment will be used:
actual browser, native EM/quantum computation, numerical convergence and
foundry release qualifications remain separate gates.

## SQDMetal in the scientific environment checklist (RC12 / dev13)

In **Prepare scientific environment**, check **SQDMetal** and keep **Automatic official GitHub source** selected. SQE performs the download automatically **only after explicit approval**; a manual GitHub visit or folder selection is no longer required. It resolves `main` to a complete Git SHA via the official GitHub API, downloads the ZIP for that immutable commit from `codeload.github.com` over HTTPS, enforces download/expansion limits and archive path rules, rejects symlinks and unsafe paths, and computes its SHA-256 before allowing installation. It records the source commit and ZIP SHA-256 under `%LOCALAPPDATA%/SQE-Studio/sources/sqdmetal/`. Repeat installations reuse the same verified cache, even if the upstream branch has changed. An explicit **Update the saved official Git revision** option refreshes that pin; a corrupt or missing pinned artifact fails closed without silent replacement. The installer runs in the existing managed Python 3.11, never the system Python.

This is *official-source provenance by HTTPS and first-use pinning*, not a pre-audited or independently signed release: the SQDMetal repository has no stable GitHub Release artifact. No fixed upstream Git commit or archive SHA-256 is baked into this RC because live fetching was not available on the build host. The first real Windows installation must be tested and its exact commit/digest captured. The upstream `pyproject.toml` may install additional dependencies (including Quantum Metal components); source upgrades warrant dependency/API review. No silent dependency rollback is claimed.

For developers or offline machines, choose **Local source folder (advanced)** and point to an extracted SQDMetal repository with `pyproject.toml` and `SQDMetal/PALACE/Eigenmode_Simulation.py`. This mode checks structure but **does not verify upstream origin**; review it separately. Errors appear as `FAILED` or aborted setup, never a successful scientific qualification. Palace WSL/Spack and Julia are never installed by this action. After installation, restart SQE and run **Qualify this laptop → Comprehensive**, then attempt a reviewed mesh/deck and actual Palace solution in the *generic design workflow*.
