# SQE Studio — integrated superconducting and microwave EDA

SQE Studio is an **experimental graphical environment for design → native simulation → physical interpretation → design improvement**. Its scope includes superconducting QPUs, resonators, readout components, fluxonium, microwave networks and Josephson RF circuits. **It is not an experiment registry** and examples do not have separate execution paths. The long-term competitive reference is the integrated QuantumPro-class EDA workflow, **not a claim of product parity**.

**Release status:** experimental, **not scientifically qualified**, not a standalone signed installer and not foundry approved. Local software tests do not establish solver accuracy or measured-device performance.

## Open the application (no command line for normal design work)

On Windows with Python and Tkinter already installed, extract the archive and double-click **`Launch SQE Studio.pyw`**. The desktop launcher starts a **localhost-only** authenticated web interface and opens a browser. Use its one-time local setup token to register and then sign in. Close the launcher to stop the service. This is a Python-based desktop launcher, not a compiled Windows application; click **Prepare scientific environment** for an optional, consent-based Python 3.11 sidecar installation (build/test tools, scqubits, Quantum Metal, Gmsh, browser tests, and SQDMetal automatically from the official GitHub repository at a saved, SHA-256-verified Git commit (or an advanced local source folder)). Palace WSL2 and Julia are configured separately; no automatic Windows Palace installation is claimed. SQDMetal installation alone is not EM qualification. If the source folder was moved after setup, the desktop launcher shows the active Python version and offers **Reconnect existing scientific environment**; this action verifies and reuses the earlier Python 3.11 environment without downloading packages. No cross-platform installer is qualified.

The GUI creates ordinary editable projects, not one-off demonstrations. In **New project**, choose Blank, **CPW resonator**, **Transmon spectrum**, or **Fluxonium flux sweep**. The same dialog shows additional literature-based design cases and the scientific edges that remain blocked. All supported projects use `sqe.project.v1`, revision saving, the same engine studies and the same results views.

## Automated laptop qualification and report sharing

For a release-candidate evidence run, click **Qualify this laptop** in the same desktop launcher, choose **Comprehensive**, and save the generated `SQE-Studio-qualification-*.zip` to share with developers. No terminal is required. It runs isolated software, installed-package, real browser and available native-engine checks without reading saved design projects. Missing runtimes, unsupported EM/quantum bridges, nonconvergence and incomplete validation are reported as **BLOCKED**, never silently passed. See [Windows workstation setup](docs/WINDOWS_WORKSTATION_SETUP.md), [laptop qualification procedure](docs/LAPTOP_QUALIFICATION.md) and [release quality gates](docs/QUALITY_GATES.md).

## Product workflow

**Specifications → Schematic → Layout → EM analysis → Quantum/circuit models → Results and iteration → Fabrication gate.** Steps may be inapplicable to some device families but share the design environment. The canvas currently shows *symbolic design intent*, **not** native QGeometry, native EM fields or production GDS.

- **Geometry:** reviewed Quantum Metal QComponent recipes, physical routing and native renderers when installed.
- **EM:** SQDMetal/Gmsh/Palace study configuration and verified output inspection; physical material, ground and port correspondence require explicit review.
- **Quantum:** scqubits on independently entered Hamiltonian inputs. A reviewed EM→Hamiltonian bridge is **not available**.
- **Nonlinear/RF:** JosephsonCircuits.jl is a target native engine, but its production path is **blocked**.
- **Design iteration:** revision-based comparison and bounded native-study numeric sweeps exist. Automatic coupled multi-engine optimization of **geometry** is **not** implemented.
- **Fabrication:** GDS and masks are **HOLD** until independent PDK/DRC/LVS and foundry signoff.

## Developer entry points

Future developers **must** follow [Engineering Principles](docs/DEVELOPER_PRINCIPLES.md), then [EDA extension architecture](docs/EDA_EXTENSION_ARCHITECTURE.md), [published-method design cases](docs/SCIENTIFIC_DESIGN_CASES.md), and [quality/release gates](docs/QUALITY_GATES.md). Source declarations for planned and available cases live in `src/sqe_studio/eda/`; starter inputs are in `design_library.py`. These are **catalogs and gate descriptions**, not alternate simulation engines.

Historical agent ownership reports under `agents/`, `docs/agents/`, and `reports/agents/` remain as audit evidence. The original `FOUNDATION_LOCK.json`, frozen contracts and A01–A09 agent protocol are preserved unchanged, and their baseline digest is **not** a digest of this extended source tree. `docs/AGENT_PROTOCOL.md` describes original delta integration, not the current recommended feature workflow.

## Local security and scientific limits

The server binds only to `127.0.0.1`, with session authentication, CSRF, project ACL, immutable revisions, controlled job execution and content-verified native outputs. Do not put it behind a public proxy or treat this as a security certification. Fixtures, successful package builds, installed Python modules and solver preparation logs are **not** evidence of native scientific qualification. See [current limitations](docs/KNOWN_LIMITATIONS.md) for the remaining barriers.

## Windows 11 RC stabilization update

The October 2026 laptop findings are addressed by a focused integration update.
See [RC_WINDOWS_STABILIZATION.md](docs/RC_WINDOWS_STABILIZATION.md) before
running **Qualify this laptop → Comprehensive**. This remains an experimental,
fail-closed integrated EDA foundation, not a qualified release candidate.

## Windows RC round 7 development update

The earlier RC7 snapshot used **0.1.1.dev7** (not a release candidate). The current installer-improved development source targets **0.1.1.dev13**. The generic EM editor, scqubits sparse-array bridge, Windows worker regression, and independently logged installed-wheel HTTP check are documented in [RC qualification round 7](docs/RC_WINDOWS_QUALIFICATION_7.md). Keep the existing scientific environment; do not reinstall solver packages simply to update this source.

### Installed scientific solvers: Windows desktop bindings (0.1.1.dev10)

SQE can now bind an existing Palace executable running in native Windows or a named WSL2 distribution, and the Julia project/depot holding `JosephsonCircuits.jl`, directly from the **Configure installed solvers** desktop panel. No automatic Palace download or scientific bypass is added. This release distinguishes Palace version verification from a solved, converged EM study and retains the fail-closed integrated EDA qualification. Follow [Installed solver bindings](docs/INSTALLED_SOLVER_BINDINGS.md).

### Native EM bridge qualification (experimental)

See [First native EM solve](docs/NATIVE_EM_FIRST_SOLVE.md) for the single generic GUI workflow, opt-in pinned official SQDMetal source installation, 15-minute bounded reviewed Palace solve, and required convergence/scientific evidence. Installation and API discovery are not solver validation.

### RC12: automatic SQDMetal source acquisition (0.1.1.dev13)

In **Prepare scientific environment**, select only **SQDMetal**, keep **Automatic official GitHub source** (default), and approve the third-party source/dependency download. SQE resolves one exact Git SHA from `sqdlab/SQDMetal`, downloads the ZIP by that SHA from official GitHub HTTPS, validates paths and the archive, and saves the commit and archive SHA-256 in `%LOCALAPPDATA%/SQE-Studio/sources/sqdmetal/`. A repeat installation reuses the same verified bytes; upgrading requires explicitly selecting **Update saved official Git revision**. An extracted local source remains optional for advanced/offline use. There is no automatic download on normal app launch. A Git commit and its ZIP hash establish reproducible provenance, **not a security audit**, native API compatibility, or EM scientific qualification. See [Windows setup](docs/WINDOWS_WORKSTATION_SETUP.md).
