# Unified Web Workspace — Release 0.17.0

## Information architecture

The default `/` page has only five primary steps: **Project → Setup → Run → Results → Support ZIP**. Do not treat the legacy Web applications as separate workflows. The earlier device editor lives at `/editor.html`, while the old `/experiments.html`, `/control.html` and `/quantumlab.html` remain reachable for compatibility and specialized inspection. The main workspace itself is the supported starting point.

| Stage | Main action | Output |
| --- | --- | --- |
| Project | Select example/imported workflow/Studio project; import workflow ZIP or create design | Selected project and step plan |
| Setup | Review dependency readiness; one-click automatic install/repair; inspect setup history | Isolated environments, smoke-test status, setup support ZIP |
| Run | Execute multi-engine workflow, Studio report, standard/full regression suite or scientific diagnostics | Persistent run record |
| Results | Inspect status, step-level results, summaries, logs and past runs | Browser-readable run details |
| Support ZIP | Download the selected run's ZIP | One sharable package with manifest and checksums |

Run types share the same report transition, even though they retain distinct server-side executors and physical qualification contracts. No result is promoted to *scientifically validated* from a passing setup probe or an artifact-integrity check.

## First-launch engine provisioning

Automatic engine setup starts only on the **local workstation launcher**, on the first start using each `studio-data` location. `SQE_AUTO_INSTALL=0` disables it for deployments that must provision packages offline. For CI or remote servers there is no uncontrolled installation on Web requests. The browser offers manual per-engine repair and an install-all button; those actions are only available to authenticated local administrators and require CSRF tokens.

The installer does not accept arbitrary package names or commands. It uses a fixed allowlist, bounded subprocess timeouts, logs and one active installation at a time. Installation sources may include the configured pip index, the upstream SQDMetal Git repository and the Julia General registry. Upstream dependencies can change over time; a setup report is evidence of what was attempted, not a reproducible software lock file.

### Environment rules

- Built-in QuantumLab needs no extra package.
- scqubits and Gmsh use the Studio interpreter. scqubits is smoke-tested with a two-level transmon eigensolve; Gmsh is smoke-tested with a native geometry API call.
- Quantum Metal and SQDMetal use one **separate Python 3.11 virtual environment**. SQDMetal currently declares `requires-python >=3.11,<3.12` and depends on Quantum Metal and external scientific tooling. The app cannot silently make incompatible operating systems or external COMSOL/Palace installations supported.
- JosephsonCircuits.jl uses a **separate Julia Pkg project**, and can be installed automatically only if a working Julia runtime is already available.
- Palace/WSL native installation is deliberately not automated by pip. Its readiness and numerical validation remain separate.

**Dependency smoke tests and solver validation are different.** An imported library can succeed while a chosen solver, boundary assignment, mesh, superconducting material model or numerical extraction is unqualified. Always verify the actual simulation artifacts.

### Support and repair

The Setup screen lists each dependency as ready or missing, its environment and the post-install check. If a setup attempt fails, download **Setup history → Support ZIP**. The bundle includes `status.json`, `install.log`, `manifest.json` and SHA-256 digests. The installer never uploads it. A failed multi-engine run or diagnostic also produces a ZIP, including partial data when available.

For end-to-end scientific qualification, use **Run → Tests and diagnostics → Palace scientific diagnostics**. Start with geometry and boundary audits before costly FEM solves. Built-in one-qubit workflows provide a repeatable non-FEM baseline.

## Security and reproducibility

The server accepts only safe, declarative JSON/YAML/CSV workflow ZIPs. An uploaded Python factory is not executed. A **bundled** Quantum Metal factory and actual external solver execution each require an explicit browser opt-in. Installation and external execution require a local administrator; remote deployments have no engine installation endpoints.

The managed SQDMetal installer currently uses the project's Git repository rather than a pinned packaged wheel. For fully reproducible deployments, capture the setup report and resolve the VCS commit plus the dependency freeze into a deployment lock before qualification. Logs may contain local paths or project details: review any exported ZIP before sharing.

## Feature limitations

This release reorganizes and connects existing scientific components; it does not establish parity with Keysight ADS QuantumPro. Advanced layout DRC/LVS/PDKs, complete EM-to-circuit reduction, arbitrary multimode EPR quantization, pumped nonlinear steady-state harmonic balance, job scheduling across clusters and target-hardware validation remain substantial research and engineering work.
