# SQE Studio

Local quantum EDA platform with native scientific engines, immutable project
revisions and verified result provenance. The Python project and technical
documentation are in [SQE-Studio](SQE-Studio/README.md).

## Development and tests

Run from the repository root:

~~~powershell
./dev.ps1 -Doctor
./dev.ps1 -Watch
~~~

The watcher runs Recommended after saves. Stop it with Ctrl+C before running
the full suite with ./dev.ps1 -Profile software.

The native single-transmon workflow uses ./dev.ps1 -Profile single_transmon.
It requires the configured scientific workstation and a real Palace backend;
see the [workflow and scientific scope](SQE-Studio/docs/SINGLE_TRANSMON.md).

Changes follow [issues and milestones](.github/ROADMAP.md), a feature branch
and a linked pull request. [GitHub Actions](https://github.com/SQE-Enrico/SQE-Studio/actions)
runs checks on pushes and PRs and retains readable summaries and downloadable
reports. The [development protocol](.github/DEVELOPMENT.md) defines this cycle.

The [verified local baseline](.github/evidence/local-baseline.json) records its
report checksum, environment, counts and exclusions. Software checks, native
execution, numerical convergence and physical qualification remain distinct.

Scientific qualification NOT_ESTABLISHED; fabrication HOLD.
