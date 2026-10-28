# SQE Studio v0.16.0 — Web-first multi-engine release

## User-facing change

Routine tests, sample experiments, research debugging and support-report ZIP
downloads are all accessible through a browser. On Windows, users double-click
`WINDOWS-FIRST-START.cmd` and sign in. No interactive command prompt is needed.

- `/`: project Studio and downloadable per-job support ZIPs.
- `/experiments.html`: multi-engine example/custom ZIP project workflows, logs,
  result states, opt-in external execution, and one-click ZIP exports.
- `/control.html`: regression and Palace scientific diagnostics with ZIPs,
  including a minimal report on unexpected diagnostic failure.

## Data and science

- The generic backend framework from v0.15.0 is retained, including optional
  Quantum Metal, SQDMetal, scqubits and JosephsonCircuits.jl adapters.
- SHA-256 checks verify archived files, not scientific accuracy.
- Existing Palace tests and research fixtures remain unchanged.
- External solver configurations, mesh validation, numerical equivalence and
  independent measurement comparisons still require workstation qualification.

## Trust and scope

Native experimentation is disabled for remotely deployed Studio servers. Only
the local authenticated administrator can import projects or start external
execution. User-uploaded ZIP files cannot contain executable Python code.
Bundled, trusted Python factories and external solver execution require
separate explicit opt-ins. Support ZIPs are not uploaded automatically and
should be reviewed before sharing.

Refer to `docs/web-first-experiments.md` for usage and bundle contents.
