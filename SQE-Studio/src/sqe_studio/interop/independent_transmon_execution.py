"""Pure M5 preflight for an *already saved* independent Transmon study.

A99 MUST obtain ``trusted_revision`` with authenticated, owner-scoped
``Store.project(owner, project_id)`` (current head, not a client-provided
snapshot), and MUST perform the same head check again before enqueuing a job.
This function does not authenticate its caller: a dictionary manufactured by
an untrusted client is NOT a trusted revision context. A99 must never expose
``trusted_revision`` as a request-body field.

Only the dedicated M4 server-created ``independent_transmon_NN`` study shape
is eligible. The M4 store does not contain an unforgeable manual-entry
attestation; name/structure checks cannot prove real-world scalar origin or
that a generic project commit did not mimic the M4 study. A99 must preserve
that separate trusted *creation-path* gate before issuing a real job.

This builder never runs scqubits, writes a project, reads EM results, promotes
Palace E_C, signs scientific review, or relaxes fabrication HOLD. READY means
syntax/identity software preflight only, not physical approval.
"""
from __future__ import annotations

import copy
import re

from sqe_studio.contracts import ValidationError, digest, validate_project
from .transmon_quantum_preflight import (
    DECLARATION_SCHEMA, TransmonPreflightBlocked,
    build_independent_transmon_preflight,
)

REQUEST_SCHEMA = 'sqe.independent-transmon-execution-request.a12.v1'
PREFLIGHT_SCHEMA = 'sqe.independent-transmon-execution-preflight.a12.v1'
_REQUEST_KEYS = frozenset({'schema', 'project_id', 'expected_revision', 'study_id'})
_CONTEXT_KEYS = frozenset({'id', 'name', 'head', 'revision', 'parent',
                           'revision_digest', 'model'})
_HEX_ID = re.compile(r'[0-9a-f]{32}\Z')
_HEX_DIGEST = re.compile(r'[0-9a-f]{64}\Z')
_M4_STUDY = re.compile(r'independent_transmon_(?:0[1-9]|[12][0-9]|30)\Z')


class IndependentTransmonExecutionBlocked(ValueError):
    """No execution-request specification can be produced."""

    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code


def _block(code: str, reason: str) -> None:
    raise IndependentTransmonExecutionBlocked(code, reason)


