# Palace on one Windows workstation via Ubuntu/WSL2

## Supported approach

The SQE Studio Web process runs on Windows; the open-source Palace FEM binary is built and executed inside a separate Ubuntu WSL2 distribution. The same design can later move to a more powerful Linux server. Palace is not bundled as a precompiled Windows executable, and WSL support is best-effort rather than a fully qualified production target.

## Installation

Use `WINDOWS-PALACE-SETUP.cmd` from your everyday Windows account, after Ubuntu is initialized in that same account. The installer asks before any WSL installation and before the Spack/Palace source build. On Windows, WSL registrations are per user; Ubuntu registered under another administrator account will not be visible to Studio. Do not remove or re-register unrelated distributions such as Docker Desktop.

The installer probes the distribution directly to avoid PowerShell UTF-16 parsing issues, then converts the installer script path through `wsl.exe --exec wslpath`. Missing paths must stop with a clear error, not continue with a null expression. Linux-side installation uses `scripts/install_palace_wsl.sh`, `sudo` for required packages, Spack for solver dependencies and a Palace source build.

WSL2 with Ubuntu 26.04.1 is a real observed workstation configuration, but the Palace build and solver numerical correctness are **not yet qualified** for it. An alternative Ubuntu 24.04 distribution can be tested separately if solver dependencies prove incompatible. Preserve build logs for debugging.

## Web workflow

Start SQE Studio and use Quantum Design Lab → Palace/FEM to inspect installed tools, generate mesh/configuration inputs and enqueue supported FEM stages. Use System & Diagnostics to check Python/Gmsh and optional WSL/Palace availability without entering commands. A detected Palace executable is **not** proof that a real solver input converges.

## Supported simulation contracts and limits

Electrostatic capacitance, eigenmode with linearized JJ, per-port driven RF and mesh-convergence jobs are implemented at the contract/worker level. The current geometrical mesher is conservative and intentionally rejects stack-ups not faithfully represented by its supported physical model. Quantitative QPU parameter extraction and real 3D package workflows require additional validation. Do not replace a failed FEM result with a nominal circuit estimate labeled as extracted.

## Next qualification benchmark

Run an independently specified electrostatic reference geometry, collect the actual Palace raw files and compare capacitance with an analytic/reference result across at least three mesh levels. Then repeat for an eigenmode test, tracking mode identity and boundary conditions. Measure runtime, RAM and resource scaling on the target laptop. Export diagnostics and solver provenance before any claim of scientific accuracy.

## Moving to a server

Back up the private data directory, then deploy the Web application and solver worker on Linux over HTTPS. Existing local SQLite files should not be shared between multiple hosts over SMB/NFS; an independent multi-host queue architecture requires additional work.
