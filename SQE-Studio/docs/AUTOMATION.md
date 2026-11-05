# Automatic local development checks

Use the enclosing Git workspace:

```powershell
.\dev.ps1 -Doctor
.\dev.ps1
.\dev.ps1 -Watch
.\dev.ps1 -Profile software
.\dev.ps1 -Profile single_transmon
```

dev.ps1 selects the scientific environment already associated with this folder,
then falls back to .venv, py -3.11 or python. `-Python <path>` selects an
interpreter explicitly. It installs no packages and changes no system Python.
Doctor reports module availability without claiming that a native solver works.

The default command refreshes software fingerprints, runs three Node controller
groups and Recommended Automatic Test: integrity, focused tests and authenticated
HTTP. Node comes from PATH or the existing Playwright installation.
The refresh preserves the original core map; active integration changes require
their separately checked source review. Refresh cannot authorize a core edit.

Watch runs immediately, batches nearby saves and runs one cycle at a time.
It ignores caches, environments, reports and builds. A save during a test requires
another cycle. Ctrl+C requests a stop after the current bounded task and retains
the report. Watch supports Recommended/Quick and runs only while the terminal
remains open; it is not installed as a service.

From the inner project directory on another host:

```bash
python tools/dev.py --doctor
python tools/dev.py --watch
python tools/dev.py --check --profile software
python tools/dev.py --profile single_transmon
```

The Software profile adds all portable domains, Chromium and an offline wheel
build/install into an isolated environment. Single transmon requires existing
Quantum Metal, SQDMetal, Gmsh, Palace, scqubits 4.3.1 and Playwright/Chromium.
It reuses operator Palace/WSL settings only for the test process. No fallback
matrix or replacement scientific result is generated when a tool is missing.
See [the native case](SINGLE_TRANSMON.md) and [profile details](TESTING.md).

| Exit code | Meaning |
|---|---|
| 0 | UI checks and all selected tasks passed on stable source |
| 1 | Test or refresh failed |
| 2 | Blocked, timed out, incomplete or source changed during the run |
| 130 | Keyboard interruption |

qualification-reports/local-latest.json is the tool summary. Numbered ZIPs are
immutable evidence, including diagnostics on failure. Conditional skips in the
portable suite remain visible and do not prove native execution.

If a separate development environment is needed, install `.[dev,browser]` and
run `python -m playwright install chromium` there. Existing graphical setup
also offers Playwright/Chromium. Test commands perform no dependency downloads.
Install missing tools in the interpreter shown by Doctor.

The repository-root GitHub workflow runs Software on pushes and pull requests:
Windows Python 3.11 and Linux Python 3.11/3.12/3.13. It uses --check to verify
committed fingerprints and preserves reports with a readable job summary.
Native workstation reports are tracked through sanitized evidence metadata;
the hosted matrix does not claim to execute the local Palace/WSL profile.
Git preserves signed source bytes across Windows and Linux.

Use CURRENT_STATE.json for current verified reports and .github/ROADMAP.md in
the enclosing workspace for issue tracking. The next scientific phase is
mesh/domain/material convergence, followed by readout/EPR integration.
