# Installed Julia and Palace: Windows binding and qualification

**Status: experimental engineering support. Not scientific release qualification.**

SQE Studio is an integrated EDA design environment. Solver configuration is a separate **desktop administrative** operation, never a project-specific scientific shortcut or a server endpoint. No source control, frozen contracts, material models, DRC/LVS or physical algorithms are changed by binding an installed engine.

## Configure in the desktop GUI (no terminal required)

1. Launch `Launch SQE Studio.pyw` with the existing managed Python 3.11 runtime.
2. Open **Configure installed solvers (Julia / Palace)**.
3. If Palace runs in WSL2, select **Palace in WSL2**, enter the **absolute Linux executable path** (`/opt/.../bin/palace` or another existing Palace binary), and optionally enter the WSL distro name (for example `Ubuntu-24.04`). A native Windows executable uses the **Palace native executable** setting. This is a *path to the binary*, not a path to a mesh or user design. The default WSL distribution is used when the distro field is empty.
4. For Julia, keep **Existing Julia project** blank when `JosephsonCircuits.jl` is already installed in the normal Julia environment. If it lives in a separate Julia project, select the directory containing its `Project.toml`. Julia itself being on PATH is not sufficient: `JosephsonCircuits.jl` must be loadable in the selected project.
5. If the Julia package really is missing, use **Install JosephsonCircuits.jl into isolated SQE Julia project...** in the same window. This action requires your explicit confirmation; it invokes Julia's package manager and downloads dependencies. It creates a project under `%LOCALAPPDATA%/SQE-Studio/julia-project`, does not install a new Julia executable and does not modify the default Julia project. Network access is needed. If it fails, no RF result is admitted.
6. Save, close/restart SQE Studio, select **Qualify this laptop > Comprehensive**, and attach only the generated report ZIP to developers after checking it for private paths.

The settings file is kept under `%LOCALAPPDATA%/SQE-Studio/solver-settings.json`, outside the source archive and outside design projects. It is intentionally **not** included in the qualification ZIP. Source/contract integrity remains independently checkable.

## Why the previous report missed installed packages

The Python/browser test harness runs in a private temporary home for security. On Windows, the old harness thereby inadvertently hid the ordinary `.julia` package depot when testing JosephsonCircuits. The current runner keeps the original Julia depot path for *Julia child processes only* while retaining its private Python/browser workspace. A custom `JULIA_DEPOT_PATH` is preserved. The report never copies package cache contents.

Similarly, Palace is commonly installed inside WSL rather than on Windows PATH. The runner now tests the explicitly configured Palace executable through the same native/WSL identity handshake as the real adapter, using the chosen WSL distribution for both Windows mesh-path translation and solver execution.

## What the gates mean

| Gate | PASS means | Not established |
|---|---|---|
| `julia_package_runtime` | Julia executed and `JosephsonCircuits.jl` was found in the selected project/depot | RF equations solved or numerical correctness |
| `native_josephson_circuits` | Both native RF test cases actually executed successfully, with no skips | Validation against calibrated measurements |
| `native_palace_runtime` | A configured executable passes a CLI identity handshake (`--version` when supported, otherwise the strict official `--help` signature). Help-only verification explicitly records `version_verified=false`. | WSL MPI/dependencies, actual compiled solve, QDesign, meshing, or an EM solution |
| `native_em_design_loop` | **Still blocked** until reviewed project geometry, boundaries, materials, mesh convergence and genuine Palace results are available | Cannot be cleared by `palace --version` |
| `em_quantum_bridge` | Still blocked: reviewed EPR-to-Hamiltonian transformation not implemented | No automatic quantum parameter extraction claim |
| `geometry_optimization` | Still blocked: no validated native objective-driven design loop | A parameter sweep alone is not optimization |
| `foundry_release` | Still blocked: independent DRC/LVS and foundry signoff missing | GDS generation is not fabrication approval |

If Julia or Palace is configured but the process fails, the diagnostic gate must **FAIL** with a bounded error log, not claim success. The `SQDMetal` Python module remains a distinct dependency; Palace plus Gmsh does not automatically provide it. Installing SQDMetal is not attempted automatically from arbitrary Git source. Installing a solver is not equivalent to qualifying scientific results.

## References

- SQDMetal, [Palace simulation installation and workflows](https://sqdlab.github.io/SQDMetal/simulations/simpalace.html): local solver / Windows via WSL / explicit `palace_dir`.
- AWS Palace, [Quick Start](https://awslabs.github.io/palace/stable/quick/): `--help` and `--version` behavior, native config and mesh inputs.
- JosephsonCircuits.jl, [official Julia package documentation](https://josephsoncircuits.org/stable/): Julia's `Pkg.add("JosephsonCircuits")` and native RF solvers.

## Palace 0.16.x installed by Spack in WSL2

Palace's **v0.16.0** shell wrapper documents `--help` but does not implement
`--version` as a wrapper option. Newer documentation may show a `--version`
option. The RC9.1 qualification runner accepts the precise official `--help`
output after verifying that the configured WSL file is executable, and records
`identity_probe=--help`, `version_verified=false`, `version=unreported by CLI`.
The installer-reported package version (for example `spack find -p palace`)
remains separate provenance, not substituted for an executable version proof.
The gate **does not test MPI, library dependencies, mesh, a native solution or
scientific correctness**. A full EM acceptance still requires the reviewed
SQDMetal/QDesign/Gmsh/Palace workflow and convergence evidence.

The qualification report must always be saved even when the Julia runtime is
present. A successful package discovery probe is not a reason to abort evidence
packaging or overwrite the report destination variable.
