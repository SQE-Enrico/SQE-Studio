"""Device-neutral, revision-first EDA optimization contracts (no synthetic scoring).

This module is deliberately *not* a second simulation worker. It prepares
bounded geometry proposals, requires a new Store revision and fresh native job
for each proposal, and inspects only authorized, SHA-256-verified native output.
Physical metric extraction and automated ranking remain gated by expert
identity/mapping review; native data alone do not make an objective qualified.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path
import re
import time
from typing import Mapping

from ..contracts import digest, validate_project
from .artifacts import (ArtifactInvalid, adapter_digest, fingerprint, sha_bytes,
                        valid_sha, verify_manifest)
from .sweep import GeometryPoint, _geometry_target, plan_geometry_sweep
from ..interop.native_views import NativeDisplayError, palace_eigenmodes

SCHEMA = 'sqe.geometry-optimization.v1'
MAX_GOALS = 12
# The native Jobs worker enforces at most 900 s for one reviewed EM solve.
# An optimization plan never schedules all 24 general-purpose study-sweep points:
# three explicit operator-reviewed revisions are the *whole lineage* limit (~45 min).
MAX_OPTIMIZATION_SOLVES = 3
NATIVE_SOLVE_BUDGET_SECONDS = 900
MAX_OPTIMIZATION_NATIVE_SECONDS = MAX_OPTIMIZATION_SOLVES * NATIVE_SOLVE_BUDGET_SECONDS

# Explicit units and physical identities, not arbitrary JSON paths or eval code.
# All are *conditional* observations, not currently qualified objectives.
METRICS = {
    'em.mode_frequency': ('sqdmetal_palace', 'GHz', 'mode'),
    'em.loaded_q': ('sqdmetal_palace', '1', 'mode'),
    'rf.s_parameter_magnitude': ('sqdmetal_palace', '1', 'ports'),
    'rf.s_parameter_phase': ('sqdmetal_palace', 'rad', 'ports'),
    'rf.return_loss': ('sqdmetal_palace', 'dB', 'ports'),
    'rf.bandwidth': ('sqdmetal_palace', 'Hz', 'ports'),
    'quantum.transition_frequency': ('scqubits', 'GHz', 'transition'),
    'nonlinear_rf.gain': ('josephson_circuits', 'dB', 'ports'),
    # Literal, saved CAD dimensions only: never a surrogate for EM/EPR physics.
    'cad.dimension': ('sqe_cad', None, 'dimension'),
}
_IDENTIFIER = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,47}$', re.ASCII)


class OptimizationBlocked(ValueError):
    """Unsafe/stale/unsupported design iteration or scientific evaluation."""


def _finite(value: object) -> bool:
    return type(value) in (float, int) and math.isfinite(value)


@dataclass(frozen=True)
class Goal:
    """One unit-checked objective or feasibility bound, never a numerical claim.

    `identity` binds the intended physical mode, port pair or transition by
    explicit *symbolic* identity; physical matching is a later evidence gate.
    """
    name: str
    metric: str
    unit: str
    comparison: str
    threshold: float
    identity: tuple[tuple[str, str | int | float], ...]
    tolerance: float | None = None

    def __post_init__(self):
        if type(self.name) is not str or not _IDENTIFIER.fullmatch(self.name):
            raise ValueError('Goal needs a unique ASCII identifier')
        definition = METRICS.get(self.metric) if type(self.metric) is str else None
        if definition is None or (self.unit not in ('mm', 'um', 'nm') if definition[2] == 'dimension'
                                   else self.unit != definition[1]):
            raise ValueError('Unknown metric or ambiguous/mismatched units')
        if self.comparison not in ('minimize', 'maximize', 'target', 'at_most', 'at_least'):
            raise ValueError('Unsupported objective/constraint comparison')
        if not _finite(self.threshold) or (self.tolerance is not None and
                                           (not _finite(self.tolerance) or self.tolerance < 0)):
            raise ValueError('Goal threshold/tolerance must be finite')
        if (self.comparison == 'target') != (self.tolerance is not None):
            raise ValueError('Target requires tolerance; other comparisons prohibit tolerance')
        if type(self.identity) is not tuple or any(type(pair) is not tuple or len(pair) != 2
                                                   or type(pair[0]) is not str
                                                   for pair in self.identity):
            raise ValueError('Goal identity must be explicit immutable key/value pairs')
        identity = dict(self.identity)
        if len(identity) != len(self.identity):
            raise ValueError('Duplicate physical identity fields')
        kind = definition[2]
        expected = {'mode': {'mode_label'},
                    'ports': {'input_port', 'output_port', 'frequency_hz', 'reference_plane'},
                    'transition': {'transition_label'},
                    'dimension': {'parameter_path'}}[kind]
        if set(identity) != expected:
            raise ValueError('Metric requires explicit physical identity and reference plane')
        for key, value in identity.items():
            if key == 'frequency_hz':
                if not _finite(value) or value <= 0:
                    raise ValueError('RF frequency must be positive finite Hz')
            elif key == 'parameter_path':
                if (type(value) is not str or len(value) > 180 or
                        not value.startswith('layout.') or
                        any(not _IDENTIFIER.fullmatch(part) for part in value.split('.'))):
                    raise ValueError('CAD identity requires a named layout dimension path')
            elif type(value) is not str or not _IDENTIFIER.fullmatch(value):
                raise ValueError('Physical identity labels must be stable named identifiers')
        if kind == 'mode' and identity['mode_label'].isdigit():
            raise ValueError('Mode indices are not physical mode identities')


@dataclass(frozen=True)
class OptimizationPlan:
    schema: str
    source_revision: str
    source_project_digest: str
    study_id: str
    objectives: tuple[Goal, ...]
    constraints: tuple[Goal, ...]
    candidates: tuple[GeometryPoint, ...]
    fabrication_status: str = 'HOLD'
    physical_qualification: str = 'BLOCKED_PENDING_NATIVE_AND_EXPERT_REVIEW'
    native_budget_seconds: int = NATIVE_SOLVE_BUDGET_SECONDS
    planned_native_budget_seconds: int = NATIVE_SOLVE_BUDGET_SECONDS
    source_native_run_id: str | None = None
    source_native_manifest_sha256: str | None = None
    # Ordered (revision, project digest, fresh run, manifest SHA, owner review SHA).
    # Never reset the bounded native-work ledger during a reviewed replan.
    native_lineage: tuple[tuple[str, str, str, str, str], ...] = ()


@dataclass(frozen=True)
class CandidateRun:
    """A saved immutable revision plus a *fresh* native submission or failure."""
    candidate_digest: str
    revision_id: str
    run_id: str | None
    status: str
    reason: str | None = None
    review_digest: str | None = None
    fabrication_status: str = 'HOLD'


def plan_optimization(project: Mapping, source_revision: str, study_id: str, axes: Mapping,
                      *, objectives: tuple[Goal, ...], constraints: tuple[Goal, ...] = (),
                      mode: str = 'manual', selected: int | None = None) -> OptimizationPlan:
    """Represent objectives and physical constraints on genuine geometry candidates.

    No project key/schema is added and no native execution is implied. The
    current geometry-to-EM edge requires an explicit saved native EM study.
    Other metrics are expressible but their cross-engine edges are still HOLD.
    """
    validate_project(project)
    if type(study_id) is not str or not _IDENTIFIER.fullmatch(study_id):
        raise ValueError('Saved study identity required')
    studies = [s for s in project['studies'] if s['id'] == study_id]
    if len(studies) != 1 or studies[0]['engine'] != 'sqdmetal_palace' or (
            studies[0]['kind'] not in ('eigenmode', 'sparameters', 'capacitance')):
        raise OptimizationBlocked('Geometry objectives require a saved native EM study')
    if (type(objectives) is not tuple or type(constraints) is not tuple or not objectives or
        len(objectives) + len(constraints) > MAX_GOALS or
        any(type(goal) is not Goal for goal in objectives + constraints)):
        raise ValueError('Use 1-12 typed objectives/constraints')
    if len({goal.name for goal in objectives + constraints}) != len(objectives + constraints):
        raise ValueError('Duplicate goal identifiers')
    if any(g.comparison not in ('minimize', 'maximize', 'target') for g in objectives):
        raise ValueError('Objective requires minimize, maximize or target')
    if any(g.comparison not in ('at_most', 'at_least') for g in constraints):
        raise ValueError('Constraint requires an inequality bound')
    for goal in objectives + constraints:
        if goal.metric == 'cad.dimension':
            try:
                _, _, unit = _geometry_target(project, dict(goal.identity)['parameter_path'])
            except (ValueError, KeyError, TypeError) as exc:
                raise OptimizationBlocked('CAD objective must reference a saved named dimension') from exc
            if unit != goal.unit:
                raise OptimizationBlocked('CAD objective unit mismatches the saved dimension')
    points = plan_geometry_sweep(project, source_revision, axes, mode=mode, selected=selected)
    if len(points) > MAX_OPTIMIZATION_SOLVES:
        raise OptimizationBlocked('Geometry optimization exceeds three native solves / 45-minute plan budget')
    return OptimizationPlan(SCHEMA, source_revision, digest(project), study_id,
                            objectives, constraints, points,
                            planned_native_budget_seconds=len(points) * NATIVE_SOLVE_BUDGET_SECONDS)


def _valid_lineage(lineage: tuple) -> bool:
    """Require bounded, typed, distinct historical solve and review identities."""
    if len(lineage) >= MAX_OPTIMIZATION_SOLVES:
        return False
    run_ids, revisions = set(), set()
    for step in lineage:
        if (type(step) is not tuple or len(step) != 5 or
            any(type(value) is not str for value in step) or
            not re.fullmatch(r'[a-f0-9]{32}', step[0]) or
            not valid_sha(step[1]) or
            not re.fullmatch(r'[a-f0-9]{32}', step[2]) or
            not valid_sha(step[3]) or not valid_sha(step[4]) or
            step[0] in revisions or step[2] in run_ids):
            return False
        revisions.add(step[0])
        run_ids.add(step[2])
    return True


def _confirm_candidate(plan: OptimizationPlan, candidate: GeometryPoint) -> dict:
    if (plan.schema != SCHEMA or
        plan.native_budget_seconds != NATIVE_SOLVE_BUDGET_SECONDS or
        plan.planned_native_budget_seconds != len(plan.candidates) * NATIVE_SOLVE_BUDGET_SECONDS or
        type(plan.native_lineage) is not tuple or
        not 1 <= len(plan.candidates) <= MAX_OPTIMIZATION_SOLVES or
        len(plan.native_lineage) + len(plan.candidates) > MAX_OPTIMIZATION_SOLVES or
        not _valid_lineage(plan.native_lineage) or
        (plan.source_native_run_id is None) != (plan.source_native_manifest_sha256 is None) or
        (bool(plan.native_lineage) != bool(plan.source_native_run_id)) or
        (bool(plan.native_lineage) and
         (plan.native_lineage[-1][:2] != (plan.source_revision, plan.source_project_digest) or
          plan.native_lineage[-1][2:4] != (plan.source_native_run_id,
                                           plan.source_native_manifest_sha256))) or
        (plan.source_native_run_id is not None and
         (type(plan.source_native_run_id) is not str or
          not re.fullmatch(r'[a-f0-9]{32}', plan.source_native_run_id) or
          not valid_sha(plan.source_native_manifest_sha256))) or
        candidate not in plan.candidates or
        candidate.source_revision != plan.source_revision or
        candidate.source_project_digest != plan.source_project_digest or
        digest(candidate.project) != candidate.project_digest or
        digest({'layout': candidate.project['layout'],
                'process': candidate.project['process']}) != candidate.geometry_digest or
        candidate.candidate_digest != digest({
            'source_revision': candidate.source_revision,
            'source_project_digest': candidate.source_project_digest,
            'project_digest': candidate.project_digest,
            'coordinates': candidate.coordinates})):
        raise OptimizationBlocked('Geometry candidate or source binding was changed')
    validate_project(candidate.project)
    studies = [s for s in candidate.project['studies'] if s['id'] == plan.study_id]
    if len(studies) != 1 or studies[0]['engine'] != 'sqdmetal_palace':
        raise OptimizationBlocked('Native study changed during geometry planning')
    return studies[0]



def _verified_parameter_change(source: dict, candidate: GeometryPoint) -> None:
    """Reconstruct the full change from original CAD; reject hidden material/solver edits.

    The public frozen dataclass is not itself a signed plan. Recomputing its SHA
    after inserting unrelated data must never authorize a supposedly CAD-only
    revision, even with a fresh review and a valid project digest.
    """
    coordinates = candidate.coordinates
    if (type(coordinates) is not tuple or not 1 <= len(coordinates) <= 3 or
            any(type(item) is not tuple or len(item) != 2 or
                type(item[0]) is not str or not _finite(item[1])
                for item in coordinates)):
        raise OptimizationBlocked('Candidate CAD parameter coordinates are invalid')
    paths = tuple(path for path, _ in coordinates)
    if paths != tuple(sorted(set(paths))):
        raise OptimizationBlocked('Candidate CAD dimensions are duplicated or unsorted')
    expected = deepcopy(source)
    try:
        for path, value in coordinates:
            node, field, _ = _geometry_target(expected, path)
            if field not in ('x_mm', 'y_mm') and value <= 0:
                raise OptimizationBlocked('CAD physical length must remain positive')
            node[field] = value
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise OptimizationBlocked('Candidate CAD target is missing or unsupported') from exc
    if (expected != candidate.project or digest(expected) != candidate.project_digest or
            digest({'layout': expected['layout'], 'process': expected['process']}) !=
            candidate.geometry_digest or expected == source):
        raise OptimizationBlocked('Candidate altered non-parameter inputs or made no CAD change')


def _cad_dimension_result(goal: Goal, source: dict, candidate: GeometryPoint,
                          revision: str, source_run: str | None,
                          manifest_sha: str | None) -> dict:
    """Exact revision-backed CAD parameter comparison, NEVER EM optimization."""
    path = dict(goal.identity)['parameter_path']
    try:
        old, old_field, old_unit = _geometry_target(source, path)
        new, new_field, new_unit = _geometry_target(candidate.project, path)
    except (ValueError, KeyError, TypeError) as exc:
        raise OptimizationBlocked('CAD goal dimension unavailable in saved revision') from exc
    if old_unit != goal.unit or new_unit != goal.unit:
        raise OptimizationBlocked('CAD goal units changed between revisions')
    before, after = old[old_field], new[new_field]
    if not _finite(before) or not _finite(after):
        raise OptimizationBlocked('CAD dimension value must be finite')
    if goal.comparison == 'at_most':
        feasible = after <= goal.threshold
    elif goal.comparison == 'at_least':
        feasible = after >= goal.threshold
    elif goal.comparison == 'target':
        feasible = abs(after - goal.threshold) <= goal.tolerance
    else:
        feasible = None  # direction alone is not a pass/fail target
    return {'goal': goal.name, 'metric': goal.metric, 'unit': goal.unit,
            'comparison': goal.comparison, 'threshold': goal.threshold,
            'tolerance': goal.tolerance, 'identity': {'parameter_path': path},
            'status': 'VERIFIED_CAD_PARAMETER_ONLY', 'value': after,
            'feasible': feasible, 'source_value': before, 'delta': after - before,
            'source_revision_id': candidate.source_revision,
            'source_project_digest': candidate.source_project_digest,
            'revision_id': revision, 'geometry_digest': candidate.geometry_digest,
            'project_digest': candidate.project_digest,
            'source_run_id': source_run, 'source_manifest_sha256': manifest_sha,
            'scientific_qualification': 'NOT_ESTABLISHED',
            'physical_objective': False, 'fabrication_status': 'HOLD'}


def _goal_spec_sha(plan: OptimizationPlan) -> str:
    return digest({'schema': plan.schema, 'source_revision': plan.source_revision,
                   'source_project_digest': plan.source_project_digest,
                   'study_id': plan.study_id,
                   'objectives': [asdict(goal) for goal in plan.objectives],
                   'constraints': [asdict(goal) for goal in plan.constraints]})


def _verify_source_native_anchor(store, owner: str, project_id: str,
                                 plan: OptimizationPlan) -> None:
    """Reverify every earlier solve *and* review in the bounded lineage.

    A previous valid manifest alone cannot reset or shorten the lifetime native
    budget: each saved review commits to the complete preceding chain. Rehash
    every recorded artifact and require the run's Store owner/revision binding.
    """
    if not plan.native_lineage:
        return
    try:
        for index, (revision, project_sha, run_id, manifest_sha, review_sha) in enumerate(
                plan.native_lineage):
            run = store.run(owner, project_id, run_id)
            if (run['revision_id'] != revision or run['study_id'] != plan.study_id or
                run['engine'] != 'sqdmetal_palace' or run['state'] != 'completed'):
                raise OptimizationBlocked('Previous native run is not a completed source-revision solve')
            folder = Path(store.root) / 'native-runs' / project_id / run_id
            if (folder.is_symlink() or folder.resolve() != Path(run['path']).resolve() or
                    not folder.is_dir()):
                raise OptimizationBlocked('Previous native run path changed')
            ref = verify_manifest(folder / 'output', revision_id=revision,
                                  project_digest=project_sha, study_id=plan.study_id,
                                  engine='sqdmetal_palace')
            if ref.manifest_sha256 != manifest_sha:
                raise OptimizationBlocked('Previous native artifact was replaced')
            # The manifest alone does not bind an earlier solve's saved inputs:
            # recheck the exact Store revision, solver kind and worker snapshot.
            saved_revision = store.project(owner, project_id, revision)
            if (saved_revision['revision'] != revision or
                saved_revision['revision_digest'] != project_sha or
                digest(saved_revision['model']) != project_sha):
                raise OptimizationBlocked('Previous native project/materials changed')
            studies = [study for study in saved_revision['model']['studies']
                       if study['id'] == plan.study_id]
            if len(studies) != 1 or studies[0]['engine'] != 'sqdmetal_palace':
                raise OptimizationBlocked('Previous solver identity changed')
            snapshot_path = folder / 'snapshot.json'
            if (snapshot_path.is_symlink() or not snapshot_path.is_file() or
                    snapshot_path.stat().st_size > 512_000):
                raise OptimizationBlocked('Previous native worker snapshot unsafe')
            snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
            if (snapshot.get('project') != saved_revision['model'] or
                snapshot.get('project_digest') != project_sha or
                snapshot.get('revision_id') != revision or
                snapshot.get('study') != studies[0] or
                snapshot.get('expected_adapter_sha256') != adapter_digest('sqdmetal_palace') or
                snapshot.get('attempt') != 1 or snapshot.get('retry_of') is not None or
                snapshot.get('parents') != [] or 'sweep_plan' in snapshot):
                raise OptimizationBlocked('Previous native snapshot/solver/materials mismatch')
            manifest = json.loads((folder / 'output' / 'RESULT_MANIFEST.json').read_text(encoding='utf-8'))
            expected_kind = {'eigenmode': 'palace.eigenmodes',
                             'sparameters': 'palace.sparameters',
                             'capacitance': 'palace.capacitance_matrix'}
            if (ref.artifact_type != expected_kind.get(studies[0]['kind']) or
                ref.cache_fingerprint != fingerprint(
                    revision_id=revision, project_digest=project_sha, study=studies[0],
                    native_version=ref.engine_version,
                    adapter_sha256=adapter_digest('sqdmetal_palace')) or
                manifest.get('adapter_sha256') != adapter_digest('sqdmetal_palace') or
                manifest.get('kind') != studies[0]['kind'] or
                manifest.get('provenance', {}).get('was_generated_by') != 'sqdmetal_palace' or
                'sweep_point' in manifest):
                raise OptimizationBlocked('Previous native solver/artifact fingerprint mismatch')
            review_path = _review_path(store, project_id, revision)
            if (review_path.is_symlink() or review_path.parent.is_symlink() or
                    not review_path.is_file() or review_path.stat().st_size > 8192):
                raise OptimizationBlocked('Previous candidate review is missing')
            saved = json.loads(review_path.read_text(encoding='utf-8'))
            if (digest(saved) != review_sha or saved.get('revision_id') != revision or
                saved.get('project_digest') != project_sha or
                saved.get('source_revision') != saved_revision['parent'] or
                (index > 0 and saved_revision['parent'] != plan.native_lineage[index-1][0]) or
                saved.get('native_lineage') != [list(step) for step in plan.native_lineage[:index]] or
                saved.get('source_native_run_id') != (plan.native_lineage[index-1][2] if index else None) or
                saved.get('source_native_manifest_sha256') != (plan.native_lineage[index-1][3] if index else None) or
                saved.get('scientific_qualification') != 'NOT_ESTABLISHED' or
                saved.get('fabrication_status') != 'HOLD'):
                raise OptimizationBlocked('Previous candidate review or cumulative native ledger changed')
    except (ArtifactInvalid, OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise OptimizationBlocked('Previous native artifact/review unavailable or stale') from exc


def _candidate_review(owner: str, candidate: GeometryPoint, review: Mapping) -> dict:
    """Explicit operator acknowledgment bound to this *exact* new layout.

    Acknowledgment is not independently validated materials, mode identity,
    physical convergence or foundry approval. Native adapters still recheck
    actual EM inputs and record review_required/HOLD.
    """
    if (type(review) is not dict or set(review) != {
            'schema', 'operator', 'candidate_digest', 'materials_rechecked',
            'ports_boundaries_rechecked', 'rationale'} or
        review['schema'] != 'sqe.geometry-review.v1' or
        review['operator'] != owner or
        review['candidate_digest'] != candidate.candidate_digest or
        review['materials_rechecked'] is not True or
        review['ports_boundaries_rechecked'] is not True or
        type(review['rationale']) is not str or
        not 12 <= len(review['rationale'].strip()) <= 1000 or
        any(ord(ch) < 32 or ord(ch) == 127 for ch in review['rationale'])):
        raise OptimizationBlocked('Explicit owner review of candidate materials/ports/boundaries required')
    return dict(review)


def _review_path(store, project_id: str, revision_id: str) -> Path:
    if (type(project_id) is not str or not re.fullmatch(r'[a-f0-9]{32}', project_id) or
        type(revision_id) is not str or not re.fullmatch(r'[a-f0-9]{32}', revision_id)):
        raise OptimizationBlocked('Unsafe project/revision identity for saved review')
    return Path(store.root) / 'optimization-reviews' / project_id / (revision_id + '.json')


def submit_geometry_candidate(store, jobs, owner: str, project_id: str,
                              plan: OptimizationPlan, candidate: GeometryPoint, *,
                              review: Mapping) -> CandidateRun:
    """Save one new revision, then force a fresh native Palace solve via JobManager.

    The caller owns auth/context; Store rechecks owner and optimistic head.
    Candidate submission never caches a previous run. A failed native queue
    leaves the newly saved design inspectable, with an explicit BLOCKED status.
    Plans must be regenerated from the new head before the next candidate.
    """
    study = _confirm_candidate(plan, candidate)
    record = store.project(owner, project_id)
    if (record['head'] != plan.source_revision or record['revision'] != plan.source_revision or
        record['revision_digest'] != plan.source_project_digest or
        digest(record['model']) != plan.source_project_digest):
        raise OptimizationBlocked('Source project is stale; replan on current head')
    original = store.project(owner, project_id, plan.source_revision)
    if (original['revision_digest'] != plan.source_project_digest or
            digest(original['model']) != plan.source_project_digest):
        raise OptimizationBlocked('Original CAD revision no longer matches saved source')
    _verified_parameter_change(original['model'], candidate)
    reviewed = _candidate_review(owner, candidate, review)
    _verify_source_native_anchor(store, owner, project_id, plan)
    em = study['inputs'].get('em')
    if (type(em) is not dict or em.get('execution') != 'solve' or
            candidate.project['process'].get('source') != 'reviewed'):
        raise OptimizationBlocked('Geometry solve requires reviewed materials and native EM execution')
    revision_id = store.commit(owner, project_id, plan.source_revision, candidate.project)
    # Save review *before* starting the worker. Failure is an explicit blocker,
    # not a fallback to an unreviewed solve.
    review_record = {'schema': 'sqe.geometry-reviewed-candidate.v1',
                     'source_revision': plan.source_revision,
                     'project_digest': candidate.project_digest,
                     'candidate_digest': candidate.candidate_digest,
                     'goal_spec_sha256': _goal_spec_sha(plan),
                     'revision_id': revision_id, 'review': reviewed,
                     'source_native_run_id': plan.source_native_run_id,
                     'source_native_manifest_sha256': plan.source_native_manifest_sha256,
                     'native_lineage': [list(step) for step in plan.native_lineage],
                     'recorded_at_utc': time.time(),
                     'scientific_qualification': 'NOT_ESTABLISHED',
                     'fabrication_status': 'HOLD'}
    review_sha = digest(review_record)
    try:
        path = _review_path(store, project_id, revision_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.parent.is_symlink() or not path.parent.resolve().is_relative_to(Path(store.root).resolve()):
            raise OptimizationBlocked('Optimization review directory is not private project storage')
        with path.open('x', encoding='utf-8') as handle:
            json.dump(review_record, handle, sort_keys=True, allow_nan=False)
    except (OSError, ValueError) as exc:
        return CandidateRun(candidate.candidate_digest, revision_id, None,
                            'BLOCKED_REVIEW_STORAGE', str(exc)[:400])
    try:
        before_submit = time.time()
        run_id = jobs.start(owner, project_id, revision_id, plan.study_id, force=True)
        if type(run_id) is not str or not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise OptimizationBlocked('Native job manager did not return a new run identity')
        run = store.run(owner, project_id, run_id)
        folder = Path(store.root) / 'native-runs' / project_id / run_id
        if (run['revision_id'] != revision_id or run['study_id'] != plan.study_id or
            run['engine'] != study['engine'] or run['created'] < before_submit or
            run['state'] not in ('queued', 'running', 'completed') or
            folder.is_symlink() or Path(run['path']).resolve() != folder.resolve() or
            not folder.is_dir()):
            raise OptimizationBlocked('Native job manager returned a stale, unrelated or unsafe run')
    except Exception as exc:
        return CandidateRun(candidate.candidate_digest, revision_id, None,
                            'BLOCKED_NATIVE_SUBMISSION', f'{type(exc).__name__}: {str(exc)[:400]}', review_sha)
    return CandidateRun(candidate.candidate_digest, revision_id, run_id,
                        'NATIVE_JOB_SUBMITTED_REVIEW_REQUIRED', review_digest=review_sha)


def _reviewed_candidate_state(store, owner: str, project_id: str,
                              plan: OptimizationPlan, candidate: GeometryPoint,
                              submission: CandidateRun) -> tuple[dict, dict]:
    """Check actual Store snapshot, source CAD, saved review and full prior lineage."""
    study = _confirm_candidate(plan, candidate)
    if (submission.candidate_digest != candidate.candidate_digest or
            type(submission.review_digest) is not str or not valid_sha(submission.review_digest) or
            submission.status not in ('NATIVE_JOB_SUBMITTED_REVIEW_REQUIRED', 'BLOCKED_NATIVE_SUBMISSION') or
            (submission.run_id is not None and
             (type(submission.run_id) is not str or
              not re.fullmatch(r'[0-9a-f]{32}', submission.run_id))) or
            (submission.status == 'NATIVE_JOB_SUBMITTED_REVIEW_REQUIRED') !=
            (submission.run_id is not None)):
        raise OptimizationBlocked('Candidate has no valid reviewed native submission state')
    saved = store.project(owner, project_id)
    if (saved['head'] != submission.revision_id or
        saved['revision'] != submission.revision_id or
        saved['parent'] != plan.source_revision or
        saved['revision_digest'] != candidate.project_digest or
        digest(saved['model']) != candidate.project_digest):
        raise OptimizationBlocked('Candidate geometry/revision is stale or inconsistent')
    original = store.project(owner, project_id, plan.source_revision)
    if (original['revision_digest'] != plan.source_project_digest or
            digest(original['model']) != plan.source_project_digest):
        raise OptimizationBlocked('Original CAD revision was replaced')
    _verified_parameter_change(original['model'], candidate)
    path = _review_path(store, project_id, submission.revision_id)
    if (path.is_symlink() or path.parent.is_symlink() or
        not path.parent.resolve().is_relative_to(Path(store.root).resolve()) or
        not path.is_file() or path.stat().st_size > 8192):
        raise OptimizationBlocked('Candidate-specific expert acknowledgment missing')
    try:
        review_record = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise OptimizationBlocked('Saved candidate review unreadable') from exc
    if (digest(review_record) != submission.review_digest or
        review_record.get('revision_id') != submission.revision_id or
        review_record.get('candidate_digest') != candidate.candidate_digest or
        review_record.get('goal_spec_sha256') != _goal_spec_sha(plan) or
        review_record.get('project_digest') != candidate.project_digest or
        review_record.get('source_revision') != plan.source_revision or
        review_record.get('source_native_run_id') != plan.source_native_run_id or
        review_record.get('source_native_manifest_sha256') != plan.source_native_manifest_sha256 or
        review_record.get('native_lineage') != [list(step) for step in plan.native_lineage] or
        review_record.get('scientific_qualification') != 'NOT_ESTABLISHED' or
        review_record.get('fabrication_status') != 'HOLD'):
        raise OptimizationBlocked('Candidate-specific expert review changed')
    _candidate_review(owner, candidate, review_record['review'])
    _verify_source_native_anchor(store, owner, project_id, plan)
    return study, original['model']


def inspect_saved_geometry_candidate(store, owner: str, project_id: str,
                                    plan: OptimizationPlan, candidate: GeometryPoint,
                                    submission: CandidateRun) -> dict:
    """Read back *actual* operator-reviewed Store CAD without claiming EM results.

    Available even if a native solver is queued/unavailable. A verified CAD
    target/constraint is about a literal model parameter, NOT an EM/QPU metric;
    hence physical goals remain null and the scientific/fabrication gates HOLD.
    """
    study, source_model = _reviewed_candidate_state(
        store, owner, project_id, plan, candidate, submission)
    state = 'NOT_SUBMITTED'
    created = None
    if submission.run_id is not None:
        run = store.run(owner, project_id, submission.run_id)
        if (run['revision_id'] != submission.revision_id or
                run['study_id'] != plan.study_id or run['engine'] != study['engine']):
            raise OptimizationBlocked('CAD candidate native job identity mismatch')
        state, created = run['state'], run['created']
    def result(goal: Goal) -> dict:
        if goal.metric == 'cad.dimension':
            return _cad_dimension_result(goal, source_model, candidate,
                                         submission.revision_id, submission.run_id, None)
        return {'goal': goal.name, 'metric': goal.metric, 'unit': goal.unit,
                'comparison': goal.comparison, 'threshold': goal.threshold,
                'tolerance': goal.tolerance, 'identity': dict(goal.identity),
                'status': 'BLOCKED_NATIVE_PHYSICAL_EVIDENCE_NOT_VERIFIED',
                'value': None, 'feasible': None, 'source_run_id': submission.run_id,
                'source_manifest_sha256': None,
                'scientific_qualification': 'NOT_ESTABLISHED'}
    return {'schema': SCHEMA, 'status': 'VERIFIED_SAVED_CAD_ONLY',
            'source_revision_id': plan.source_revision,
            'source_project_digest': plan.source_project_digest,
            'candidate_revision_id': submission.revision_id,
            'candidate_digest': candidate.candidate_digest,
            'candidate_project_digest': candidate.project_digest,
            'candidate_geometry_digest': candidate.geometry_digest,
            'coordinates': [list(pair) for pair in candidate.coordinates],
            'operator_review_sha256': submission.review_digest,
            'native_submission_status': submission.status,
            'native_run_id': submission.run_id, 'native_run_state': state,
            'native_run_created_unix': created, 'native_runtime_seconds': None,
            'native_runtime_status': 'BLOCKED_NO_NATIVE_FINISH_TIMESTAMP',
            'native_budget_seconds': plan.native_budget_seconds,
            'native_lineage_solves_completed': len(plan.native_lineage),
            'native_lineage_remaining_seconds':
                (MAX_OPTIMIZATION_SOLVES - len(plan.native_lineage)) * NATIVE_SOLVE_BUDGET_SECONDS,
            'objective_results': [result(goal) for goal in plan.objectives],
            'constraint_results': [result(goal) for goal in plan.constraints],
            'mode_matching': 'BLOCKED_UNTIL_COMPLEX_FIELD_OVERLAP',
            'rf_port_mapping': 'BLOCKED_PENDING_EXPERT_REFERENCE_PLANE_REVIEW',
            'scientific_qualification': 'NOT_ESTABLISHED',
            'fabrication_status': 'HOLD'}


def inspect_native_candidate(store, owner: str, project_id: str, plan: OptimizationPlan,
                             candidate: GeometryPoint, submission: CandidateRun) -> dict:
    """Rehash the authorized run and report *gates*, never synthetic fitness.

    Only literal CAD dimensions may receive numeric values/feasibility.
    Native EM, RF and quantum objective numbers are never promoted: matching requires
    independently verified complex overlap; RF objectives need reviewed ports,
    reference planes and complex samples. Future native readers can consume
    this verified binding without changing the immutable project contract.
    """
    study, source_model = _reviewed_candidate_state(
        store, owner, project_id, plan, candidate, submission)
    if submission.run_id is None:
        raise OptimizationBlocked('Native solve was not submitted or is not complete')
    run = store.run(owner, project_id, submission.run_id)
    if (run['revision_id'] != submission.revision_id or run['study_id'] != plan.study_id or
        run['engine'] != study['engine'] or run['state'] != 'completed'):
        raise OptimizationBlocked('Native solve not complete for this candidate revision')
    # Use only authorized Store paths, never a caller-supplied archive location.
    folder = Path(store.root) / 'native-runs' / project_id / submission.run_id
    if (folder.is_symlink() or Path(run['path']).resolve() != folder.resolve() or
        not folder.is_dir()):
        raise OptimizationBlocked('Native job path is outside project-owned run storage')
    snapshot_path = folder / 'snapshot.json'
    if snapshot_path.is_symlink() or not snapshot_path.is_file() or snapshot_path.stat().st_size > 512_000:
        raise OptimizationBlocked('Native worker snapshot missing or unsafe')
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise OptimizationBlocked('Native worker snapshot unreadable') from exc
    if (snapshot.get('expected_adapter_sha256') != adapter_digest(study['engine']) or
        snapshot.get('attempt') != 1 or snapshot.get('retry_of') is not None or
        snapshot.get('revision_id') != submission.revision_id or
        snapshot.get('project_digest') != candidate.project_digest or
        snapshot.get('project') != candidate.project or snapshot.get('study') != study or
        snapshot.get('parents') != [] or 'sweep_plan' in snapshot):
        raise OptimizationBlocked('Native worker did not run the saved candidate snapshot')
    output = folder / 'output'
    try:
        ref = verify_manifest(output, revision_id=submission.revision_id,
                              project_digest=candidate.project_digest,
                              study_id=plan.study_id, engine='sqdmetal_palace')
        expected = fingerprint(revision_id=submission.revision_id,
                               project_digest=candidate.project_digest, study=study,
                               native_version=ref.engine_version,
                               adapter_sha256=adapter_digest(study['engine']))
        expected_type = {'eigenmode': 'palace.eigenmodes',
                         'sparameters': 'palace.sparameters',
                         'capacitance': 'palace.capacitance_matrix'}[study['kind']]
        if ref.cache_fingerprint != expected or ref.artifact_type != expected_type:
            raise OptimizationBlocked('Native fingerprint or numerical artifact type is invalid')
        manifest_raw = (output / 'RESULT_MANIFEST.json').read_bytes()
        if sha_bytes(manifest_raw) != ref.manifest_sha256:
            raise OptimizationBlocked('Native manifest changed during verification')
        manifest = json.loads(manifest_raw)
        if (manifest.get('adapter_sha256') != adapter_digest(study['engine']) or
            manifest.get('kind') != study['kind'] or
            manifest.get('provenance', {}).get('was_generated_by') != study['engine'] or
            'sweep_point' in manifest):
            raise OptimizationBlocked('Native worker identity or solve kind is not authentic')
    except (ArtifactInvalid, OSError, ValueError) as exc:
        raise OptimizationBlocked('Native provenance verification failed: ' + str(exc)) from exc
    # Raw index-labelled Palace frequencies may be displayed to an expert only;
    # they are never assigned to a goal's symbolic mode identity or scored.
    observations = None
    if study['kind'] == 'eigenmode':
        try:
            observations = palace_eigenmodes(output, manifest)
        except (NativeDisplayError, ArtifactInvalid, OSError, ValueError) as exc:
            raise OptimizationBlocked('Native eigenmode observations are invalid') from exc
        if observations is None:
            raise OptimizationBlocked('Native eigenmode observations are missing')

    # Route every requested goal through the saved native study kind. Even
    # verified bytes are NOT an expert-verified port, mode or quantum mapping.
    def gate(goal: Goal) -> dict:
        origin, _, kind = METRICS[goal.metric]
        if kind == 'dimension':
            return _cad_dimension_result(goal, source_model, candidate,
                                         submission.revision_id, submission.run_id,
                                         ref.manifest_sha256)
        required = ('eigenmode' if kind == 'mode' else
                    'sparameters' if kind == 'ports' and origin == 'sqdmetal_palace' else None)
        if origin != 'sqdmetal_palace':
            status = 'BLOCKED_UNREVIEWED_CROSS_ENGINE_MAPPING'
        elif required != study['kind']:
            status = 'BLOCKED_INCOMPATIBLE_NATIVE_STUDY_KIND'
        elif kind == 'mode':
            status = 'BLOCKED_UNVERIFIED_COMPLEX_FIELD_MODE_IDENTITY'
        else:
            status = 'BLOCKED_UNREVIEWED_PORT_AND_REFERENCE_PLANE_IDENTITY'
        return {'goal': goal.name, 'metric': goal.metric, 'unit': goal.unit,
                'comparison': goal.comparison, 'threshold': goal.threshold,
                'tolerance': goal.tolerance, 'identity': dict(goal.identity),
                'status': status, 'value': None, 'feasible': None,
                'source_run_id': submission.run_id,
                'source_manifest_sha256': ref.manifest_sha256}

    # Rev-bound *provenance* is established; physical identity & material/mode
    # qualification remain independent and must not be auto-marked PASS.
    return {'schema': SCHEMA, 'status': 'VERIFIED_NATIVE_ARTIFACT_REVIEW_REQUIRED',
            'revision_id': submission.revision_id, 'candidate_digest': candidate.candidate_digest,
            'project_digest': candidate.project_digest, 'run_id': submission.run_id,
            'native_budget_seconds': plan.native_budget_seconds,
            'planned_native_budget_seconds': plan.planned_native_budget_seconds,
            'native_lineage_solves_completed': len(plan.native_lineage) + 1,
            'native_lineage_budget_seconds': MAX_OPTIMIZATION_NATIVE_SECONDS,
            'native_lineage_remaining_seconds': (MAX_OPTIMIZATION_SOLVES - len(plan.native_lineage) - 1) * NATIVE_SOLVE_BUDGET_SECONDS,
            'operator_review_sha256': submission.review_digest,
            'engine': ref.engine, 'engine_version': ref.engine_version,
            'native_manifest_sha256': ref.manifest_sha256,
            'native_content_sha256': list(ref.content_sha256),
            'native_artifact_type': ref.artifact_type,
            'native_run_state': run['state'], 'native_run_created_unix': run['created'],
            'native_runtime_seconds': None,
            'native_runtime_status': 'BLOCKED_NO_NATIVE_FINISH_TIMESTAMP',
            'geometry_comparison': {'status': 'VERIFIED_CAD_REVISION_DIFF_ONLY',
                                    'source_revision_id': plan.source_revision,
                                    'source_project_digest': plan.source_project_digest,
                                    'candidate_revision_id': submission.revision_id,
                                    'candidate_project_digest': candidate.project_digest,
                                    'candidate_geometry_digest': candidate.geometry_digest,
                                    'coordinates': [list(pair) for pair in candidate.coordinates],
                                    'physical_equivalence': 'NOT_ESTABLISHED'},
            'native_observations_unassigned': observations,
            'source_native_run_id': plan.source_native_run_id,
            'source_native_manifest_sha256': plan.source_native_manifest_sha256,
            'objective_results': [gate(g) for g in plan.objectives],
            'constraint_results': [gate(g) for g in plan.constraints],
            'mode_matching': 'BLOCKED_UNTIL_COMPLEX_FIELD_OVERLAP',
            'rf_port_mapping': 'BLOCKED_PENDING_EXPERT_REFERENCE_PLANE_REVIEW',
            'scientific_qualification': 'NOT_ESTABLISHED', 'fabrication_status': 'HOLD'}



def _revision_mesh_record(store, owner: str, project_id: str, revision: str,
                          project_sha: str, run_id: str, study_id: str) -> dict:
    """Read a single *already verified* native Gmsh mesh, not a mesh surrogate.

    The caller first validates the completed Store run, worker snapshot and
    full SHA-bound output via inspect_native_candidate/native lineage rehash.
    This second read binds the exact mesh member and engine version to the
    same Store revision; it never interprets mesh equality as mode overlap.
    """
    run = store.run(owner, project_id, run_id)
    root = Path(store.root) / 'native-runs' / project_id / run_id
    if (run['revision_id'] != revision or run['study_id'] != study_id or
            run['engine'] != 'sqdmetal_palace' or run['state'] != 'completed' or
            root.is_symlink() or root.resolve() != Path(run['path']).resolve()):
        raise OptimizationBlocked('B10 source/candidate native run identity is stale')
    output = root / 'output'
    try:
        ref = verify_manifest(output, revision_id=revision,
                              project_digest=project_sha, study_id=study_id,
                              engine='sqdmetal_palace')
        raw = (output / 'RESULT_MANIFEST.json').read_bytes()
        if sha_bytes(raw) != ref.manifest_sha256:
            raise OptimizationBlocked('B10 native manifest changed during mesh inspection')
        manifest = json.loads(raw)
        # Never accept an arbitrary unmanifested mesh or guess the identity of
        # one of several geometries from an output directory listing.
        meshes = [entry for entry in manifest['artifacts']
                  if entry['name'].lower().endswith('.msh')]
        if len(meshes) != 1:
            return {'revision_id': revision, 'project_digest': project_sha,
                    'run_id': run_id, 'manifest_sha256': ref.manifest_sha256,
                    'engine_version': ref.engine_version,
                    'mesh_sha256': None, 'mesh_member': None,
                    'mesh_status': 'BLOCKED_NO_UNAMBIGUOUS_VERIFIED_GMSH_MESH'}
        mesh = meshes[0]
        return {'revision_id': revision, 'project_digest': project_sha,
                'run_id': run_id, 'manifest_sha256': ref.manifest_sha256,
                'engine_version': ref.engine_version,
                'mesh_sha256': mesh['sha256'], 'mesh_member': mesh['name'],
                'mesh_status': 'VERIFIED_SHA256_MEMBER_NOT_PHYSICAL_REGISTRATION'}
    except (ArtifactInvalid, OSError, ValueError, KeyError, TypeError) as exc:
        raise OptimizationBlocked('B10 native mesh provenance could not be verified') from exc


def inspect_b10_revision_pair(store, owner: str, project_id: str,
                              plan: OptimizationPlan, candidate: GeometryPoint,
                              submission: CandidateRun) -> dict:
    """Production B10 read-only source/candidate comparison, fail-closed physics.

    Requires two completed, independently submitted, *revision-distinct* Palace
    eigenmode runs and the immutable native lineage recorded before the current
    commit. Actual Gmsh mesh members are identified by their verified file SHA.
    It explicitly does NOT infer mode identity from a shared index, frequency
    closeness, a matching mesh hash or a fixture. Independently reviewed complex
    field registration/mode matching is not currently a certified A11 interface:
    physical metrics are therefore always null and scientific status BLOCKED.

    A15 can call this alongside its real native-run receipt, but must separately
    attest native execution kind, timings and quantitative acceptance. This
    method alone is read-only verification of stored evidence, not fresh solve.
    """
    if (not plan.native_lineage or plan.source_native_run_id is None or
            plan.source_native_manifest_sha256 is None or
            plan.native_lineage[-1][:2] !=
            (plan.source_revision, plan.source_project_digest) or
            plan.native_lineage[-1][2:4] !=
            (plan.source_native_run_id, plan.source_native_manifest_sha256)):
        raise OptimizationBlocked('B10 needs a completed source revision native solve and ledger')
    study = _confirm_candidate(plan, candidate)
    if study['kind'] != 'eigenmode':
        raise OptimizationBlocked('B10 physical mode comparison requires a saved eigenmode study')
    # Reinspect all previous revisions and this candidate; validates owner,
    # optimistic head, reviewed CAD mutation, source/target worker snapshots,
    # solver version/artifact kind/fingerprints and every artifact's SHA-256.
    inspected = inspect_native_candidate(store, owner, project_id, plan,
                                         candidate, submission)
    before = _revision_mesh_record(store, owner, project_id,
                                   plan.source_revision, plan.source_project_digest,
                                   plan.source_native_run_id, plan.study_id)
    after = _revision_mesh_record(store, owner, project_id,
                                  submission.revision_id, candidate.project_digest,
                                  submission.run_id, plan.study_id)
    if before['manifest_sha256'] != plan.source_native_manifest_sha256:
        raise OptimizationBlocked('B10 source native manifest changed after expert review')
    if after['manifest_sha256'] != inspected['native_manifest_sha256']:
        raise OptimizationBlocked('B10 candidate native manifest changed during inspection')
    if not before['mesh_sha256'] or not after['mesh_sha256']:
        blocker = 'BLOCKED_NO_UNAMBIGUOUS_VERIFIED_GMSH_MESH'
    elif before['mesh_sha256'] == after['mesh_sha256']:
        blocker = 'BLOCKED_IDENTICAL_MESH_FOR_CHANGED_CAD_REVISIONS'
    elif before['engine_version'] != after['engine_version']:
        blocker = 'BLOCKED_DIFFERENT_NATIVE_SOLVER_VERSIONS'
    else:
        blocker = 'BLOCKED_INDEPENDENT_COMPLEX_FIELD_REGISTRATION_AND_MODE_IDENTITY_REVIEW'
    return {'schema': 'sqe.b10-locked-revision-pair.v1', 'case_id': 'B10',
            'stage_status': 'BLOCKED', 'blocker': blocker,
            'execution_kind': 'REPLAY_EXISTING_EVIDENCE',
            'native_fresh_execution_this_call': False,
            'source': before, 'candidate': after,
            'geometry_delta': inspected['geometry_comparison'],
            'objective_results': inspected['objective_results'],
            'constraint_results': inspected['constraint_results'],
            'mode_identity': 'UNRESOLVED', 'mode_overlap': None,
            'physical_objectives_evaluated': False,
            'scientific_qualification': 'NOT_ESTABLISHED',
            'fabrication_status': 'HOLD',
            'qualification_note': ('Native mesh member hashes prove source/result file lineage only, '
                                   'not coordinate/FE-basis registration or physically identical modes.')}


def replan_after_native_candidate(store, owner: str, project_id: str,
                                  plan: OptimizationPlan, candidate: GeometryPoint,
                                  submission: CandidateRun, axes: Mapping, *,
                                  objectives: tuple[Goal, ...] | None = None,
                                  constraints: tuple[Goal, ...] | None = None,
                                  mode: str = 'manual', selected: int | None = None) -> OptimizationPlan:
    """Advance one *recorded*, expert-reviewed native iteration, not an optimizer.

    Require full reinspection of the prior source bytes, and bind its manifest
    to the next plan. A second candidate cannot use the former source revision.
    At each step a new operator review and fresh native solve remain mandatory.
    No numerical rank or conditional acceptance is inferred from solver indices.
    """
    evidence = inspect_native_candidate(store, owner, project_id, plan, candidate, submission)
    if evidence['scientific_qualification'] != 'NOT_ESTABLISHED' or any(
            result['value'] is not None for result in
            evidence['objective_results'] + evidence['constraint_results']
            if result['metric'] != 'cad.dimension'):
        raise OptimizationBlocked('Scientific objective scoring cannot be inferred from these artifacts')
    if len(plan.native_lineage) + 1 >= MAX_OPTIMIZATION_SOLVES:
        raise OptimizationBlocked('Three-solve lifetime budget exhausted; independent new study requires review')
    saved = store.project(owner, project_id)
    next_plan = plan_optimization(saved['model'], saved['head'], plan.study_id, axes,
                                  objectives=plan.objectives if objectives is None else objectives,
                                  constraints=plan.constraints if constraints is None else constraints,
                                  mode=mode, selected=selected)
    chain = plan.native_lineage + ((submission.revision_id, candidate.project_digest,
                                    submission.run_id, evidence['native_manifest_sha256'],
                                    submission.review_digest),)
    if len(chain) + len(next_plan.candidates) > MAX_OPTIMIZATION_SOLVES:
        raise OptimizationBlocked('Next geometry plan exceeds remaining three-solve lifetime budget')
    return replace(next_plan, source_native_run_id=submission.run_id,
                   source_native_manifest_sha256=evidence['native_manifest_sha256'],
                   native_lineage=chain)
