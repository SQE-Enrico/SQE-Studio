# SQE Studio 0.1.1.dev9 — Installed Solvers / Windows WSL Binding

**Status: EXPERIMENTAL_NOT_RELEASE_CANDIDATE**

## Input evidence

- Parent source archive: `SQE-Studio-RC8.1-browser-qualification-EXPERIMENTAL.zip`
- Target Windows qualification: `SQE-Studio-qualification-20261030(9).zip`, integrity-verified in earlier triage; 10 PASS, 0 FAIL, 6 BLOCKED. Two of those blocked gates were the Julia/JosephsonCircuits runtime and native EM/Palace stack. Native execution on the user's laptop is not claimed for this build.
- Original `FOUNDATION_LOCK.json`, frozen contract files, scientific safety policy and ownership records were preserved.

## Resolved software gaps

1. **Julia depot discovery:** The qualification harness previously replaced `HOME` and `USERPROFILE` with a temporary home for every child, hiding the Windows Julia package depot (`%USERPROFILE%/.julia`) from the native tests. New qualification invocations retain the originally configured `JULIA_DEPOT_PATH` or the original Julia default depot for Julia test subprocesses, while retaining an isolated home for Python/browser. They never archive the depot or Julia project files.
2. **Explicit Julia package gate:** `julia_package_runtime` probes the selected active project/depot via a real Julia process. A Julia executable without `JosephsonCircuits.jl` remains `BLOCKED`. A failed configured probe is `FAIL`. Native JosephsonCircuits tests still have to actually execute.
3. **Installed Palace binding:** A new optional desktop-only **Configure installed solvers (Julia / Palace)** panel stores Palace native or Windows WSL executable location and optional selected WSL distro in a user-local settings JSON. An optional existing Julia project can also be selected. This is not a per-design shortcut or HTTP API.
4. **Same WSL distro through mesh path and solve:** Palace A03 adapter now retains the selected WSL distro for binary verification, workspace path translation, and solver invocation; existing WSL default remains supported.
5. **Independent Palace runtime gate:** `native_palace_runtime` executes the existing adapter's binary/version handshake. It may pass while `native_em_design_loop` remains blocked awaiting reviewed material, boundary, port and convergence evidence.
6. **Optional explicit Julia package setup:** The desktop dialog provides a confirmed, optional installation of the published `JosephsonCircuits.jl` package into a separate SQE-owned Julia project via `Pkg.add`, rather than changing the default Julia project. Network traffic/downloads require the user's click and confirmation. No solver auto-installer is run silently.
7. **Version:** `0.1.1.dev9` wheel and matching Windows install/build scripts. No edits to frozen contracts, engine physics, RF normalization, solver outputs, foundry HOLD or authentication controls.

## Verification performed on this build environment

- Full available pytest regression, excluding separate real-browser acceptance: **282 PASS, 11 SKIPPED, 0 FAIL**. Those 11 skipped native tests depend on runtimes unavailable in this Linux host.
- New targeted WSL distribution, isolated Julia package installer (mock subprocess only), settings validation, qualification depot preservation, and integrity tests executed.
- `tools/verify_release_source.py`: PASS, evolved source inventory SHA-256 **2592bad2d2721fb4bdebbce8b63248991d4c106e0b4f61f2c2de40006cce62d3**.
- Two offline wheels with fixed `SOURCE_DATE_EPOCH` had the exact same SHA-256: **3415aa6ae750df44f402a72fc0ed5ec0d92e6d0593a896acaccd32802e60fa8a**.
- Installed wheel byte/provenance verification in isolated venv: PASS, version `0.1.1.dev9`.
- Installed HTTP test: PASS, real loopback auth, CSRF, revisions and bundled GUI assets.
- Native Julia, Windows WSL Palace, SQDMetal, browser GUI acceptance and full EM solver calculations: **NOT RUN on this host**; do not infer completion.
- One earlier full regression attempt timed out near test-process completion; the subsequent complete run finished successfully and is preserved as evidence.

## Practical Windows sequence without shell

1. Back up the previous extracted source directory; extract the complete RC9 ZIP into a new folder.
2. Open `Launch SQE Studio.pyw`; reconnect the existing Python 3.11 environment if necessary.
3. Click **Configure installed solvers (Julia / Palace)**. Choose **Palace in WSL2** if installed in WSL, optionally specify its WSL distro, and select the absolute Linux Palace executable. **Find in WSL** can detect a binary on the selected distro's PATH; if Spack didn't activate the package in non-interactive mode, the full path must be entered instead.
4. Keep the Julia project empty to use the default installed Julia package environment. If Julia exists but JosephsonCircuits is not in the selected project, use the explicitly consented **Install JosephsonCircuits.jl into isolated SQE Julia project** button.
5. Save and restart. Run **Qualify this laptop > Comprehensive**, share the new ZIP after checking logs for private paths.

## Still blocking scientific RC

- The SQDMetal Python adapter must be importable in the selected scientific Python runtime, independently of whether Palace exists in WSL.
- A real QDesign -> Gmsh mesh -> Palace solve, convergence and port/material review must succeed in the generic project GUI. Runtime version verification does **not** qualify the scientific data.
- EM-to-EPR-to-Hamiltonian mapping, reviewed kinetic-sheet model, objective-driven geometry optimization, independent reference comparison and DRC/LVS/foundry signoff are not finished. Fabrication remains HOLD.

## Sources

- https://sqdlab.github.io/SQDMetal/simulations/simpalace.html
- https://awslabs.github.io/palace/stable/quick/
- https://awslabs.github.io/palace/stable/faq/
- https://josephsoncircuits.org/stable/
