# RC12.3 — Windows qualification test stabilization

Status: **experimental; not a release candidate**.

The Windows 11 RC12.2 qualification archive dated 2026-10-30 (14:55 local) reported two failed tests out of 323 executed/skipped tests (314 passed, 2 failed, 7 skipped). The native Quantum Metal, SQDMetal import, Gmsh import, Palace CLI, scqubits and JosephsonCircuits checks passed their defined gates, but no native mesh/Palace solve was executed.

## Changes

- `tests/test_sqdmetal_official_source.py`: the simulated Windows ZIP normalization scenario uses the public `ZipFile.infolist()` / `ZipInfo.filename` / `ZipInfo.orig_filename` fields instead of private `zipfile._sanitize_filename`, which does not exist on the reporter's Python 3.11 installation. The original path remains mandatory and `sqdmetal_source._check_zip()` still rejects unsafe raw member names.
- `tests/security/test_hardening.py`: one adversarial HTTP request that MUST receive 403 now tolerates up to two transient `ConnectionAbortedError` events, **provided no project was created**. It requires an actual 403 response on an eventual attempt; exhausting attempts, observing a non-403 response, or detecting any mutation is a test failure. Other CSRF/origin checks remain unchanged.

## No scientific claim

No QDesign geometry, Gmsh mesh, Palace solve, EM eigenfrequency, EPR quantization, geometry optimization or foundry process was newly qualified by this update. The scientific-environment installation is unchanged. Repeat `Qualify this laptop -> Comprehensive` on Windows and share the generated ZIP. If the security test still fails, retain the exact error: additional HTTP/server investigation is required, not an unconditional test waiver.
