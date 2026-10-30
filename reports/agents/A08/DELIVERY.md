# A08 delivery evidence — 2026-10-29

**Status: DELIVERED WITH BLOCKED ACCEPTANCE. NOT WINDOWS-QUALIFIED. NOT SCIENTIFICALLY QUALIFIED.**

## Input, identity and isolation

- Sole authorized input: uploaded archive `SQE-Studio-product-foundation-CLEAN(8).zip`, SHA-256 `27fd2ec0cec6c8cbc67e21a180fe90ffa0465532fe7cc534d4a1a09b364b4e07` — **MATCH** before source extraction/edits.
- Archive traversal precheck: 50 entries, no absolute paths, `..` or backslashes in member names; untouched BASE passed `tools/delta.py verify`.
- `FOUNDATION_LOCK.json` tree digest: `4a3d24b0d43ab5a6bec18f21276db1c21f904fe09a7c6bfc193d870a20998a9c`; frozen contract digest: `6ffd28ebea3dcfa815a61c22598733520055d8e2b902c1e7ec5ffd5255f74171`.
- Independent BASE and WORK copies; no historical data/archive merge. No edits to `pyproject.toml`, frozen contracts, core ABI, adapters, registry, jobs/worker, web assets or other agents' files.

## Changes implemented (A08-owned only)

1. `server.py`: explicit loopback/Host and CSRF/Origin/Sec-Fetch verification; duplicate/conflicting HTTP header rejection; JSON size cap, duplicate-key/NaN/deep-object rejection, bounded receive timeouts, privacy-safe URL-free access logs, security response headers, failed-login throttling, first-run token symlink protection, authenticated CSRF-protected password-change and session-clear endpoint, native result path/size/symlink and revision/digest/engine/study provenance guards.
2. `store.py`: SQLite WAL/busy-timeout/FULL durability, protected data root permissions on POSIX, DB symlink rejection, transactional CAS and account setup, legacy 250,000-round PBKDF2-HMAC-SHA256 login upgrade to 600,000 rounds, password rotation invalidating all sessions, session pruning, email/password length and control-character constraints, owner-scoped stored runs and revision validation.
3. `scripts/`: reviewed-offline-wheelhouse PowerShell build, exact-name wheel+SHA256 sidecar Windows install, local-first launcher, installed-wheel byte-for-byte static asset inspection and child-process HTTP smoke, opt-in real Chromium/Playwright browser script. No third-party binary is fetched by any installer. Scripts are **not** claimed Windows-tested.
4. `requirements/`: pinned build dependency candidates, separately documented optional Quantum Metal/scqubits/Gmsh candidate pins, SQDMetal/Python 3.11 limits, Palace/WSL and JosephsonCircuits.jl native sidecar policy; explicitly no unverified native auto-installs.
5. `tests/security/`: fresh attack checks for Host/Origin/CSRF/cookies/password lifecycle, throttling, ACLs, concurrency, JSON/framing caps, result path/symlink/provenance and ZIP artifact exclusion. All fixture archive tests are non-scientific controls, never claimed native results.

## Raw evidence / actual versions / results

Primary unedited command log in the delta: `logs/A08-tests.log`. The runner **actually returned status 1** because browser navigation was blocked and Windows-only checks could not run. Each subcommand in that raw log declares its own real exit status. **Do not reclassify the overall result as pass.**

| Check | Outcome | Evidence |
| --- | --- | --- |
| Foundation integrity tool | PASS | `verify` emitted exact tree and contract digests (exit 0). |
| Linux host | Observed | Linux 6.18.55 x86_64; Python 3.13.5; setuptools 82.0.1; pytest 9.0.2. |
| Focused and foundation tests | PASS | `pytest -q tests/security tests/test_domain.py tests/test_delta.py tests/ui`: **21 passed**, 2 unrelated importlib deprecation warnings (exit 0). |
| Isolated core wheel build, repeated | PASS on Linux | Two clean wheel outputs with `SOURCE_DATE_EPOCH=1700000000` compared byte-for-byte (`cmp` exit 0); SHA-256 both `4077aba6ebfa1628dc7d72abda7e03cce9fa6a1214f20fc45e4961fa345fbf70`. This is **not** a Windows reproducibility certificate. |
| Independent installed wheel | PASS on Linux | `venv` `pip install --no-index --no-deps` (exit 0), `scripts/verify_wheel.py` child process (exit 0), local real HTTP `/api/status`, HTML/CSS/JS, first-run registration, login, CSRF rejection, revision and logout. |
| All three wheel UX assets | PASS on Linux | `index.html` SHA-256 `139bcd43c94a32ab60c2c2873033ff039ed9d0297213fa099698164d43ec6f99`; `app.js` `d73b5aed3c6df7c1c045d1b9041a89f5fdec8f373598424beac709c73da48086`; `style.css` `950ca46e89ff5676ffa3fa9d56dee7ccb491423d9845cceae4c0c1a5ce33bdad`. Hashes from wheel contents match imported installed resources and HTTP bytes. |
| Real browser over local HTTP | **BLOCKED, exit 1** | Playwright 1.57.0 + Chromium 144.0.7559.96 attempted `page.goto(127.0.0.1)`, rejected `net::ERR_BLOCKED_BY_ADMINISTRATOR`. Managed Chromium policy has `URLBlocklist: ["*"]`. This **is not** browser acceptance. Do not bypass administrator policy. |
| Windows 11 x64, Python 3.11, PowerShell, firewall/LAN | **NOT RUN** | Available runner is Linux Python 3.13, cannot claim Windows installer, Windows package repeatability, or absence of LAN listener from Windows firewall. Loopback binding is asserted in code and Linux tests only. |
| Scientific native engines & benchmark/output review | **NOT RUN/BLOCKED** | No native scientific dependencies installed/qualified. No produced solver convergence, spectrum, GDS, EM mesh, S-parameters, quantitative benchmarks, experimental results or foundry signoff. |

