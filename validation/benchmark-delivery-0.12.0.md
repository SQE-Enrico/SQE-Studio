# SQE Studio v0.12.0 - Validation record

Target: Windows 11 / Ubuntu WSL2 + Palace installation previously detected on the user's ThinkPad E16 Gen 2. That physical target is NOT accessible in this build environment.

## Verified in development environment

- Python source compiles, and control.js passes the Node syntax checker.
- Bash Palace WSL runner passes `bash -n`.
- Scientific profile validation, fixed quick stages, legacy full-stage skip behavior, solver failure logs, diagnostic allowlisted ZIP, authorization and HTTP profile validation tests pass.
- Existing scientific modules and Web diagnostic permissions tested in regression.
- The full regression suite printed `Ran 141 tests ... OK (skipped=4)`. Observed process completion through the log; the outer execution tool exceeded its wait budget, so exit-status verification was also performed separately on targeted suites.

## Not verified

- Windows PowerShell bootstrap and live UI interactions after upgrade.
- Quick's `palace --help` on the actual user Ubuntu/Spack installation.
- Palace electrostatic, eigenmode and RF solves with reference meshes.
- Numerical convergence, physical accuracy, peak RAM/CPU measurements on the real workstation.

## Safety boundaries

- Quick does not construct the million-element transmon mesh.
- Each stage runs a fixed subprocess with a time limit and bounded disk log. Palace WSL runs are subject to Linux-side GNU timeout as well as the Windows/Python deadline.
- Logs are best-effort redacted; diagnostic ZIPs must be reviewed prior to sharing.
- No user projects or runtime `studio-data`, `.venv`, local tokens or credentials are bundled.
