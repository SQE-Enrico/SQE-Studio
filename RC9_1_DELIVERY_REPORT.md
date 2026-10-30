# SQE Studio RC9.1: Julia report crash / Palace 0.16.x identity hotfix

**Build:** 0.1.1.dev10; **Status:** EXPERIMENTAL — NOT RELEASE CANDIDATE.

## Windows field evidence

- The user's RC9 Comprehensive qualification reached real Julia and JosephsonCircuits.jl execution and package discovery (PASS).
- The run then crashed while writing ZIP evidence: `AttributeError: 'str' object has no attribute 'with_name'`.
- Palace was configured using its real absolute Spack/WSL2 Linux path, but the version handshake failed.

## Confirmed causes and modifications

1. `qualification.py` reused `output` for the Julia subprocess output, replacing the report destination `Path` with a string. Replaced with `probe_output`, retaining the original report target. Regression test checks ZIP production after a positive Julia probe.
2. Palace 0.16.0's published CLI wrapper does not support `--version` but does support `--help`. If explicit `--version` is not a validated version response, the Palace readiness check now accepts only the official `Usage: palace [OPTIONS] CONFIG_FILE` and `Wrapper for launching Palace using MPI` help signature, plus the existing executable/path checks. The evidence contains `identity_probe`, `version`, and `version_verified` and records unreported versions truthfully.
3. Qualification gates describe the precise scope of the CLI identity check, not a native EM solution or scientific validation.

**Palace source:** https://github.com/awslabs/palace/blob/v0.16.0/scripts/palace

## Local test outcomes

- Full software regression: **286 passed, 14 skipped, 0 failed** (local Linux; not Windows native Palace).
- Focused qualification/source-inventory/solver-setup regression: **22 passed**.
- Evolved source inventory: `168f9a5f2a318e08816b30003ab92d55febc5ec3320fd68b802a9ba0bb15b149`; frozen contracts unchanged.
- Two deterministic wheel builds (SOURCE_DATE_EPOCH=1700000000) matched byte-for-byte.
- Installed wheel 0.1.1.dev10 imported correctly from an isolated environment.
- The real WSL/Palace executable, scientific EM solve and browser on the user's Windows 11 were **not** executed here.

## Laptop installation / operator acceptance

1. Preserve the prior RC9 directory and current Python 3.11 / Julia / Spack installations; do not reinstall solvers.
2. Extract this complete ZIP to a new directory. Start `Launch SQE Studio.pyw`. Reconnect the existing scientific Python runtime if required.
3. Keep the existing external Palace setting: **Palace in WSL2**, absolute Linux executable `/home/enrico/.sqe/spack/.../bin/palace`; default distro blank or actual WSL distro name. SQE keeps the settings outside the source archive.
4. Run `Qualify this laptop > Comprehensive`, and upload the generated ZIP evidence after reviewing its contents for private paths.
5. Expect `native_palace_runtime` PASS only if the executable's official CLI responds; a help-based PASS will state `version_verified=false`. The full native EM design loop, EPR/quantum bridge, geometry optimization and foundry gates remain BLOCKED until separately qualified.

Never infer EDA Release Candidate readiness from solver availability alone.
