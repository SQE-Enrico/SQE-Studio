# Local execution report

This report records actual workstation execution. It does not claim exhaustive
frontend coverage or QuantumPro parity. Later results replace pending entries.

Environment checked on 2026-11-05: Windows 11 Pro 10.0.26300, x64,
Intel Core Ultra 5 125U (12 cores / 14 logical processors), approximately
31.5 GiB RAM, approximately 182 GiB free on C: at inspection.
The existing managed scientific Python is 3.11.9. Node, Playwright, Chromium,
Quantum Metal, SQDMetal, Gmsh, scqubits, VTK, Julia and WSL are discoverable.
Discovery alone does not establish execution success.

Source starts from `d8cf31085ae0bb2b1a9f06a06b15405e7506f244` on
`codex/2-single-transmon-chain`, with the reviewed feature delta.
Exact source inventories and active core hashes are preserved in the reports
and repository. The original dev78 hash map remains unchanged.

| Actual command / check | Result | Evidence / scope |
|---|---|---|
| `.\\dev.ps1 -Doctor` | PASS discovery | Existing scientific runtime, Node and optional packages found |
| `.\\dev.ps1 -Profile single_transmon` | PASS, stable source, 136.03 s | Report 0011; integrity/targeted/HTTP/native chain, analytic benchmark, real browser, source rejection |
| `.\\dev.ps1 -Profile extraction` | PASS | Report 0012; explicitly separate EM fixture plus genuine scqubits |
| First `.\\dev.ps1 -Profile software` on feature | FAIL | Report 0013; two integration omissions and one Windows loopback abort; Chromium and isolated wheel PASS |
| Focused catalogue/operator-doc/upstream-diagnostic regressions | 14 passed | New starter now registered in catalogue; operator instructions restored; connection abort did not reproduce |
| Full Software after corrections | All five tasks PASS; 1795 tests passed / 24 skipped | Report 0014, 518.88 s; controller returned incomplete because the root agent instructions changed during the run |
| Recommended on current instructions | PASS, stable source | Report 0015; integrity, targeted checks and authenticated HTTP |

Report 0013's failures are preserved. The loopback diagnostic passed both its
isolated rerun and the corrected focused group; no authentication check was
removed and no retry was added to hide that failure.

Report 0014 is not accepted as a stable-source integration pass. The product
tests passed, but the agent instructions changed during execution. The final
integrated source must receive another stable-source Software run.

Actual native chain:

- Official Palace sphere case: maximum relative entry error 3.532% against a
  predeclared 5% analytic tolerance.
- Fresh saved Palace transmon solve and scqubits quantization through real HTTP.
- Real Chromium submits EM, inspects its verified source, enters explicit
  junction assumptions, previews extraction and opens the saved native spectrum.
- Four charge-basis cutoffs pass. Larger additional C_J lowers EC and f01.
- CSRF, revision, geometry, unit, junction convention and artifact guards pass.
- Original native files and screenshot are retained inside report 0011's
  `transmon-chain/native-evidence.zip`. Raw test data is not pushed to GitHub.

The existing Software browser test also executes setup/login, project creation,
seven-stage navigation, health and logout. Its scope is distinct from the native
case. The complete editor/field/export/cancellation/responsive-control inventory
still needs expanded real-browser execution; 100% UI coverage is not claimed.

The native computer-control interface is unavailable in this session.
Playwright and process-level application tests are available. The real Windows
launcher has not yet been interactively exercised in this development increment.

Start the application from the inner project folder with
`python "Launch SQE Studio.pyw"` using the configured runtime, or use the
existing Windows launcher shortcut. Test commands above run from the outer Git
workspace. Reports are under `SQE-Studio/qualification-reports/`.
