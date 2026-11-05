# SQE Studio — start here

Read this file and CURRENT_STATE.json. Do not load the whole repository.
Run `python tools/context.py` to list areas; then `python tools/context.py http`
or the relevant area. Read individual symbols with
`python tools/context.py --symbol sqe_studio.http_api.extraction:extract`.
PROJECT_MAP.json is the routing index, not an additional document to read in full.

## Boundaries

- server.py is the stable entry; HTTP resources live in http_api/.
- web/app.js holds shared state/helpers; web/modules/ contains UI concerns.
  web/modules.json fixes the order. web_assets.py serves one /app.js response.
  Edit the owning module; never keep a second generated JS bundle.
- adapters/ integrates native packages; interop/ validates scientific provenance.
- jobs.py/worker.py/orchestration/ own immutable jobs, artifacts and cancellation.
- testing/ owns Automatic Test; tests/ is grouped by domain, not agent numbers.
- docs/ has current architecture, development, testing, science and setup only.
  Deleted historical approvals/source copies are not runtime dependencies.

## Work cycle

1. Identify the owning area and its focused tests before editing.
2. Reuse upstream SQDMetal/Palace, Quantum Metal, scqubits and JosephsonCircuits.
   Do not write another solver, diagonalizer, Hamiltonian or geometry matcher.
3. Keep HTTP auth/CSRF/ACL, immutable revisions, source hashes and explicit units.
4. Validate changed boundaries and refresh with `python tools/update_release.py`.
   This updates current software fingerprints, never scientific approval.
5. Select the relevant Automatic Test profile and state which report is needed.
   Missing native tools remain BLOCKED; label fixture/provider/VM checks honestly.
6. Keep CURRENT_STATE.json short: current facts, blockers and next work.
   Replace obsolete instructions; do not append a chronology.

The original dev78 core map stays immutable in config/core_hashes.json.
Current integration changes are separately recorded in config/core_changes.json
and docs/SINGLE_TRANSMON.md, with exact source hashes, primary references and
meaningful native validation. Do not relax physical validation or change a pin
merely to pass tests. Fingerprint refresh alone cannot authorize a core change.
No fabricated reviewer or physical GO. Scientific qualification NOT_ESTABLISHED;
fabrication HOLD. See docs/SCIENCE.md for the remaining extraction/EPR work.