def _id(value: object, pattern: re.Pattern[str]) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def build_independent_transmon_execution_preflight(
    request: object, *, trusted_revision: object,
) -> dict[str, object]:
    """Return a safe **not executed** software-job request for a saved study.

    ``request`` is an *untrusted selector only*::

        {"schema": REQUEST_SCHEMA, "project_id": "<32 lowercase hex>",
         "expected_revision": "<32 lowercase hex>",
         "study_id": "independent_transmon_01"}

    ``trusted_revision`` is the exact response of the authenticated and
    owner-scoped ``Store.project(owner, project_id)`` for the **current head**,
    supplied server-side by A99. This does not grant the right to execute, and
    a caller-built lookalike is not an acceptable substitute. No client-sent
    parameters, context, reviewer claims or EM artifacts are admitted.

    The result can only inform a FUTURE A99 job path. A99 must re-read the
    owner-scoped head atomically at enqueue time, enforce the dedicated M4
    save-origin boundary, and revalidate frozen adapter inputs. It must NOT
    equate declared ``source=independent`` with scientific authorization.
    """
    if type(request) is not dict or set(request) != _REQUEST_KEYS:
        _block('INVALID_REQUEST_SHAPE', 'Require only schema, project_id, expected_revision, study_id')
    if type(request['schema']) is not str or request['schema'] != REQUEST_SCHEMA:
        _block('INVALID_REQUEST_SCHEMA', 'Unsupported execution-request schema')
    if not _id(request['project_id'], _HEX_ID):
        _block('INVALID_PROJECT_ID', 'Project identity must be exact lowercase store ID')
    if not _id(request['expected_revision'], _HEX_ID):
        _block('INVALID_REVISION', 'Expected revision must be exact lowercase store ID')
    if not _id(request['study_id'], _M4_STUDY):
        _block('UNTRUSTED_STUDY_ORIGIN', 'Only the dedicated M4 independent Transmon saved-study IDs are eligible')

    # This is structural inspection of A99-supplied Store.project output, NOT
    # a cryptographic authentication of who supplied the mapping. That trust
    # boundary is deliberately outside this pure module.
    if type(trusted_revision) is not dict or set(trusted_revision) != _CONTEXT_KEYS:
        _block('UNTRUSTED_REVISION_CONTEXT', 'A99 must supply exact owner-scoped Store.project context')
    if (not _id(trusted_revision['id'], _HEX_ID)
            or not _id(trusted_revision['head'], _HEX_ID)
            or not _id(trusted_revision['revision'], _HEX_ID)
            or not _id(trusted_revision['revision_digest'], _HEX_DIGEST)
            or (trusted_revision['parent'] is not None and
                not _id(trusted_revision['parent'], _HEX_ID))):
        _block('UNTRUSTED_REVISION_CONTEXT', 'Malformed saved Store revision identifiers')
    if (trusted_revision['id'] != request['project_id']
            or trusted_revision['head'] != trusted_revision['revision']
            or trusted_revision['head'] != request['expected_revision']):
        _block('STALE_OR_MISMATCHED_REVISION', 'Project, current head and requested saved revision must match exactly')

    model = trusted_revision['model']
    if type(model) is not dict or type(trusted_revision['name']) is not str:
        _block('UNTRUSTED_REVISION_CONTEXT', 'Missing stored model/name')
    try:
        validate_project(model)
        actual_digest = digest(model)
    except (ValidationError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        _block('UNTRUSTED_REVISION_CONTEXT', 'Saved project model is invalid')
    if (actual_digest != trusted_revision['revision_digest']
            or model['name'] != trusted_revision['name']):
        _block('REVISION_DIGEST_MISMATCH', 'Saved snapshot contents do not match Store revision digest/name')
    if model['family'] not in ('transmon', 'multi_qubit'):
        _block('UNSUPPORTED_DESIGN_FAMILY', 'Manual independent Transmon requires a transmon design family')

    # Never choose a study by list index, kind alone, or a reported result.
    matches = [row for row in model['studies'] if row['id'] == request['study_id']]
    if len(matches) != 1:
        _block('SAVED_STUDY_NOT_FOUND', 'Exact saved independent Transmon study is missing')
    study = matches[0]
    if (type(study) is not dict or set(study) != {'id', 'engine', 'kind', 'inputs'}
            or type(study['engine']) is not str or study['engine'] != 'scqubits'
            or type(study['kind']) is not str or study['kind'] != 'quantum_spectrum'):
        _block('UNTRUSTED_STUDY_SHAPE', 'Saved study must use the frozen scqubits quantum_spectrum contract')
    inputs = study['inputs']
    if type(inputs) is not dict:
        _block('UNTRUSTED_STUDY_SHAPE', 'Saved study inputs must be an explicit mapping')

    # Reuse A12 M3's more restrictive manual declaration gate. The only
    # approved data source is exact scalar inputs *read from this revision*.
    # In particular adapter-optional EM lineage, review, context hashes,
    # sweeps and user assertions are not permitted for this M4 study path.
    declaration = {'schema': DECLARATION_SCHEMA, **inputs}
    try:
        preliminary = build_independent_transmon_preflight(declaration)
    except TransmonPreflightBlocked as exc:
        _block('SAVED_PARAMETERS_BLOCKED', f'Saved independent declaration rejected: {exc.code}')
    expected_inputs = preliminary['study_template']['inputs']
    # Freshly normalized data is a *plan*, never a replacement for the saved
    # study or a scientific result. No borrowed input hash can self-approve.
    plan_inputs = copy.deepcopy(expected_inputs)
    return {
        'schema': PREFLIGHT_SCHEMA,
        'status': 'READY_FOR_SOFTWARE_EXECUTION_ONLY',
        'target': {
            'project_id': trusted_revision['id'],
            'revision': trusted_revision['revision'],
            'revision_digest': actual_digest,
            'study_id': study['id'],
            'engine': 'scqubits',
            'kind': 'quantum_spectrum',
            'saved_input_sha256': digest(inputs),
        },
        'adapter_invocation_plan': {
            'engine': 'scqubits',
            'kind': 'quantum_spectrum',
            'inputs': plan_inputs,
            'input_contract': 'FROZEN_SCQUBITS_TRANSMON_INDEPENDENT',
            'energy_unit': 'GHz',
            'energy_convention': 'E_OVER_H',
            'ng_unit': '2e',
        },
        'study_source': 'EXACT_SAVED_REVISION_MANUAL_DECLARATION_UNVERIFIED_ORIGIN',
        'trusted_context_requirement': 'A99_AUTHENTICATED_OWNER_SCOPED_STORE_HEAD_AND_M4_SAVE_PATH',
        'saved_revision_mutation': 'NONE',
        'solver_execution': 'NOT_EXECUTED',
        'native_solver_evidence': 'NONE',
        'scientific_authorization': 'BLOCKED_INDEPENDENT_EXPERT_REVIEW_REQUIRED',
        'b04_approval': 'BLOCKED',
        'em_ec_transfer': 'BLOCKED',
        'em_to_hamiltonian': 'BLOCKED',
        'fabrication': 'HOLD',
    }
