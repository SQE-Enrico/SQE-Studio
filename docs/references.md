# Sources and licenses

Official documentation was checked while authoring this repository (26 October 2026). The repository contains original integration code; it does not bundle upstream software, proprietary solver dependencies or private project correspondence.

| Source | Role |
|---|---|
| [QPDK documentation](https://gdsfactory.github.io/quantum-rf-pdk/) and [source](https://github.com/gdsfactory/quantum-rf-pdk) | Open quantum PDK and transmon PCell; MIT |
| [GDSFactory](https://gdsfactory.github.io/gdsfactory/) | Parametric layout/hierarchy/GDS export; MIT |
| [Gmsh manual](https://gmsh.info/doc/texinfo/gmsh.html) | OCC fragmentation, physical groups and conformal meshing; GPL-2.0-or-later with upstream exceptions |
| [Palace](https://awslabs.github.io/palace/stable/) and [source](https://github.com/awslabs/palace) | Open electrostatic and Maxwell solvers; Apache-2.0 |
| [Palace configuration reference](https://awslabs.github.io/palace/stable/config/reference/) | Boundary, material, port and solver settings |
| [Palace problem types](https://awslabs.github.io/palace/stable/guide/problem/) | Maxwell matrix and eigenmode output conventions |
| [scqubits Transmon](https://scqubits.readthedocs.io/en/latest/guide/qubits/transmon.html) | Charge-basis quantum model; BSD-3-Clause |
| [QuTiP master equation solver](https://qutip.readthedocs.io/en/stable/guide/dynamics/dynamics-master.html) | Optional Lindblad dynamics cross-check; BSD-3-Clause |
| [KLayout](https://www.klayout.de/doc/) | GDS viewing, Python geometry and DRC; GPL-2.0-or-later |
| [NumPy](https://numpy.org/doc/) / [SciPy](https://docs.scipy.org/doc/scipy/) / [Matplotlib](https://matplotlib.org/stable/) | Core open scientific computing and plots |

QPDK also advertises optional commercial integrations. This repository uses its open Python APIs only and has no dependency on GDSFactory+, HFSS, COMSOL, Sonnet or a commercial license.

Scientific background:

- J. Koch et al., *Charge-insensitive qubit design derived from the Cooper pair box*, Physical Review A 76, 042319 (2007), [doi:10.1103/PhysRevA.76.042319](https://doi.org/10.1103/PhysRevA.76.042319).
- P. Krantz et al., *A Quantum Engineer's Guide to Superconducting Qubits*, Applied Physics Reviews 6, 021318 (2019), [arXiv:1904.06560](https://arxiv.org/abs/1904.06560).
- P. Groszkowski and J. Koch, *scqubits: a Python package for superconducting qubits*, Quantum 5, 583 (2021), [arXiv:2107.08552](https://arxiv.org/abs/2107.08552).
- Z. K. Minev et al., *Energy-participation quantization of Josephson circuits*, npj Quantum Information 7, 131 (2021), [doi:10.1038/s41534-021-00461-8](https://doi.org/10.1038/s41534-021-00461-8).

Check upstream LICENSE files for the precise terms of each installed version and its transitive/native dependencies. The Apache-2.0 license of this repository does not relicense those tools. Record citations appropriate to the actual tools and physical models used in publications.

Application references added for SQE Studio v0.3:

- [Python WSGI reference](https://docs.python.org/3/library/wsgiref.html) and [SQLite interface](https://docs.python.org/3/library/sqlite3.html): application integration and transactions.
- [Python hashlib](https://docs.python.org/3/library/hashlib.html): password-key derivation and integrity hashes.
- [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): PBKDF2-HMAC-SHA256 work factor.
- [Gunicorn deployment guidance](https://gunicorn.org/deploy/): WSGI behind a reverse proxy.
- [Gunicorn application factories](https://gunicorn.org/run/): creating the WSGI application in each web worker.
- [Caddy request-body limits](https://caddyserver.com/docs/caddyfile/directives/request_body): configurable proxy upload limit.
- [SQLite WAL documentation](https://www.sqlite.org/wal.html): local-disk and single-host concurrency constraints.

The application UI uses original static HTML/CSS/JavaScript and no CDN-hosted UI framework. Enabling trusted Python macros is an administrative capability, not a claim of sandboxed execution.
