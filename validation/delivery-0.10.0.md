# Consolidation delivery — SQE Studio 0.10.0

This release consolidates the uploaded 0.9.0 workstation plus the known Windows path and WSL detection fixes into a clean, English-first distribution. It preserves the existing scientific engine, project schema and worker contracts. The working `studio-data`, .venv, previous diagnostic archives and original local installation logs are excluded from the release ZIP.

## Automated evidence

- New Web diagnostic manager/API: administrator authentication, CSRF, production disablement, immutable local ZIP download, restart interruption, error handling and retention cap.
- Existing scientific regression suite: see delivery test log; optional native packages may be absent.
- JavaScript syntax: main Web application, Quantum Design Lab and new control center.
- Python syntax: source, bootstrap, and diagnostics managers.
- End-to-end diagnostic ZIP generation using installed interpreter. This is not an authentic Palace FEM benchmark.

## Not validated on this development host

Windows 11 GUI launch and PowerShell script execution, actual Palace source build on Ubuntu 26.04 WSL2, real Palace 3D field solution and physical benchmark, native Quantum Metal runtime, JosephsonCircuits.jl nonlinear solve, full browser visual interaction, and cross-host remote scheduling. Green diagnostics indicate a successful check, not validation of all those separate systems.

## Known trade-offs

- Local Web diagnostics are restricted to administrators and loopback development instances; native installs remain OS-user-consented scripts.
- Python smoke tests are non-blocking at startup to permit collecting diagnostic reports from the Web UI.
- The Web server must be running to use Web diagnostics; `WINDOWS-DIAGNOSTICS.cmd` is retained for early bootstrap failures.
- Reports are allowlisted and sanitized, but the user must inspect them before sharing.
