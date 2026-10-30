# Parallel agent contract

## Dispatch

Give each agent the **same exact `SQE-Studio-product-foundation.zip`** and its individual `agents/Axx.md`. The initial foundation is immutable. Each works in an isolated copy. Do not distribute intermediate agents' changes. Changes to `contracts/`, `src/sqe_studio/contracts.py`, adapter `registry.py`, `base.py`, `tools/delta.py` or `pyproject.toml` are frozen and require an A09-reviewed migration.

## Delta only — not a full-source ZIP

Every agent returns `Axx-delta.zip` containing `DELTA_MANIFEST.json`, only changed owned files under `files/`, and raw test logs under `logs/`. Include a `reports/agents/Axx/` delivery note with actual test evidence, dependency constraints and unclosed defects. No `studio-data`, compiled binaries, engine caches or fabricated native solver outputs.

## Commands (from the parent of both trees)

```sh
python BASE/SQE-Studio/tools/delta.py verify BASE/SQE-Studio
python BASE/SQE-Studio/tools/delta.py pack BASE/SQE-Studio WORK/SQE-Studio A02 A02-delta.zip --log A02-tests.log --exit-code 0
python BASE/SQE-Studio/tools/delta.py admit BASE/SQE-Studio A02-delta.zip
```

`--exit-code` must be the actual command result from the raw log, **never inferred/changed to pass**. A failed or blocked test needs an honest nonzero status and blocker explanation. The integrator reviews all records. If agent modifies an unowned path, pack must fail. Agent file deletions require explicit preimage hashes.

## Final integrator A09

A09 receives untouched foundation + all eight finished `A01-delta.zip`...`A08-delta.zip`; never merge early. Run `admit`, then `merge --dry-run`, then real `merge`. Reject conflict, missing agents, invalid path/hash, missing test logs, frozen digest mismatch and unsigned runtime outputs. Run full available unit, UI, native engine, Windows packaging, browser-over-local-HTTP and scientific comparison checks. No fixture-only test may be described as live browser acceptance. Any migration of frozen contracts requires versioned review, scoped owners and regressions.

```sh
python BASE/SQE-Studio/tools/delta.py admit BASE/SQE-Studio A01-delta.zip A02-delta.zip A03-delta.zip A04-delta.zip A05-delta.zip A06-delta.zip A07-delta.zip A08-delta.zip
python BASE/SQE-Studio/tools/delta.py merge BASE/SQE-Studio SQE-Studio-integrated.zip A01-delta.zip A02-delta.zip A03-delta.zip A04-delta.zip A05-delta.zip A06-delta.zip A07-delta.zip A08-delta.zip --dry-run
python BASE/SQE-Studio/tools/delta.py merge BASE/SQE-Studio SQE-Studio-integrated.zip A01-delta.zip A02-delta.zip A03-delta.zip A04-delta.zip A05-delta.zip A06-delta.zip A07-delta.zip A08-delta.zip
```

The merged archive is an **integration candidate only** until A09 appends a real qualification report and verifies all required gates.
