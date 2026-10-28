# SQE Studio v0.17.0 — Getting Started

**Normal use requires no command-line interaction.** On Windows, extract the ZIP into a new writable directory, then double-click **`WINDOWS-FIRST-START.cmd`**. Your browser opens the local SQE Studio. On first use, create the administrator account through the one-time browser link.

## One workspace, five steps

1. **Project** — Choose a reference workflow, create a design, or import a trusted declarative workflow ZIP.
2. **Setup** — Review automatically detected and smoke-tested engines. First launch starts background installation of supported optional tools. Choose **Install / repair available engines** to retry failed components from the browser.
3. **Run** — Launch the selected workflow, an ordinary Studio analysis, the complete software test suite, or an optional Palace scientific diagnostic profile.
4. **Results** — Examine step states, scientific classification, checks and logs directly in the browser.
5. **Support ZIP** — Download the single report bundle for the selected completed or failed run. Attach the ZIP for debugging; do not manually collect logs.

The detailed device design and process editors are available behind **Advanced editor** in the workspace toolbar. The old experiment and diagnostic URLs are kept for compatibility but are not separate required steps.

## Automatic optional dependencies

The local launcher starts best-effort provisioning **in the background**, without blocking the Web interface. The allowlisted automatic targets are **scqubits, Gmsh, Quantum Metal, SQDMetal and JosephsonCircuits.jl**. Installation and smoke-test results appear under **Setup**, with a downloadable support ZIP for each attempt.

- **scqubits and Gmsh:** installed into the isolated Studio Python environment, then exercised by a small scientific/native API smoke test.
- **Quantum Metal and SQDMetal:** installed into a separate Python 3.11 environment if a Python 3.11 interpreter is available. An existing Python 3.12/3.13 Studio environment is not downgraded. Missing Python 3.11 is flagged with an action in Setup instead of silently installing an outdated interpreter.
- **JosephsonCircuits.jl:** installed into a dedicated Julia project if Julia is installed; Julia itself is a native runtime prerequisite.
- **Palace:** probed but never installed automatically. It needs a qualified native or WSL build, solver configuration and physical validation.

A smoke-test pass shows that an import or small API operation works. It **does not** qualify FEM accuracy, Quantum Metal layout equivalence, SQDMetal extraction, nonlinear harmonic balance or fabrication readiness. Internet access and package-index policy can prevent installation; these failures are visible and reportable without command-line work.

## Troubleshooting and privacy

Every experiment, Studio job, diagnostics run and dependency setup attempt has a **Support ZIP**. The archive contains available inputs, state, logs, checksums and scientific-status warnings. ZIPs stay local until explicitly downloaded. **Review files before sharing**, because logs and project snapshots may include design details.

If the Web application cannot launch, double-click `WINDOWS-DIAGNOSTICS.cmd` as the offline fallback. To upgrade, back up `studio-data` and test the new release from a new folder; the release archive deliberately excludes private workspace data and installed virtual environments.

See [Unified Web Workflow](docs/unified-web-workflow.md), [Detailed science limitations](docs/ecosystem-workflow.md), and [Windows diagnostics](docs/diagnostics-windows.md).
