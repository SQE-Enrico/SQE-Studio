# A04 delivery report — native scqubits / Hamiltonian provenance

**Status: DELTA READY FOR ADMISSION, NOT SCIENTIFICALLY QUALIFIED.** A04 is an implementation agent, not A09. No cross-agent source, frozen contract, registry, base ABI, install recipe, UI, core project schema or worker changes were made. This report is not an instrument/experimental measurement or a native solver benchmark.

## Baseline identity / isolation

- Authorized original upload: `SQE-Studio-product-foundation-CLEAN(4).zip` (user-provided basename in sandbox); SHA-256 **`27fd2ec0cec6c8cbc67e21a180fe90ffa0465532fe7cc534d4a1a09b364b4e07`**, independently measured before extraction.
- `python tools/delta.py verify` on the untouched extracted foundation: tree **`4a3d24b0d43ab5a6bec18f21276db1c21f904fe09a7c6bfc193d870a20998a9c`**, frozen contract **`6ffd28ebea3dcfa815a61c22598733520055d8e2b902c1e7ec5ffd5255f74171`**, file_count 48.
- Edited an isolated `WORK/SQE-Studio` copy of that exact extracted `BASE/SQE-Studio`; no A01/A02/A03/A05/A06/A07/A08 source integrated.

## Files owned / changed

- `src/sqe_studio/adapters/scqubits_adapter.py`: deterministic allowlisted native scqubits dispatch, typed results and provenance.
- `tests/adapters/test_scqubits_validation.py`: preflight/negative, staleness, boundedness, native-dispatch structural and nonreal native-output checks.
- `tests/adapters/test_scqubits_native.py`: actual native transmon, fluxonium, flux sweep and coupled two-transmon acceptance tests; genuinely skipped when native package is missing (never replaced by synthetic solver results).
- `docs/agents/A04.md`: input grammar, examples, output schema and upstream migration notes.
- `reports/agents/A04/REPORT.md` and `native_probe.txt`: this evidence and environment capture.

All preimage/content hashes and operations are populated from the unchanged baseline by `tools/delta.py pack`, including `null` preimage for newly owned files. Final admission is verified by `tools/delta.py admit`.

## Implemented physics boundary

1. Standalone actual `scqubits.Transmon`, `Fluxonium`, `TunableTransmon` constructors, `eigenvals(evals_count=...)`; never an SQE approximation of the Hamiltonian eigensolver.
2. Native `scqubits.HilbertSpace` for 2..3 explicit devices, with 1..3 Hermitian `n_operator x n_operator` interactions through native `add_interaction`; native eigenvalues for both coupled and otherwise identical unlinked systems, recorded as comparison, **not** measured/fitted interaction strength or unqualified physical extraction.
3. Explicit saved sweeps: up to 21 parameter values (by native calls), up to 12 levels, total composite Hilbert dimension <=144. Output includes x axes, absolute energies and ground-relative transitions for A06/A07. No arbitrarily evaluated expressions, dynamic imports, external shell commands or derived parameters from CAD.
4. Finite-input validation, strict native unit convention (`GHz` as E/h, normalized `Phi0` flux, `ng` in `2e`), basis sizing, explicit units for new studies, and bounded basis refinement. Native one-step convergence is measured against transition energies for every requested sweep point, not fabricated or assumed; failed tolerance prevents success artifacts. Disabled convergence is marked `not_checked` and must not be interpreted as converged.
5. Independent/explicit-source path supported; any declared engine-/EM-derived source or user-self-signed EM verification fails closed until A01 delivers trusted verified quantity proof tied to the immutable revision and exact originating artifacts. SHA-256 input/context stamps can detect local stale mutations; they are not substitutes for authenticated cross-engine provenance.
6. `input_snapshot.json`, `spectrum.json`, `series.json`, optional `coupling.json` with versioned subartifact schemas and the frozen worker ABI `{engine_version, native_files, kind, scientific_status}`. The unchanged worker still hashes each emitted file and stamps its immutable revision/project provenance; existing UI's `levels`/`units` fields remain available to preview the first point. Series rendering itself is pending A07.

## Test evidence (actual run)

- Command: `PYTHONPATH=src python -m pytest -q -rA -s tests` inside isolated `WORK/SQE-Studio`.
- Raw complete stdout/stderr: `logs/A04-tests.log` in the delta, and truthfully declared exit code **0**.
- **47 passed, 4 skipped, 2 warnings**; Python 3.13.5, Linux x86_64. The four skipped native checks are `test_real_transmon`, `test_real_fluxonium`, `test_real_native_flux_sweep`, `test_real_native_composite_coupling`; reason: **scqubits is not installed**.
- Specifically tested negative: unsupported model, missing EC/EJ, invalid/nonfinite flux and energies, wrong units, unverified EM extraction, unknown operator, overbound composite basis/sweep/convergence and stale context/input digest. Runtime component shape tests use structural spies only; no spy data is included or reported as numerical solver output.
- `native_probe.txt` records availability of installed packages at time of test: **scqubits NOT INSTALLED, QuTiP NOT INSTALLED**; numpy 2.3.5, scipy 1.17.0, pytest 9.0.2. A package-index probe to install scqubits could not resolve the index DNS endpoint in this environment. No published native scqubits version, native eigenenergy, native basis-runtime measurement or native convergence observation exists from this run.

