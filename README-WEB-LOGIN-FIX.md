# SQE Studio 0.10.0 — First Login Hotfix

The first administrator login succeeds (HTTP 200), but the dashboard load fails on `GET /api/template` with HTTP 500 / `UnboundLocalError: document`. A duplicate `from .process import document` inside `Application.__call__` shadows the module-level import for all requests. This hotfix removes the redundant local import. It also changes the Windows launcher Shapely version check to avoid quoting errors in PowerShell.

## Apply without the command line

1. Close the SQE Studio server window with **Ctrl+C**.
2. Extract the contents of this ZIP **inside the existing SQE Studio folder**, next to `WINDOWS-FIRST-START.cmd`. Keep the `WEB-LOGIN-FIX` subfolder intact.
3. Double-click **`APPLY-WEB-LOGIN-FIX.cmd`**. This validates source hashes, backs up changed files, and runs four regression tests using the existing virtual environment. No Python dependencies are reinstalled, and `studio-data` is not touched.
4. Double-click **`WINDOWS-FIRST-START.cmd`** again. Sign in with the administrator account you already created. Do not repeat administrator setup.
5. Verify that the dashboard opens and `System & Diagnostics` can be accessed.

If the patch refuses to apply because of unexpected local edits, do not force replacement. Share the error message for a targeted fix. Backup files (if changes were needed) are placed under `hotfix-backups/`.

## Tested / not tested

Automated WSGI endpoint tests cover authenticated `/api/projects`, `/api/macros`, `/api/template`, `/api/capabilities`, the parametric QPU preset, and unauthenticated template access. The source also passed the existing Studio API and startup scientific smoke tests on Linux. PowerShell installer behavior and Windows GUI remain to be checked on the target machine.
