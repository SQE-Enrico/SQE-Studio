# Native environment

Keep the scientific Python environment that passed the supplied dev78 report.
Open Launch SQE Studio.pyw from a writable extracted directory. The launcher,
workstation_setup.py, solver_setup.py and sqdmetal_source.py retain their existing
engine discovery/reconnection behavior. This refactor adds no runtime dependency.
The local HTTP service binds only127.0.0.1; keep it local.

requirements/ contains the existing engine environment specifications. Optional
scqubits remains pinned4.3.1. Quantum Metal, SQDMetal/Gmsh/Palace and
JosephsonCircuits.jl continue through their existing native adapters. Palace
runtime paths/WSL settings are deployment configuration, never user-study shell
commands. Missing or incompatible native tools must remain BLOCKED.

The installed wheel contains the complete UI module manifest and modules; no
Node, npm or browser build step is needed to launch the application. Node is
only used by optional local VM tests. Playwright is required for real browser
tests. Use Troubleshoot SQE Studio.cmd for the existing startup diagnostics.

The clean ZIP excludes user workspaces, accounts, credentials and databases.
Extract into a new folder; keep any existing studio-data directory separately
until you have verified the new application. Existing project/HTTP contracts
and frozen numerical/core files are preserved by this release.
