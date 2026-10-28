# SQE Studio 0.12.0 — Palace Benchmark & Solver Observability

## Run from the browser

1. Start `WINDOWS-FIRST-START.cmd` and sign in as a local administrator.
2. Open **System & Diagnostics** (`http://127.0.0.1:8000/control.html`). Inspect **Compute queue health** and avoid starting duplicate FEM jobs.
3. Select **Palace scientific diagnostics**. Choose **Quick** first, then **Run checks**.
4. Download the resulting ZIP, inspect it for sensitive data and send it for debugging. No upload happens automatically.
5. Only after Quick succeeds, consider **Standard**. Select **Full** only when you can tolerate a large mesh and longer solve times.

## Profile definitions and resource expectations

| Profile | Steps | Deadline per stage | Result limitations |
| --- | --- | --- | --- |
| **Quick** (default) | Tiny 3D Gmsh unit box; load Palace via WSL2/Spack; execute `palace --help` | 45s mesh; 100s solver activation | No actual electromagnetic solve; verifies installation/executable only. |
| **Standard** | One-transmon geometry/GDS + coarser Gmsh 3D mesh + Palace electrostatic + capacitance extraction | 40s geometry; 240s mesh; 450s electrostatic; 40s extraction | Execution/integrity test only; coarse mesh deliberately **not converged**; not analytic-accuracy-checked. |
| **Full** | Same geometry at original mesh settings + electrostatic, capacitance, eigenmode, driven 2 ports | 40s geometry; 360s mesh; 780s each EM stage; 1500s for both RF ports | Potentially high resource use (prior 1.29 million volume elements); not automatically mesh-converged. |

Standard uses a minimum mesh size of at least 25 µm and maximum of at least 500 µm in the fixed reference config to reduce computational expense. These settings do **not** override project geometry and should **not** be used to infer device performance. Full retains the existing prototype configuration.

## Evidence and fault handling

Each case produces `PASS`, `FAIL`, or `SKIP` with an elapsed time and diagnostic code. The ZIP contains allowlisted `environment.json`, `checks.json`, `test-results.txt`, `SUMMARY.txt`, `README-PRIVACY.txt`, `manifest.json`, and `SHA256SUMS.txt`.

- Subprocess output is streamed to a temporary disk file, not held unbounded in RAM. At the end of the step, bounded, sanitized tail excerpts are copied into the ZIP, including Palace's `electrostatic.log`, `eigenmode.log`, and driven-port logs when they exist.
- `TIMEOUT` is not a physical failure verdict. The worker terminates the Windows process group, and the WSL solve invokes Linux GNU `timeout` to bound detached children even if the Windows proxy stops.
- If `/usr/bin/time` is installed in Ubuntu, Linux solver logs include CPU and peak resident-memory accounting; otherwise they explicitly state unavailable. Windows system-wide CPU/memory sampling is not provided in this release.
- Failed prerequisites produce `SKIP`, never made-up Palace output. Output files are verified by checksums and named solver artifacts.
- The isolated workspace and raw field data are removed after testing; only scrubbed, bounded text evidence is shared. Review all report files for privacy before sending them.

## Scientific qualification remains separate

Successful Quick only verifies basic native tools. Standard/Full can establish that Palace completed on a specific generated geometry, but **not** absolute accuracy, mesh convergence, reliable mode tracking, parameter extraction, or fab readiness. The subsequent roadmap calls for reference analytic benchmarks, mesh-refinement studies, numeric tolerances, stable WSL worker management and field visualization.

## Windows update

Stop SQE Studio, back up `studio-data`, and extract the v0.12.0 archive over the current `SQE-Studio` folder without deleting `.venv` or `studio-data`. Restart using `WINDOWS-FIRST-START.cmd`. The Palace/Spack installation under Ubuntu WSL2 remains untouched.

For initial acceptance testing please run **Quick only**, then send the diagnostic ZIP. There is no reason to rerun an expensive Full test until the Quick report has been reviewed.
