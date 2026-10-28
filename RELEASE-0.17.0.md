# SQE Studio v0.17.0 — Unified Web Workflow and Automatic Engine Setup

**Release scope:** substantial information-architecture overhaul, plus best-effort automatic setup and smoke testing of optional scientific engines.

- The default browser page is a new responsive five-stage workflow: **Project / Setup / Run / Results / Support ZIP**. It replaces the previous disjoint home navigation.
- Legacy detailed editors and specialized pages are preserved for existing projects, bookmarks and regressions, reachable as advanced tools.
- Setup probes optional engines and, on the first launch through the local workstation launcher, starts background allowlisted provisioning without blocking the UI. Retries and individual engine installs are available from the browser.
- scqubits/Gmsh use the Studio environment, Quantum Metal/SQDMetal use an isolated Python 3.11 environment and JosephsonCircuits uses a Julia project. Palace remains a native prerequisite, not silently installed.
- Managed sidecar Python can now execute Metal/SQDMetal workflows through the existing immutable ecosystem runner, instead of merely showing a detected package in an unrelated interpreter.
- All new UI, code, error messages, tests and documentation are in English. A legacy Quantum Design Lab mixed-language placeholder was corrected.
- Dependency provisioning records every engine outcome, and failed/partial attempts can be exported as a support ZIP.
- No arbitrary shell commands, user-supplied pip names or untrusted Python code can be submitted through the installer.

**Validation:** see `validation/unified-web-delivery-0.17.0.md` for actual local software test results. Real third-party SQDMetal/Palace and Julia numerical results were not qualified in this build environment. Import checks and synthetic API tests must not be interpreted as numerical solver validation.
