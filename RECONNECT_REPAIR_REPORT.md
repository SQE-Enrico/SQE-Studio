# SQE Studio: managed environment reconnection repair

**Status: EXPERIMENTAL — not a release candidate.**

## Diagnosis from user-provided report (2026-10-30)

- The evidence ZIP passed its embedded file-hash verification.
- 1 PASS, 1 FAIL, 14 BLOCKED; active interpreter still Python 3.15.1.
- The source inventory failed, but the old verifier does not identify changed filenames.
- Python 3.11 and installed packages were not visible in the *active runtime*.
- No `launcher-errors.log` is expected when the launcher silently selects the original Python because a source-folder-specific environment is not found. A missing log is not proof that installation succeeded or failed.

## Corrected behavior

- The desktop launcher displays the active Python and available managed-environment count.
- **Reconnect existing scientific environment** discovers user-local Python 3.11 environments using read-only marker checks.
- User explicitly selects the environment; SQE checks the executable runs Python 3.11 x64 and writes a local *binding*, without moving the venv, reinstalling packages or editing its marker.
- Relaunch SQE to activate the linked interpreter. The existing startup fallback is still retained.
- Comprehensive qualification now reports ready/incomplete managed-environment counts (no folder names or hash IDs in the shared report).
- Source integrity mismatch reports relative added, missing and modified source paths, with no auto-repair.

## No-terminal Windows procedure

1. Make a backup of the existing `SQE-Studio` **source folder**; leave the scientific environment under `%LOCALAPPDATA%` untouched.
2. Unpack the **complete** corrected ZIP into an empty folder. Open `SQE-Studio/Launch SQE Studio.pyw` with a double-click.
3. If the window displays Python 3.15, click **Reconnect existing scientific environment**. Choose the ready environment, confirm, then close and reopen SQE.
4. If no ready environment is found, **do not reinstall everything**: select **Prepare scientific environment** to inspect the setup state and generate a new Comprehensive report.
5. Run **Qualify this laptop → Comprehensive** and share that new ZIP. The new `SUMMARY.md` and `QUALIFICATION.json` show environment readiness; `logs/source_integrity.txt` identifies any source mismatch.

The overlay is useful only when the current installation is known to match the previous complete recovery ZIP. Because the user's inventory was already failing, a **clean, complete extraction is recommended**.

## Verification and scope

257 automated tests passed, 11 native-conditional tests skipped; one sporadic test-harness HTTP connection-close error occurred on an earlier run and did not reproduce. Two equal-epoch wheels were byte-identical. The current wheel installed and imported in an isolated environment. Windows reconnection, Chromium, QDesign, Gmsh/Palace, scqubits and Julia native calculations were **not** demonstrated here. Frozen contracts remain unchanged.
