# SQE Studio RC12 — Automatic SQDMetal Scientific Environment Setup

**Version:** 0.1.1.dev13  
**Status:** EXPERIMENTAL / BLOCKED_NOT_RELEASE_CANDIDATE

## Change summary

The desktop **Prepare scientific environment** checklist now supports installing **SQDMetal** in one action without downloading or selecting a GitHub folder manually. On the first explicitly approved use, SQE queries only the official `sqdlab/SQDMetal` repository, resolves the `main` branch to an exact Git SHA, downloads the source ZIP from official GitHub HTTPS at that SHA, checks for unsafe archive members, and records the ZIP SHA-256. Subsequent approved SQDMetal installations reuse this pinned local archive with a new integrity check. **Updating the pin requires explicit user selection**. Advanced local-folder installation remains available for offline/developer use.

The source is third-party executable code. **SQE has not independently audited or signed the upstream revision**, and the downloaded archive is not checked against a prepublished, independent hash. At first installation, GitHub HTTPS and the returned Git SHA are the initial trust source; the SHA-256 subsequently protects the cached bytes against local changes. No automatic source download occurs at application startup or from the EDA job system.

The same local Python 3.11 environment is reused. SQE will **not** install or reconfigure Julia, Palace, WSL2 or system Python. Installation may change Python dependencies in that managed environment, so the native API and scientific qualification must run afterward.

## Verified on build host

- Complete suite: **311 passed, 14 skipped, 0 failed, exit 0** (captured in `evidence/pytest-verified.log` and `.exit`).
- Bounded-download logic, exact commit selection, pinned cache reuse, corrupted cache/pin rejection, malicious ZIP/path/symlink rejection, remote redirect rejection, explicit refresh and local offline path tested with controlled HTTPS fixtures, not live GitHub.
- Source inventory and frozen contract digest **PASS**. Historical `FOUNDATION_LOCK.json` preserved.
- Two `0.1.1.dev13` wheels are byte-identical under fixed `SOURCE_DATE_EPOCH`; SHA-256: `7aa9106684a9c0d5cfa48b0f9f79191c911aefcf8d57336ff9e96d89a1a6f164`.
- Wheel installation into an isolated Python environment and an actual localhost authenticated HTTP smoke **PASS**.

## Windows user acceptance

1. Extract the complete RC12 ZIP into a **new** folder and launch `Launch SQE Studio.pyw`. Reconnect your existing Python 3.11 runtime if prompted.
2. Open **Prepare scientific environment**; uncheck other packages and check **SQDMetal**. Keep **Automatic official GitHub source** selected and **Update the saved Git revision** unchecked for ordinary repeat installation.
3. Read the explicit third-party source/dependency confirmation and approve. A first-time download requires HTTPS access to `api.github.com`, `codeload.github.com` and PyPI for declared dependencies. The desktop setup log will show the exact commit and archive SHA-256.
4. Restart SQE Studio, then select **Qualify this laptop → Comprehensive** and share the resulting ZIP. Inspect the `native_sqdmetal_api` gate. An API PASS does not imply a Gmsh mesh or Palace solve.
5. Keep your existing Palace WSL2/Spack and Julia/JosephsonCircuits configurations unchanged. After the API handshake, prepare a normal reviewed EM design and attempt a **mesh/deck-only** native job before a full Palace solve.

## Known constraints

- No live GitHub acquisition or Python 3.11 Windows installation was performed on the build host because its network is unavailable; simulated tests validate only the installer logic, not the current repository compatibility or upstream dependencies.
- Some upstream SQDMetal dependencies may conflict with packages already installed in the scientific Python environment. A failure stays FAILED; the installer does not silently repair dependency changes or claim solver readiness.
- The release-candidate scientific gates remain blocked: native meshing, Palace eigenmode solve/convergence, validated EM→Hamiltonian EPR, optimization driven by real solves, and independent physical/fabrication qualification.
