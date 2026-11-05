# Automatic Test and local checks

From the enclosing Git workspace, `.\dev.ps1` runs local development checks.
`.\dev.ps1 -Watch` repeats Recommended after saves. The summary is
qualification-reports/local-latest.json; the numbered ZIP is the immutable
Automatic Test evidence. Exit 0 requires all selected tasks to pass on stable
source; exit 1 means failure and exit 2 means blocked or incomplete.

The same profiles are available in the application's **Automatic Test** menu.
Choose the relevant family. Click **Automatic Test** once and retain the original
numbered report, for example `SQE-RC14_12-report-0001.zip`.

| Profile | Use | Evidence |
|---|---|---|
| Recommended / Quick | Routine code, HTTP and provenance changes | Focused software and HTTP |
| Software | Before integration | All portable domains, real browser and isolated wheel |
| Single transmon | Native isolated-transmon integration | Official Palace benchmark, saved EM-to-spectrum jobs, real browser and rejection checks |
| Extraction | Conditional extraction contracts | Declared EM fixture plus native scqubits |
| Quantum | Quantum models and basis stability | Native scqubits and reference comparisons |
| CAD | Quantum Metal recipes and GDS | Native geometry |
| Fields / Field compare | Field readers and comparisons | Explicit VTK fixtures |
| EM / Convergence | Electromagnetic simulation changes | Native Palace solve |
| RF | JosephsonCircuits.jl integration | Native Julia |
| Milestone | Broad validation when needed | Selected families with explicit exclusions |

`.\dev.ps1 -Profile single_transmon` requires the configured native toolchain
and Chromium. It verifies the pinned sphere example, creates a fresh private
test project and submits genuine jobs through authenticated HTTP and the UI.
It checks source lineage, charge-basis stability, declared additional C_J
sensitivity and rejection of CSRF, revision, unit and artifact errors.
Its nested native-evidence.zip retains the reference inputs, original manifests,
solver files, immutable models and screenshot. It excludes accounts, credentials
and user projects. These raw reference files stay in local reports.

Missing selected tools remain BLOCKED; excluded tasks are SKIPPED_BY_PLAN.
The global budget is 3600 seconds with 120 seconds reserved for reporting and
one native task at a time. Software PASS does not establish EM or device accuracy.

Focused commands from SQE-Studio/:

```bash
python -m unittest discover -s tests/core -p 'test_current_*.py'
python -m pytest -q tests/extraction/test_native_capacitance_identity.py
python -m unittest discover -s tests/extraction -p test_conditional_transmon.py
node scripts/m17_ui_qa.cjs
node scripts/m18_ui_qa.cjs
node scripts/m19_ui_qa.cjs
python scripts/portable_regression.py
```

Node checks execute real UI functions in a VM. Real browser evidence is reported
separately. Injected-provider tests verify contracts and never claim native
physics. Portable suite skips remain visible with their conditional reasons.
