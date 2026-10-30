# A07 delivery report — unified quantum EDA interface

**Agent:** A07 (independent implementation delta; not the final integrator)  
**Foundation:** user-provided, untouched `SQE-Studio-product-foundation-CLEAN(7).zip`  
**Verified ZIP SHA-256:** `27fd2ec0cec6c8cbc67e21a180fe90ffa0465532fe7cc534d4a1a09b364b4e07`  
**Foundation tree:** `4a3d24b0d43ab5a6bec18f21276db1c21f904fe09a7c6bfc193d870a20998a9c`  
**Frozen contract digest:** `6ffd28ebea3dcfa815a61c22598733520055d8e2b902c1e7ec5ffd5255f74171`  
**Source scope:** `src/sqe_studio/web/`, `tests/ui/`, this report. No frozen/shared/other-agent changes.

## Implemented

- One dark workspace (not a second app), icon shortcuts, readable project and immutable-revision chrome, a 7-stage navigation, contextual inspector and progressive Guided/Expert editing of the same schema.
- SVG schematic connectivity canvas from declared nodes/elements, and a Quantum Metal placement-intent canvas using chip size and coordinates. Accessible keyboard-selectable graph objects expose their original model fields. These visualizations **do not** render a native QDesign, assert netlist electrical equivalence, or generate CAD geometry.
- GDS runs require a supported native-installed port, an explicitly prepared/saved study, a saved current revision, nonempty reviewed primitive list, valid dimensions, and in-chip placement centers. SQDMetal/Palace and Julia ports remain blocked; scqubits is only callable with a saved explicit study when installed. No automatic cross-engine conversions or implicit save+run.
- Native result UI requires a matching revision/study/engine manifest. Only authentic `scqubits.eigenvals` JSON is eligible for a spectrum chart, with exact values also in a table. Failed/timeout/incomplete jobs explicitly have no result; the user can download the server's actual diagnostic ZIP (when finished).
- Modal focus trapping, Escape/focus return, keyboard stage shortcuts `Alt+1` through `Alt+7`, accessible focus outlines, skip link, semantic labels/statuses, reduced-motion stylesheet, no external assets, and responsive sidebar/rail/inspector layouts.
- More truthful labels: **Draft saved ≠ scientific qualification**; QDesign recipe intent is not an executed native QDesign; fabrication remains **HOLD**, never silently Ready.

## Versioned inputs and environment

- Python 3.13.5; pytest environment from host (pytest version recorded by test log if queried); Linux 6.18.55 x86_64.
- Node v22.16.0 for `node --check`; Chromium 144.0.7559.96, Python Playwright 1.57.0.
- Real loopback HTTP `make_server` on OS-selected 127.0.0.1 port. Fresh ephemeral SQLite/identity per test; no imported legacy data. Test account/password are synthetic local-only fixtures; no user account data was used.
- Native packages absent: `qiskit_metal`, `SQDMetal`, `gmsh`, `scqubits` are **not installed**. Julia/Palace native execution unavailable/blocked. No native successful spectrum, GDS, Palace S-parameters, Josephson model, DRC, LVS or foundry signoff was generated or inspected.

## Test evidence (raw output in delta)

- Main `logs/A07-tests.log` is unmodified stdout/stderr from final `node --check` and `PYTHONPATH=src pytest -q -s` command group; actual recorded **exit code 0**. Suite outcome: **14 passed, 2 skipped**, 2 baseline Python 3.13 `load_module` deprecation warnings.
- Browser harness is real Chromium Playwright over local HTTP; two browser tests were **skipped**, not passed, because the host-managed `/etc/chromium/policies/managed/000_policy_merge.json` applies `URLBlocklist: ["*"]`. A prior unskipped attempt produced `net::ERR_BLOCKED_BY_ADMINISTRATOR` for localhost; original raw failed attempt is preserved in `playwright-initial-blocked.raw.log` (actual exit status 1).
- The independent **real local-HTTP** acceptance test passed: unauthenticated rejection, first-run account setup, session/CSRF, project creation, immutable revision, conflict 409, native EM job submitted to real worker, real `EngineBlocked` failure, result 404, downloaded ZIP verified to include `output/FAILURE.json` and `engine.log` but **not** `RESULT_MANIFEST.json`, and logout invalidation. Worker message: `SQDMetal/Palace requires reviewed mesh, 3D stack, boundary conditions, ports, materials and a QDesign mapping. A03 owns this native bridge. No EM solver was started.`
- Pure static accessibility checks verify semantic landmarks, keyboard/focus-handler presence and 9 tested WCAG-style foreground/background palette ratios between **6.85:1 and 17.17:1**; these do **not** prove real-world pixel overlays or browser keyboard semantics.
- No Playwright screenshot could be produced on this host at **1366×768, 1920×1080 or compact (430×820)**. No screenshot is claimed or packaged. Browser viewport, keyboard/focus operation, horizontal overflow and rendered white-on-white-text visual QA remain **BLOCKED**, pending an unrestricted browser (Windows 11 recommended).

## Remaining qualification gates

1. Run `PYTHONPATH=src pytest -q -s tests/ui/test_browser.py` on an approved host where Chromium/Edge accepts loopback HTTP, and inspect the real screenshots collected under `reports/agents/A07/screenshots/`. Test code includes authentication, editing, saving, engine health, failed native worker diagnostic download, keyboard/focus/dialog, inspector and three viewport assertions. The tests are provided but unexecuted end-to-end here.
2. Independently review contrast and SVG focus semantics in Edge/Chromium on Windows 11 and with screen readers at 100%/125% scaling; static color ratios alone are insufficient. Verify rendering after other agent deltas are merged.
3. Real native engine smoke/results on Windows with installed supported dependencies and reviewed end-to-end inputs remain other agents'/A09's qualification. No fake native outputs may be used to satisfy these gates.
4. Unvalidated SQDMetal/Palace/Josephson paths, EM-to-quantization mapping, fabrication PDK/DRC/LVS/signoff remain closed, as demanded by the frozen contracts.

## Dependencies, limitations and migrations

- **Dependencies:** frozen foundation server/store/jobs and immutable project schema, plus separately installed reviewed scientific engines. No A01–A08 delta was merged. User workflow does not start scientific jobs automatically; manual handoffs are gated by the current foundation's advertised engine `mode === 'native'` and `available` plus revision/study checks.
- **Limitation:** backend currently advertises install availability rather than full dependency/contract smoke evidence. UI distinguishes a limited native port from scientific qualification and blocks explicitly unreviewed ports. A09 should consider a *future versioned engine-readiness contract* with `installed`, `input_contract_validated`, `native_smoke_verified`, `block_reasons`, `allowed_study_kinds`; A07 did not change frozen contracts or pretend that such a field already exists.
- **Limitation:** failure specifics are currently inside the authenticated diagnostic ZIP, not a typed failure API response; any future endpoint change belongs to the relevant backend owners and A09's migration review.
- **Requested frozen migration in this delta:** **none**. Existing frozen contracts and all other agents' owned files are unchanged.

**Delivery status:** A07 implementation delta with passing non-browser tests; **browser/Windows acceptance blocked, not qualified**. Final cross-agent integration and scientific/fabrication qualification are reserved to A09.
