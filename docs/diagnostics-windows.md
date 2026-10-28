# Web-first diagnostics and support bundles

## Operating principle

SQE Studio offers **System & Diagnostics** at `/control.html`. Access is restricted to authenticated administrators on a **local loopback development instance**; the endpoint is disabled in remote/production deployment. No commands are accepted from the browser: it selects from fixed allowlisted checks implemented in Python.

## Workflow

1. Start the Web interface with `WINDOWS-FIRST-START.cmd`, then sign in.
2. Open **System & Diagnostics** from the Studio left sidebar or at `http://127.0.0.1:8000/control.html`.
3. Select Standard or Extended and choose **Run checks**. A background task keeps the UI responsive.
4. Inspect the result summary, itemized check codes, warnings and suggestions.
5. Download the support ZIP **only after the run completes**, open and review its contents, then share it intentionally.

The standard mode checks runtime versions, OS resources, installed scientific modules, Julia availability, WSL presence and focused regressions. Extended mode additionally attempts an Ubuntu shell probe, optional JosephsonCircuits.jl import and Gmsh 3D unit-box meshing. A successful meshing test **does not validate a Palace FEM solve or quantum results**.

Diagnostic ZIPs include only `SUMMARY.txt`, `environment.json`, `checks.json`, `test-results.txt`, `README-PRIVACY.txt`, `manifest.json`, and `SHA256SUMS.txt`. No user project directory is crawled, and no automatic network uploads occur. Secret/path scrubbing is best-effort; users must personally review each ZIP before sharing.

Reports persist under the local private `studio-data/diagnostic-reports/` directory, separate from project artifacts. History is limited to 15 runs to control disk use. Interrupted runs are marked as such after a server restart. If history is full, archive previously downloaded reports and ask an administrator to remove old local diagnostic-report folders after backing them up.

## Emergency fallback without a Web server

Double-click `WINDOWS-DIAGNOSTICS.cmd` (optionally with `-Extended`) if installation fails before the browser opens. The PowerShell fallback can create a minimal ZIP even without Python. The Web diagnostic UI is preferred after first successful launch.

## Scientific qualification

Distinguish (1) package import, (2) mesh generation, (3) Palace executing a real FEM problem, (4) convergence against mesh refinement, and (5) agreement with an independent physical benchmark. Only the first two are automatically covered by the current diagnostic page. Scientific FEM benchmark workflows are planned future milestones; do not infer an accuracy certificate from green checks.
