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
| SQDMetal | **No automatic source/HEAD install** | Review a fixed revision, Python 3.11 dependencies, SQE bridge, Palace deck generation |
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
