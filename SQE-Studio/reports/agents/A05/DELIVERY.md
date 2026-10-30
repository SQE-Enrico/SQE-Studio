# A05 delivery: JosephsonCircuits.jl adapter

## Baseline and provenance

- Sole authorized archive: uploaded `SQE-Studio-product-foundation-CLEAN(6).zip`, bytes verified against SHA-256 `27fd2ec0cec6c8cbc67e21a180fe90ffa0465532fe7cc534d4a1a09b364b4e07` on 2026-10-29.
- `tools/delta.py verify` on the untouched extracted `BASE/SQE-Studio` succeeded: foundation tree SHA-256 digest `4a3d24b0d43ab5a6bec18f21276db1c21f904fe09a7c6bfc193d870a20998a9c`; frozen-contract digest `6ffd28ebea3dcfa815a61c22598733520055d8e2b902c1e7ec5ffd5255f74171`.
- Work was performed in a separate `WORK/SQE-Studio` tree. Exactly four owned paths were added/changed: the adapter, A05 test, A05 docs and this A05 report. No frozen contracts, base ABI, registry, setup or other agent files were edited. A05 is **not** the integrator.

## Implementation and test input

- The adapter consumes a matching hash of saved `project.schematic`, 2–24 nodes including ground, 1–48 bounded SI R/L/C/Lj elements and 1–4 ordered ports. See `docs/agents/A05.md` for the entire schema, acceptance gates and native port normalization.
- The adapter contains a fixed Julia source literal. Python validates strict declarative input, emits an ASCII TSV request and calls native `JosephsonCircuits.hblinsolve` (linear) or bounded native `hbsolve` (one-tone pump), then stores only native S complex values and provenance. No synthetic S data or internal RF equations.
- Native data/metadata must include actual version and time from Julia, exact native port ordering and port impedance indices, SI unit conventions, pump settings and a candid solver-returned status without fabricated convergence logs. The outer worker attaches immutable revision/project digests to its artifact manifest when an engine run truly succeeds.
- Test fixture (declarative, **not** solver output): ground `0`, nodes `n1,n2`, capacitor 0.1 pF `n1->n2`, inductor 1 nH `n2->0`, port 1 at `n1` with 50 ohms; requested 4.5 GHz and 5 GHz. Nonlinear fixture adds Josephson inductance 1 nH `n2->0`, one 4.75 GHz 1 nA current tone, pump-harmonic limit 2, modulation-harmonic limit 1. No claim is made that the nonlinear operating point converges.

## Actual environment and blocked science

- Host tool `julia`: **not installed/on PATH** (`command -v julia` returned no executable).
- JosephsonCircuits.jl native package version: **unknown (not installed/testable)**.
- Julia version, native timings, native S-parameters, per-iteration convergence: **not observed**. No native values were generated, estimated, or substituted.
- Native small-circuit linear smoke and nonlinear Josephson harmonic-balance smoke: **BLOCKED/SKIPPED**, not passed. The tests are present and run only if `julia` is available; if Julia is installed without the package or an API mismatch occurs, they should fail and supply native error evidence.
- Actual focused tests cover missing ground, duplicated ports, invalid impedance, ghost-node references, stale schematic hash, unsafe identifiers, port shunt ambiguity, disconnected nets, unsupported pump topology, excessive sweep/harmonics, runtime absence, simulated subprocess errors and timeouts. Simulated subprocess *errors* do not simulate scientific results.
- Native API intended by implementation: `hblinsolve`, `hbsolve`, `lin.S((0,),output,(0,),input,k)`, `lin.portnumbers`, `lin.portimpedanceindices`. API compatibility and result conventions remain unverified at runtime. Sources: https://josephsoncircuits.org/stable/ and https://josephsoncircuits.org/stable/reference/ .

## Gaps and A09 follow-up

- No native scientific validation, linear benchmark against a trustworthy reference, nonlinear convergence residual inspection, engine version interoperability matrix, installed package test, or Windows 11 smoke was possible. There is no native pass/qualification claim, and emitted results are `review_required`/`HOLD`.
- Only the direct signal `(0,)->(0,)` S matrix is exported; idler conversion, full pumped scattering and DC/multi-pump/flux-pump analyses are explicitly unsupported. No impedance renormalization is attempted.
- A01 should formalize a typed `circuit.netlist`/`josephson.sparameters` edge, a reviewed schematic-to-port mapping and the native power-wave convention. A06 should confirm cross-process single active job, timeout, artifact provenance and caching. A09 should review a versioned `sqe.interoperability.v2` migration before modifying any frozen contracts.
- Full test command, full raw output, exact exit code and skip totals are packaged under `logs/A05-tests.log` with the delta. Verify delta admission against the untouched BASE; no silent conflict fix.

## Final regression record

- Final command (2026-10-29 UTC): `PYTHONPATH=src python -m pytest -ra -q tests`, Python 3.13.5, pytest 9.0.2, **exit 0; 41 passed, 2 skipped; 2 deprecation warnings**. See the included unmodified command output `logs/A05-tests.log` for exact skips and stdout. The skipped native tests are not a pass.
- A preliminary full-regression invocation exposed a legacy test that expected the blocked-engine error to contain `requires`/`awaits`; the final adapter error wording was adjusted **within the owned file only**, preserving fail-closed semantics. The untouched shared test was not modified. The final regression is the packaged raw test log.
