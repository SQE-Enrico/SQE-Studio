# A06 delivery report — immutable foundation, orchestration delta

**Scope:** implementation agent A06 only; not a final integrator or product release. Status: **core orchestration tests passed; full scientific/native and Windows acceptance blocked/unqualified**.

## Authorized input and exact identity

- Uploaded foundation archive logical name: `SQE-Studio-product-foundation-CLEAN.zip` (received on disk as `SQE-Studio-product-foundation-CLEAN(5).zip`).
- Observed raw archive SHA-256: `27fd2ec0cec6c8cbc67e21a180fe90ffa0465532fe7cc534d4a1a09b364b4e07` — **exact match**.
- `FOUNDATION_LOCK.json` tree SHA-256: `4a3d24b0d43ab5a6bec18f21276db1c21f904fe09a7c6bfc193d870a20998a9c` — **verified with baseline `tools/delta.py verify`**.
- Frozen contract SHA-256: `6ffd28ebea3dcfa815a61c22598733520055d8e2b902c1e7ec5ffd5255f74171` — **verified, unchanged**.
- No historical archives or unowned source files were integrated; pristine `base/SQE-Studio` was retained for delta admission.

## Runtime and evidence

- Observed environment: Linux x86-64 container; CPython **3.13.5**, pytest **9.0.2**. Project `pyproject.toml` targets Python >=3.11; Windows 11 and Python 3.11 were **not** run here.
- External scientific module and distribution probes: `scqubits` absent; `qiskit_metal` / `quantum-metal` absent; `SQDMetal` absent; `gmsh` absent. No independently accepted Palace native executable or Julia JosephsonCircuits.jl installation is available in this environment.
- Actual suite invoked with `PYTHONPATH=src python -m pytest -q`; final raw stdout/stderr and exit code are in the delta `logs/A06-tests.log` and `DELTA_MANIFEST.json`. The tests include foundation domain/security/UI/delta tests and the new `tests/orchestration/` suite.
- At development preflight, tests initially could not import the local package without `PYTHONPATH=src`. A subsequent preflight revealed an expected compatibility assertion and a sweep code typo; both were resolved in A06-owned files. Final tests must be judged by the raw final run log, not by this narrative.

## Implemented and covered

| Area | Observed evidence | Integrity boundary |
|---|---|---|
| DAG | Graph orders dependencies; rejects missing, mismatched and older-revision artifacts; refuses unreviewed conversions and unknown capabilities; detects cycles. | No downstream numerical conversion started automatically. |
| Artifact provenance | Every listed native file is hash-verified; declared engine/revision/study/type/source/cache data checked; tampering and invalid paths rejected. | Valid manifest is NOT scientific qualification. |
| Cache | Content fingerprint covers revision, source project SHA-256, study options, native engine version, adapter source and upstream manifest hashes. Exact current verified results only. | Stale historical output never validates a new revision. |
| Lifecycle | Thread-safe active-job registry, exclusive workspace lock, fixed subprocess command, cancellation, 180 s timeout, retries capped at 3 attempts, progress, bounded ZIP. | Native OS child-tree cleanup on Windows needs independent verification. |
| Iteration | Numeric-only manual and automatic sweep planning, 24-point cap and 600 s overall wall clock. Native execution serial; failure stops further points. | No optimizer or invented solver convergence. |
| Partial failures | Per-point result manifest, audit log, point and option digests; `partial_failed` retains verified earlier points, no synthetic results. | Completed points require independent physical review. |
| Real-engine absence | Actual Josephson adapter subprocess test returns a failed run and `FAILURE.json`, with **no** `RESULT_MANIFEST.json`. | No fixture substituted for native-engine acceptance. |

Test fixtures for lifecycle/provenance are synthetic byte files labeled `TEST-FIXTURE-ONLY` and `NOT PHYSICS`; their only purpose is checking immutable manifests, scheduling and cache logic. They do **not** demonstrate installed scqubits, Quantum Metal, Palace or Julia execution. End-to-end native acceptance, eigenmodes, S-parameters, EM-to-quantum extraction, QGDS signoff, measurement comparison, numerical convergence and mask qualification remain **blocked / not qualified**.

## Dependencies and explicit interface requests

1. **A01:** define a versioned `ArtifactReference`/`ArtifactManifest` ABI with content/manifest hashes, units, port/geometry identities, transformations, engine version, source revision/digest, and authenticated reviewer evidence bound to all exact parents. Provide a trusted verification path for reviewed quantization/netlist conversions. Until then, `Jobs.start(parents=...)` **fails closed**. DAG capabilities are trusted integration declarations only, never accepted from a study.
2. **A02:** supply a separately persisted QDesign recipe artifact (not merely a GDS export), explicit QDesign ownership/version and recipe-to-GDS provenance with no mask signoff claim.
3. **A03:** supply native QDesign-to-mesh-to-deck-to-EM artifact stages, complete reviewed 3D stack/boundaries/ports and the native Palace version. Current bridge remains blocked.
4. **A04:** preserve explicit scqubits units, basis/truncation and reviewer provenance for extracted Hamiltonian parameters; never infer from geometry automatically.
5. **A05:** provide the native Julia bridge and verified port/netlist convention. Current bridge remains blocked.
6. **A08:** wire CSRF-protected status, cancellation, retry and sweep routes to A06 methods. Update existing result-download routes to recheck completed state and artifact hashes; present stale/unqualified evidence correctly. The existing foundation `server.py` uses raw `RESULT_MANIFEST.json` presence for the `/result` route and must not be mistaken for a verified scientific gate. Review OS process-tree termination and crash recovery on Windows.

## Versioned shared-contract proposal (A09 decision only)

**Proposed `sqe.interoperability.v2` migration; not applied here.** Add immutable canonical `artifact_type`, `content_sha256[]`, `manifest_sha256`, source revision ID/digest, engine/adapter provenance and option fingerprint; typed port/unit/geometry mapping; reviewed transformation ID/evidence with reviewer, review timestamp and exact parent hashes; separate `artifact_integrity_state` from scientific `validation_state`; and a stage/job interface for multiple native output artifacts per adapter invocation. Add API representations for sweep groups/point result refs, cancellation, retries, stale status and log availability. Require cross-agent compatibility tests and a versioned migration of frozen interfaces under A09; **do not silently modify frozen contracts**.

## Known limitations and unclosed acceptance gates

- Stage graph is ready for trusted typed integrations but blocked for native cross-engine transitions; it does not materialize missing A01/A03 stages.
- The source baseline defines no `Store` compare-and-swap run-state transaction and no new HTTP endpoints. A06 serializes transitions within its service and rechecks the project head before dispatch/each sweep point. A08/A09 should review transactional run-state CAS and abandoned run reconciliation on restart.
- The native subprocess is bounded but not a complete OS sandbox. Log caps are polling-based. On Windows, `msvcrt` exclusive file locking is implemented, but worker descendant termination should use a reviewed Windows Job Object implementation if needed.
- `Jobs.status` re-hashes completed native files and checks current source/engine; results are **not** independently qualified even when current. Direct raw baseline HTTP route integration still requires A08 ownership.
- No scientific packages, native solver data, PDK, DRC/LVS, measurements, benchmark references, browser automation or Windows 11 tests were supplied or invented.

**Output:** `A06-delta.zip` only, packed using unchanged foundation `tools/delta.py`, with all changes owned by A06, raw final test log and manifest verified by `tools/delta.py admit`.
