# Development with bounded context

Start with AGENTS.md and CURRENT_STATE.json. Use tools/context.py to locate the
owner. Read one area and the relevant test; use --symbol for a bounded Python
function/method excerpt. rg remains useful for exact strings and call sites.
The tool never imports SQDMetal, scqubits, VTK or other scientific dependencies.
Read source/UI/JSON text with an explicit UTF-8 encoding. For fingerprints,
sort relative POSIX path names explicitly; native Path ordering differs on Windows.

Keep changes within one clear concern when possible. HTTP endpoints belong in
http_api/ resources, not server.py. UI features belong in the relevant web/module;
update web/modules.json only when adding/reordering a source module. Keep shared
state visible in web/app.js. A generated frontend bundle must not be committed.
Native algorithms belong to upstream packages, with explicit version, units,
inputs and artifact provenance at the adapter boundary.

Run the focused checks for the change, then:

From the enclosing Git workspace, `./dev.ps1` automates software fingerprint
refresh, the three Node UI controller groups and Recommended Automatic Test.
`./dev.ps1 -Watch` reruns after saves. On other hosts run `python tools/dev.py`.
Use `--check` / `-Check` to verify existing fingerprints without rewriting them.
See [local automation](AUTOMATION.md) for profiles, reports and exit codes.

```bash
python tools/update_release.py
python tools/verify_release_source.py .
python tools/science_first_gate.py .
```

The refresh tool writes one current software fingerprint and the source inventory.
It cannot update numerical/core pins or claim independent scientific approval.
Source and contract validation remain distinct from a successful numerical test.
Current integration changes are recorded in config/core_changes.json with exact
baseline/current hashes and the method review in docs/SINGLE_TRANSMON.md. The
gate preserves the original baseline map and rejects unreviewed edits even after
fingerprint refresh. Native tests accompany scientific integration changes; this
source review is not independent physics approval.

Keep tests grouped by behavior. Retain meaningful failure, ownership, stale data,
units, numerical-boundary and cleanup checks. Retire only tests for mechanisms
actually removed; report replacements and count changes rather than treating a
smaller suite as progress. After moving code, compare old/new bodies and exercise
HTTP/worker/UI boundaries. Code equivalence does not replace native validation.

For a release, build a fresh wheel, verify every package file against source,
install into an isolated environment and run local HTTP smoke checks. Package
current source, current evidence and concise instructions. Do not nest previous
releases, wheels from older versions, prior logs or chat transcripts in the code.
Use external version control for history when one is available.

Use English for code, documentation, commits, issues and pull requests.
