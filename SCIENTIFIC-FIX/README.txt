SQE Studio 0.11.0 - Scientific Diagnostics Hotfix v2 (Windows installer fix)

What happened:
- The first hotfix passed ProjectRoot from CMD as a quoted Windows path ending with \.
- PowerShell received a malformed argument, causing GetFullPath to reject the path.
- The error occurred before file modification or backups.

This version:
- Determines the SQE Studio root from the location of apply.ps1, without a command-line path argument.
- Checks the SQE Studio version, required files, and hotfix payload before copying anything.
- Saves copies of all three target files under patch-backups/.
- Copies only files that differ, validates SHA-256 hashes, and runs focused regression tests.
- Rolls back original files on errors, including failed tests.
- Can safely be run again after a successful installation.

Installation:
1. Close SQE Studio with Ctrl+C in the server console.
2. Extract all ZIP contents into your existing SQE-Studio directory beside WINDOWS-FIRST-START.cmd.
3. Overwrite the previous APPLY-SCIENTIFIC-DIAGNOSTICS-FIX.cmd and SCIENTIFIC-FIX/apply.ps1 when asked.
4. Double-click APPLY-SCIENTIFIC-DIAGNOSTICS-FIX.cmd.
5. Restart SQE Studio and run Scientific workflow validation from the browser.
6. Download and review the diagnostic ZIP before sharing it.

This patch changes only:
- src/sqw/diagnostics.py
- scripts/palace-wsl-run.sh
- tests/test_scientific_diagnostics_v011.py

No changes to .venv, studio-data, projects, Spack, Ubuntu or Palace.

The patch fixes Windows CRLF probe parsing and the acceptance of driven-1.json and driven-2.json.
Passing regression tests does NOT constitute FEM solver qualification.