### Actual acceptance input cases, pending native runtime

| Case | Inputs and nominal basis | Native runtime / result |
| --- | --- | --- |
| Transmon | `EJ=15 GHz, EC=0.25 GHz, ng=0 (2e), ncut=10`, `levels=3`, resolved `truncated_dim=6`, convergence increment 3, tolerance 0.1 GHz | **NOT RUN — scqubits absent**; no energy table or timing claimed |
| Fluxonium | `EJ=8 GHz, EC=2 GHz, EL=0.5 GHz, flux=0.5 Phi0, cutoff=20, truncated_dim=5`, `levels=3` | **NOT RUN — scqubits absent** |
| Fluxonium sweep | Same Fluxonium, `flux=[0.4,0.5,0.6] Phi0` | **NOT RUN — scqubits absent** |
| Composite | Two above-grammar Transmons, each `ncut=10, truncated_dim=4`; coupling `g=0.025 GHz * n1*n2`, `levels=4`, joint dimension 16 | **NOT RUN — scqubits/QuTiP absent** |

Native tests are present and automatically execute on a suitable installed `scqubits>=4.3,<5` environment. Failure will be reported rather than ignored when scqubits is importable but its dependencies/interfaces are broken. Native Windows 11 acceptance, runtime/precision benchmarking, scientific calibration and independent solver convergence remain **BLOCKED / NOT QUALIFIED**.

## Dependencies and limitations

- Runtime engine: installed `scqubits>=4.3,<5` with compatible QuTiP, numpy and scipy; A04 is prohibited from adding packages to frozen `pyproject.toml`. `scq.set_units('GHz')` is applied inside the isolated worker.
- Composite interactions intentionally only charge-charge `n_operator` products; no EPR, black-box quantization, oscillator/cavity extraction, nonlinear many-body decomposition, weak-coupling perturbation assertion or qubit-resonator coupling inference.
- Units and quantified native results cannot be evaluated end to end here due to absent scqubits. A passing one-step basis sensitivity criterion is not a full convergence proof. Native Hamiltonian eigenvalues are uncalibrated design predictions, not measurement or silicon qualification.
- Fixed 180s worker timeout and one-job laptop budget may time out slow fluxonium/composite sweeps; output status must remain failed/timed out, not silently approximated.
- Optional context and input hash stamps are not mandatory for legacy independent inputs and cannot prove source revision by themselves. Cross-engine derivations stay blocked.
- Current foundation UI plots `spectrum.levels` for **first sweep point only**. It does not render `series.json` until A07 integration; no UI files were changed.
- Foundation `tests/test_domain.py::test_engine_job_without_installed_native_engine_is_not_faked` assumes scqubits is unavailable. Once scqubits is installed, this *preexisting, unowned* test must be updated by the appropriate owner/A09 to condition its expectation on engine health; A04 did not modify it.

## Proposed **versioned** migrations for A09 (no frozen changes made)

1. **A01 verified-derived-quantity interface, v2**: freeze a typed signed/trusted or server-produced lineage object, not a user-editable boolean, with quantity ID, value, UCUM/documented units, physical dimension, target Hamiltonian field, transformation method/version, uncertainty/assumptions, parent artifact SHA-256, engine version, project revision ID and `verified` gate. Worker should pass authenticated envelope/source handles outside user-controlled `study.inputs`; A04 may accept EM-derived values only after checking it against the run's authenticated revision and source artifact chain. Block `palace.eigenmodes -> scqubits.spectrum` until physically reviewed mapping is implemented/tested. In particular an eigenmode frequency alone cannot imply EJ/EC/EL.
2. **Artifact taxonomy and series v2**: extend `contracts/interoperability.json` artifact types for `scqubits.spectrum.series`, `scqubits.coupling` and `scqubits.input_snapshot` (or define them as typed child members of `scqubits.spectrum`); explicitly version `axes`, `series`, `normalization`, `source_snapshot_sha256`, units and A06 iteration keys. Preserve checksums and reject stale upstream artifacts.
3. **A06/A07 integration v2**: expose verified immutable revision and artifact identity in the adapter invocation without breaking frozen `run(study, project, output_dir)` until A09 reviews a new ABI; register sweep-series plotting and coupling inspection instead of first-point-only preview. Preserve `review_required` and `HOLD` statuses.
4. **Native/Windows qualification**: install scqubits in pinned, reviewed Windows 11 Python 3.11 environment, run four real acceptance cases, capture exact native dependency versions, basis, runtime, energy tables/hash and independently evaluate basis convergence. Review the existing hardcoded absence test as above.

**Integrator instruction:** accept this delta only as A04-owned, native-engine-gated functionality. Do not mark EM extraction, Windows packaging, full convergence or scientific/fabrication qualification as complete.
