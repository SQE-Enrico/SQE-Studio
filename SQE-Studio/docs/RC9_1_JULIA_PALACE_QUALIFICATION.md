# RC9.1 Windows qualification hotfix (0.1.1.dev10)

**Engineering status: EXPERIMENTAL, not a release candidate.** This change does not qualify EM calculations.

## Field trigger

On Windows 11, a Comprehensive qualification with a working Julia package was able to finish native Julia tests, but the evidence reporter crashed with:

`'str' object has no attribute 'with_name'`

The Julia package probe reused a variable containing the destination `Path` for textual subprocess output. The report saver then attempted to call `Path.with_name` on that text. The probe output has been renamed `probe_output` so the report destination remains a `Path`. A Comprehensive-probe regression test now creates and validates the resulting ZIP.

Separately, Palace 0.16.0 installed under Ubuntu/WSL via Spack can have a wrapper supporting `--help` but not `--version` (as documented at `https://github.com/awslabs/palace/blob/v0.16.0/scripts/palace`). The previous gate required `--version` and could reject a real installed binary. The runtime gate now:

1. Checks that the selected WSL executable is accessible and executable (unchanged).
2. Requests `--version`, accepting only successful recognizable version output.
3. If that is unavailable, requests `--help`, accepting only the official Palace CLI usage and wrapper signature.
4. Records `identity_probe`, `version_verified`, and `version` truthfully. A `--help` acceptance records `version_verified=false` and `version=unreported by CLI`.

The CLI handshake proves only a matching executable wrapper was reached. It does **not** test MPI, Palace's compiled solver dependencies, a mesh, a solution, a converged frequency, or the SQDMetal-to-Palace adapter. These remain distinct qualification gates and cannot be cleared by this hotfix.

## Installation and reporting

Install this complete source package in a new folder. Keep the Python 3.11 and Julia/Spack installations intact. In the desktop solver setup, select **Palace in WSL2**, and keep the absolute Linux Palace path and WSL distribution entered previously; settings are stored outside the source archive. Use **Reconnect existing scientific environment** if the new source folder needs binding to the existing Python environment.

Run **Qualify this laptop > Comprehensive** again. The generated ZIP should contain `QUALIFICATION.json`, `SUMMARY.md`, `INTEGRITY.json`, and `logs/native_palace_runtime.txt`, plus logs for the other gates. If the Palace CLI only exposes help, expect identity `PASS` with version unverified; the native EM design loop stays `BLOCKED` pending physically reviewed solver execution and convergence.

## Local verification

- Full pytest: 286 passed, 14 skipped, zero failed (Linux host, not the user's Windows machine).
- Targeted qualification and solver-setup regression: 22 passed.
- Source inventory verified with frozen contracts unchanged.
- Windows/WSL native Palace 0.16.0 and native Julia installation remain to be verified on the operator's laptop.
