# Windows workstation setup (SQE Studio 0.10.0)

## One-click application startup

- On Windows 11 x64, extract the ZIP into a writable user-owned folder, not Windows system folders, a ZIP preview, or an unhydrated OneDrive placeholder.
- Double-click `WINDOWS-FIRST-START.cmd`. A compatible Python 3.11–3.13 interpreter is discovered; if none is found, the launcher downloads the official Python 3.12 installer, checks its Authenticode signature and installs it per user.
- The launcher creates/reuses `.venv`, installs pinned core dependencies, attempts the optional `gmsh` wheel, records optional scientific startup checks, then starts the Web service and separate worker.
- **An optional scientific regression failure does not block the Web UI.** Open System & Diagnostics to inspect the failure. Missing core Python modules or invalid installation may still prevent the server itself from starting.
- The first browser visit opens a one-time administrator setup link. The server binds to `127.0.0.1:8000` only. Do not expose this local launcher directly to the Internet.

## Working in the browser

- `http://127.0.0.1:8000/`: login, projects, stage execution, files and history.
- `http://127.0.0.1:8000/quantumlab.html`: QPU circuit and physical-design workbench.
- `http://127.0.0.1:8000/control.html`: protected local diagnostics, test reports and ZIP downloads.

The new Diagnostics view is the recommended way to capture software and native-tool checks. The old `WINDOWS-DIAGNOSTICS.cmd` remains only as an emergency fallback when the server cannot start.

## Native Palace / WSL2

Palace is a Linux FEM solver and is **not shipped as a binary**. Use the opt-in `WINDOWS-PALACE-SETUP.cmd` from the **same Windows user account that launches Studio**. WSL distributions are per-user: Ubuntu installed under a different administrator account is not available to a normal-user session. The installer probes `Ubuntu` directly, converts the Windows source path using `wsl.exe --exec wslpath`, and asks before Spack compilation. Ubuntu 26.04 has not been formally qualified. See `docs/palace-windows.md`.

For Windows machines with 32 GiB RAM, start with small meshes, one or two MPI ranks and a constrained WSL memory budget; collect actual run data before tuning concurrency. Spack builds may be large and time-consuming.

## Other optional solvers

- `WINDOWS-JOSEPHSONCIRCUITS-SETUP.cmd`: separate Julia project for JosephsonCircuits.jl; does not automatically enable an HB Web solver.
- `WINDOWS-QUANTUM-METAL-SETUP.cmd`: separate Quantum Metal environment; never force its dependencies into the core Web environment.

## Troubleshooting

If the browser cannot open, check the launcher window. Port 8000 may be occupied; use the `-Port` argument with the one-click launcher if necessary. If Python is unavailable, run the fallback diagnostics script. Never delete `studio-data` to repair Python dependencies. Download a Web diagnostic ZIP, inspect it for personal data, and share the report rather than account or project files.

This release has been tested using Python and simulated/existing solver contracts; no complete real-world Palace qualification on Windows is claimed.
