# SQE Studio — integrated superconducting and microwave EDA

SQE Studio is an **experimental graphical environment for design → native simulation → physical interpretation → design improvement**. Its scope includes superconducting QPUs, resonators, readout components, fluxonium, microwave networks and Josephson RF circuits. **It is not an experiment registry** and examples do not have separate execution paths. The long-term competitive reference is the integrated QuantumPro-class EDA workflow, **not a claim of product parity**.

**Release status:** experimental, **not scientifically qualified**, not a standalone signed installer and not foundry approved. Local software tests do not establish solver accuracy or measured-device performance.

## Open the application (no command line for normal design work)

On Windows with Python and Tkinter already installed, extract the archive and double-click **`Launch SQE Studio.pyw`**. The desktop launcher starts a **localhost-only** authenticated web interface and opens a browser. Use its one-time local setup token to register and then sign in. Close the launcher to stop the service. This is a Python-based desktop launcher, not a compiled Windows application; click **Prepare scientific environment** for an optional, consent-based Python 3.11 sidecar installation (build/test tools, scqubits, Quantum Metal, Gmsh, and browser tests). SQDMetal/Palace and Julia still require separately reviewed native setup; no automatic Windows Palace installation is claimed. No cross-platform installer is qualified.

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