## Dependency inventory and verified upstream boundaries

- Reviewed as candidate runtime pins: Quantum Metal **0.9.0** (Python 3.10–3.14 metadata), scqubits **4.3.1** (Python 3.9+ metadata), Gmsh **4.15.2** (upstream Windows x64 wheel). No native smoke was performed on this runner. Source: https://pypi.org/project/quantum-metal/0.9.0/ ; https://pypi.org/project/scqubits/4.3.1/ ; https://pypi.org/project/gmsh/ .
- SQDMetal upstream currently states Python `>=3.11,<3.12`, `pandas==2.3.3`, and `quantum-metal[full]`; no SQDMetal release/commit, binary, wheel or dependency graph is automatically acquired. Source: https://github.com/sqdlab/SQDMetal/blob/main/pyproject.toml .
- Palace maintainers explicitly do not routinely test or officially support native Windows binaries; WSL/Ubuntu is best-effort, not a qualified SQE adapter transport. Source: https://awslabs.github.io/palace/stable/faq/ .
- JosephsonCircuits.jl depends on independent Julia environment/setup and a reviewed netlist/port mapping; no Julia environment or fake Julia outputs are included. Source: https://github.com/kpobrien/JosephsonCircuits.jl .
- Pinned **build** packages: setuptools 80.9.0; wheel 0.45.1; build 1.3.0; packaging 25.0; pyproject_hooks 1.2.0. Intended wheelhouse input is reviewed externally; a hash-complete transitive lock and Windows repeatability test remain to be established.

## Residual limitations / fail-closed boundaries

- **Windows 11 acceptance remains blocked**. A09 or a designated Windows runner must execute the two PowerShell scripts, verify wheel SHA and deterministic output, inspect UAC/ACL and firewall behavior, use an actual Windows browser, and exercise an independent application process and authentication attacks.
- **Managed Chromium browser policy** prevents navigation here. The browser script is delivered for a permitted host, but no UI browser success is claimed in this report.
- Login throttling is per service process, not a distributed/OS firewall. This is a single-user local-only host, not a secure web server for LAN/external exposure. The HTTP cookie lacks `Secure` specifically because the foundation serves loopback HTTP; `HttpOnly`+`SameSite=Strict` do not make LAN exposure safe. OS Windows data ACL enforcement and private Windows firewall are unverified.
- `POST /api/password` is secure API capability only; UI change-password controls fall under A07. Data rest encryption, full recovery ceremony, session hard timeouts in multi-instance deployments, native worker OS sandbox, supply-chain signing and algorithm agility need follow-up. No database/project schema changes are automatic.
- The frozen package metadata names a missing entrypoint `sqe_studio.agent_delta:main`; installation of the core CLI and module works, but that dead CLI command remains a known **frozen** defect to be migrated by A09 (and README must be updated to document offline wheel-first installer). Do not patch shared/frozen files in A08.
- Engine health detects availability only: it never qualifies native execution. A02/A03/A04/A05 and A01/A06 integration candidates must be independently tested by A09, with reviewed mappings and native provenance. SQDMetal/Palace and JosephsonCircuits adapters remain fail-closed.

## Proposed A09 versioned migration (not performed)

**Package metadata v0.1.1**: explicitly review the missing `sqe-studio-delta` script in `pyproject.toml` (remove or direct to an actually present, reviewed implementation), and align the shared README, integrated dependency metadata and Windows instructions with the immutable wheel/isolated-install process. No ownership-incompatible direct change was made. Do not alter project snapshots or the frozen domain contract without a separate migration version, independent backup and regression plan.

## Admission conditions

`DELTA_MANIFEST.json` is generated by the immutable foundation `tools/delta.py pack` (which includes SHA-256 preimage/content pairs and the raw log digest), with the truthful exit code **1**. Only A08-owned changes are present. The untouched BASE is used for the final `admit` step. No full source ZIP, native outputs or private studio data is included.
