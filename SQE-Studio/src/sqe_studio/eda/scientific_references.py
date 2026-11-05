"""M8 literature-anchored *diagnostics* on ordinary, hash-verified Results.

This module does not run solvers, create projects, certify mesh convergence or
transfer Maxwell-derived parameters into a Hamiltonian. The HTTP caller MUST
first authenticate the run and verify every native artifact and its revision.
Numerical comparators apply to ANY compatible saved design; published device
measurements are NEVER treated as a target for an unrelated geometry.
"""
from __future__ import annotations

import math
from copy import deepcopy
from decimal import Decimal, localcontext

from ..contracts import digest

SCHEMA = 'sqe.scientific-reference-diagnostics.m8.v1'
_E = Decimal('1.602176634e-19')
_H = Decimal('6.62607015e-34')

# Metadata is deliberately distinct from the executable numerical checks.
# The numbers below are either literature observations or universally
# evaluated approximations, never precomputed 'native solver' outputs.
CASES = (
    {
        'id': 'T01_KOCH_ASYMPTOTIC', 'family': 'transmon',
        'use_case_id': 'transmon_independent_spectrum', 'readiness': 'conditional_native_numeric',
        'title': 'Transmon spectrum vs Koch high-EJ/EC asymptote',
        'reference': {'authors': 'Koch et al.', 'year': 2007,
                      'title': 'Charge-insensitive qubit design derived from the Cooper pair box',
                      'doi': '10.1103/PhysRevA.76.042319'},
        'oracle_kind': 'LITERATURE_ANALYTIC_APPROXIMATION',
        'method': 'f01 ~= sqrt(8*EJ*EC)-EC; alpha ~= -EC; energies E/h in GHz',
        'applicability': 'Single independent scqubits Transmon, EJ/EC>=40, unswept, >=3 levels; basis check reported separately',
        'tolerances': {'f01_relative': 0.05, 'anharmonicity_relative': 0.20},
        'science_boundary': 'Asymptotic sanity check only; not measured device agreement or EM-derived circuit parameters',
    },
    {
        'id': 'T02_MAXWELL_CHARGING_UNITS', 'family': 'transmon',
        'use_case_id': 'transmon_independent_spectrum', 'readiness': 'conditional_matrix_numeric',
        'title': 'Matrix-only effective capacitance and charge energy',
        'reference': {'authors': 'Koch et al.', 'year': 2007,
                      'title': 'Charge-insensitive qubit design derived from the Cooper pair box',
                      'doi': '10.1103/PhysRevA.76.042319'},
        'oracle_kind': 'INDEPENDENT_SI_UNIT_CONVERSION',
        'method': 'E_C/h = e^2/(2*h*C_eff), using exact SI e and h',
        'applicability': 'Saved revision-bound B04 transmon topology and Maxwell matrix-only reduction',
        'tolerances': {'ec_relative': 0.000001},
        'science_boundary': 'Only a unit/constant cross-check of the same numerical C_eff; not independent EM validation, mesh convergence or scqubits transfer',
    },
    {
        'id': 'R01_GOPPL_CPW_2008', 'family': 'resonator',
        'use_case_id': 'cpw_resonator_eigenmode', 'readiness': 'reference_requires_geometry_replication',
        'title': 'Published half-wave CPW resonator geometry/frequency',
        'reference': {'authors': 'Goppl et al.', 'year': 2008,
                      'title': 'Coplanar waveguide resonators for circuit quantum electrodynamics',
                      'doi': '10.1063/1.3010859'},
        'oracle_kind': 'PUBLISHED_DEVICE_MEASUREMENT',
        'published': {'resonator_length_mm': 14.220, 'measured_f0_GHz': 4.6846},
        'method': 'For matched geometry only: half-wave estimate f0 ~= c/(2*l*sqrt(epsilon_eff))',
        'applicability': 'Requires independent verification of substrate, center/gap, CPW ends, coupling, boundary conditions, materials and physical mode identity',
        'tolerances': {'frequency_relative_provisional': 0.05},
        'science_boundary': 'Cannot automatically compare an arbitrary editable CPW to the published device',
    },
    {
        'id': 'R02_CPW_LENGTH_SCALING', 'family': 'resonator',
        'use_case_id': 'cpw_resonator_eigenmode',
        'readiness': 'conditional_pairwise_native_numeric',
        'title': 'CPW length-frequency scaling across two verified Palace runs',
        'reference': {'authors': 'Goppl et al.', 'year': 2008,
                      'title': 'Coplanar waveguide resonators for circuit quantum electrodynamics',
                      'doi': '10.1063/1.3010859'},
        'oracle_kind': 'LITERATURE_TRANSMISSION_LINE_SCALING',
        'method': 'Eq. (1): at fixed effective permittivity and end conditions, f_right/f_left ~= length_left/length_right',
        'applicability': 'Cross-run Results of two saved, verified Palace eigenmodes; exactly one editable CPW route length changes; otherwise identical design and native study',
        'tolerances': {'frequency_ratio_relative_provisional': 0.15},
        'science_boundary': 'NUMERICAL_SCREEN only; no field-matched mode identity, mesh convergence, matched published device or fabrication approval',
    },
    {
        'id': 'R03_PALACE_MESH_REFINEMENT', 'family': 'resonator',
        'use_case_id': 'cpw_resonator_eigenmode',
        'readiness': 'conditional_three_native_run_index_diagnostic',
        'title': 'Three verified native EM eigenmode mesh-refinement diagnostics',
        'reference': {'authors': 'Celik et al.', 'year': 2008,
                      'title': 'Procedure for estimation and reporting of uncertainty due to discretization in CFD applications',
                      'doi': '10.1115/1.2960953'},
        'oracle_kind': 'THREE_RUN_NUMERICAL_REFINEMENT_SCREEN',
        'method': ('For three unchanged physical models with coarse/medium/fine meshes, '
                   'compare consecutive native eigenfrequency index drifts; '
                   'requires independently validated field overlaps before mode convergence'),
        'applicability': ('Results cross-run comparison with three completed SHA-verified '
                          'Palace eigenmode runs; mesh sizes change, all other inputs fixed'),
        'tolerances': None,
        'science_boundary': ('No fixed percentage is a scientific acceptance without validated '
                             'complex-field overlap mode identity, actual mesh statistics and physical review; '
                             'no extrapolation or fabrication approval; Celik is a general discretization-uncertainty methodology, not a CPW EM validation'),
    },
    {
        'id': 'R04_PALACE_COMPLEX_FIELD_LINEAGE', 'family': 'resonator',
        'use_case_id': 'cpw_resonator_eigenmode',
        'readiness': 'conditional_sha_verified_native_field_format',
        'title': 'Native eigenfield provenance before cross-mesh mode correlation',
        'reference': {'authors': 'Allemang and Brown', 'year': 1982,
                      'title': 'A correlation coefficient for modal vector analysis',
                      'url': 'https://cir.nii.ac.jp/crid/1572261549345496448',
                      'palace_export_guide': 'https://awslabs.github.io/palace/stable/guide/postprocessing/'},
        'oracle_kind': 'FIELD_EXPORT_LINEAGE_AND_REGISTRATION_READINESS',
        'method': ('Verify PVD/PVTU/VTU SHA provenance and complex E-component declarations '
                   'from revision-bound Palace runs before any field-overlap comparison'),
        'applicability': ('Any saved SHA-verified Palace eigenmode run, with optional two/three '
                          'run comparison using the existing Results UI'),
        'tolerances': None,
        'science_boundary': ('An eigenfield inventory is not a MAC matrix or physical mode identity; '
                             'no coordinate registration, phase normalization, H(curl) projection, '
                             'scientific convergence, EPR or fabrication approval'),
    },
    {
        'id': 'R05_PALACE_CROSS_MESH_VISUALIZATION_DIAGNOSTIC',
        'family': 'resonator', 'use_case_id': 'cpw_resonator_eigenmode',
        'readiness': 'conditional_small_single_piece_verified_native_pair',
        'title': 'Diagnostic phase-invariant visualization field comparison across two meshes',
        'reference': {'authors': 'Allemang and Brown', 'year': 1982,
                      'title': 'A correlation coefficient for modal vector analysis',
                      'url': 'https://cir.nii.ac.jp/crid/1572261549345496448'},
        'oracle_kind': 'BOUNDED_CROSS_MESH_VISUALIZATION_L2_DIAGNOSTIC',
        'method': ('For two revision- and SHA-verified Palace runs with identical nonmesh inputs, '
                   'use an existing bounded barycentric VTK PointData vector interpolation; '
                   'an unambiguous single-cycle, single-piece source is required'),
        'applicability': ('Results cross-run comparison for any supported native eigenmode layout, '
                          'with explicit reporting of MPI, multi-cycle and interpolation blockers'),
        'tolerances': None,
        'science_boundary': ('Complex visualization L2 is not material-weighted H(curl) MAC. '
                             'PVD cycle is not mode identity, field coordinates are not independently registered; '
                             'never authorizes physical convergence, EPR or fabrication'),
    },
    {
        'id': 'J01_KAUFMAN_2023', 'family': 'amplifier',
        'use_case_id': 'josephson_rf_amplifier', 'readiness': 'blocked_missing_native_edge',
        'title': 'Broadband Chebyshev JPA gain profile',
        'reference': {'authors': 'Kaufman et al.', 'year': 2023,
                      'title': 'Josephson parametric amplifier with Chebyshev gain profile and high saturation',
                      'doi': '10.1103/PhysRevApplied.20.054058'},
        'oracle_kind': 'PUBLISHED_DEVICE_MEASUREMENT',
        'published': {'center_frequency_GHz': 4.6, 'gain_dB': 20.0,
                      'gain_ripple_dB_less_than': 1.0, 'bandwidth_MHz_up_to': 500.0},
        'method': 'Requires valid pump/harmonic-balance netlist and calibrated port reference planes',
        'applicability': 'Only a physically equivalent matching network and bias; no generic RF amplifier target',
        'tolerances': None,
        'science_boundary': 'Schematic-to-JosephsonCircuits native edge is blocked; never synthesize a gain curve',
    },
    {
        'id': 'E01_MINEV_EPR_2021', 'family': 'multi_qubit',
        'use_case_id': 'epr_transmon_resonator', 'readiness': 'blocked_missing_native_edge',
        'title': 'Junction energy-participation quantization',
        'reference': {'authors': 'Minev et al.', 'year': 2021,
                      'title': 'Energy-participation quantization of Josephson circuits',
                      'doi': '10.1038/s41534-021-00461-8'},
        'oracle_kind': 'PUBLISHED_METHOD_REQUIREMENTS',
        'method': 'Check normalized field energies, EPR participation and Hamiltonian against converged native fields',
        'applicability': 'Review junction identities and mode-overlap identity before comparison',
        'tolerances': None,
        'science_boundary': 'EM-to-Hamiltonian bridge not qualified',
    },
)


def list_reference_cases() -> list[dict]:
    """Public read-only catalog, with no magic project or engine implementation."""
    return deepcopy(CASES)


def _number(value):
    if type(value) not in (float, int):
        return None
    x = float(value)
    return x if math.isfinite(x) else None


def _row(case, status, reason, *, measurements=None, checks=None, basis=None):
    return {'case_id': case['id'], 'oracle_kind': case['oracle_kind'],
            'status': status, 'reason': reason, 'measurements': measurements or {},
            'checks': checks or [], 'basis_convergence': basis or 'NOT_ESTABLISHED',
            'physical_validation': 'NOT_ESTABLISHED', 'fabrication': 'HOLD'}


def compare_transmon_asymptote(ej, ec, levels):
    """Shared Koch numerical comparator; makes no statement about input origin."""
    if (type(ej) not in (int,float) or type(ec) not in (int,float) or
            not math.isfinite(ej) or not math.isfinite(ec) or ec<=0 or ej/ec<40):
        return {'status':'NOT_APPLICABLE','reason':'Koch high-EJ/EC approximation requires EJ/EC >= 40','checks':[],
                'reference':'https://doi.org/10.1103/PhysRevA.76.042319','physical_validation':'NOT_ESTABLISHED'}
    if (not isinstance(levels,list) or len(levels)<3 or
            any(type(x) not in (int,float) or not math.isfinite(x) for x in levels[:3]) or
            not levels[0]<levels[1]<levels[2]):
        raise ValueError('Ordered finite native levels required for Koch comparison')
    row=levels[:3]
    case=next(c for c in CASES if c['id']=='T01_KOCH_ASYMPTOTIC')
    f01 = row[1] - row[0]
    alpha = row[2] - 2*row[1] + row[0]
    f_approx = math.sqrt(8*ej*ec) - ec
    err_f = abs(f01 - f_approx) / f_approx
    err_alpha = abs(alpha + ec) / ec
    checks = [{'quantity': 'f01', 'unit': 'GHz', 'actual': f01,
               'reference': f_approx, 'relative_error': err_f,
               'relative_tolerance': case['tolerances']['f01_relative'],
               'pass': err_f <= case['tolerances']['f01_relative']},
              {'quantity': 'anharmonicity', 'unit': 'GHz', 'actual': alpha,
               'reference': -ec, 'relative_error': err_alpha,
               'relative_tolerance': case['tolerances']['anharmonicity_relative'],
               'pass': err_alpha <= case['tolerances']['anharmonicity_relative']}]
    return {'status':'NUMERICAL_PASS' if all(c['pass'] for c in checks) else 'NUMERICAL_FAIL',
            'checks':checks,'EJ_over_EC':ej/ec,
            'reference':'https://doi.org/10.1103/PhysRevA.76.042319',
            'scope':'Literature asymptote for this conditional Hamiltonian; not a reproduced device measurement',
            'physical_validation':'NOT_ESTABLISHED'}


def _transmon(case, project, manifest, spectrum):
    if manifest.get('artifact_type') != 'scqubits.spectrum' or manifest.get('engine') != 'scqubits':
        return _row(case, 'NOT_APPLICABLE', 'Run is not an independently specified scqubits spectrum')
    studies = [s for s in project['model'].get('studies', ()) if s.get('id') == manifest.get('study_id')]
    if len(studies) != 1 or studies[0].get('engine') != 'scqubits':
        return _row(case, 'BLOCKED', 'Matching revision-bound quantum study unavailable')
    inputs = studies[0].get('inputs', {})
    if not isinstance(inputs, dict) or not isinstance(spectrum, dict):
        return _row(case, 'BLOCKED', 'No verified native spectrum and stored study')
    # An output with mismatched native input digest cannot be compared.
    if (spectrum.get('input_sha256') != digest(inputs) or
            spectrum.get('schema') != 'sqe.scqubits.spectrum.v1' or
            spectrum.get('model') != inputs.get('model') or
            inputs.get('source', 'independent') != 'independent'):
        return _row(case, 'BLOCKED', 'Native model/source/input SHA-256 does not match immutable study')
    if inputs.get('model') in ('Fluxonium', 'TunableTransmon', 'Composite'):
        return _row(case, 'NOT_APPLICABLE',
                    'T01 applies to a standalone Transmon; this verified native model uses a different Hamiltonian',
                    basis='NOT_APPLICABLE')
    if inputs.get('model') != 'Transmon':
        return _row(case, 'BLOCKED', 'Unsupported native quantum model')
    p = inputs.get('parameters', {})
    if not isinstance(p, dict) or not isinstance(inputs.get('parameter_units'), dict):
        return _row(case, 'BLOCKED', 'Hamiltonian parameters and units not explicitly declared')
    ej, ec = _number(p.get('EJ')), _number(p.get('EC'))
    if (ej is None or ec is None or ec <= 0 or ej / ec < 40 or
            inputs.get('sweep') is not None or spectrum.get('axis') is not None or
            spectrum.get('units') != 'GHz' or spectrum.get('energy_unit') != 'GHz' or
            spectrum.get('preview_point_index') != 0 or
            inputs.get('parameter_units', {}).get('EJ') != 'GHz' or
            inputs.get('parameter_units', {}).get('EC') != 'GHz'):
        return _row(case, 'BLOCKED', 'Expected unswept high-EJ/EC Transmon with explicit GHz units')
    levels = spectrum.get('levels')
    if not isinstance(levels, list) or len(levels) < 3 or len(levels) > 12:
        return _row(case, 'BLOCKED', 'At least three native eigenlevels required')
    row = [_number(x) for x in levels[:3]]
    if any(x is None for x in row) or row[0] >= row[1] or row[1] >= row[2]:
        return _row(case, 'BLOCKED', 'Invalid ordered native eigenenergies')
    checks = compare_transmon_asymptote(ej, ec, levels)['checks']
    convergence = spectrum.get('convergence', {})
    basis = ('SINGLE_EXPANSION_CHECKED' if isinstance(convergence, dict) and
             convergence.get('status') == 'checked_passed' else 'NOT_CHECKED')
    if isinstance(convergence, dict) and convergence.get('steps', 1) > 1:
        basis = ('MULTI_EXPANSION_CHECKED' if convergence.get('status') == 'checked_passed'
                 else 'NOT_CONVERGED')
    return _row(case, 'NUMERICAL_PASS' if all(c['pass'] for c in checks) else 'NUMERICAL_FAIL',
                'Koch high-EJ/EC analytic approximation against verified native eigenenergies; not a physical device qualification',
                measurements={'EJ_over_EC': ej/ec, 'input_digest': digest(inputs)},
                checks=checks, basis=basis)


def _capacitance(case, manifest, screen):
    if manifest.get('artifact_type') != 'palace.capacitance_matrix':
        return _row(case, 'NOT_APPLICABLE', 'Run is not a native Maxwell capacitance matrix')
    if not isinstance(screen, dict) or screen.get('status') != 'NUMERICAL_SCREEN_ONLY':
        return _row(case, 'BLOCKED', 'Missing revision-bound transmon selection or valid native reduction')
    reduction = screen.get('reduction')
    preview = reduction.get('numerical_preview') if isinstance(reduction, dict) else None
    if (not isinstance(preview, dict) or reduction.get('status') != 'NUMERICAL_SCREEN_ONLY' or
            screen.get('scqubits_EC_transfer') != 'BLOCKED_NOT_REVIEWED'):
        return _row(case, 'BLOCKED', 'Untrusted Maxwell reduction or unexpected physical authorization')
    cap = _number(preview.get('effective_capacitance_f'))
    actual = _number(preview.get('ec_over_h_hz_matrix_only'))
    if cap is None or actual is None or cap <= 0 or actual <= 0:
        return _row(case, 'BLOCKED', 'Invalid finite native matrix-only capacitance/energy')
    with localcontext() as ctx:
        ctx.prec = 40
        calculated = float(_E*_E/(2*_H*Decimal(str(cap))))
    rel = abs(actual-calculated)/calculated
    check = {'quantity': 'EC_over_h_matrix_only', 'unit': 'Hz', 'actual': actual,
             'reference': calculated, 'relative_error': rel,
             'relative_tolerance': case['tolerances']['ec_relative'],
             'pass': rel <= case['tolerances']['ec_relative']}
    return _row(case, 'NUMERICAL_PASS' if check['pass'] else 'NUMERICAL_FAIL',
                'Independent SI constant/unit conversion for the same unreviewed matrix-only capacitance',
                checks=[check], measurements={'effective_capacitance_f': cap,
                                              'scqubits_EC_transfer': 'BLOCKED'})


def evaluate_verified_result(*, project: dict, manifest: dict, spectrum=None,
                             transmon_screen=None) -> dict:
    """Run ONLY after authenticated revision + native output SHA checks.

    Never accepts client-provided targets, comparison declarations, or arbitrary
    output paths. The Results caller provides an already verified Store project.
    """
    if (manifest.get('revision_id') != project.get('revision') or
            manifest.get('project_digest') != project.get('revision_digest')):
        raise ValueError('Scientific diagnostic source revision/digest mismatch')
    rows = []
    for case in CASES:
        if case['id'] == 'T01_KOCH_ASYMPTOTIC':
            rows.append(_transmon(case, project, manifest, spectrum))
        elif case['id'] == 'T02_MAXWELL_CHARGING_UNITS':
            rows.append(_capacitance(case, manifest, transmon_screen))
        elif case['id'] == 'R02_CPW_LENGTH_SCALING':
            # The current single-run reader cannot evaluate a length ratio.
            # Real verification is on the generic authenticated pair endpoint.
            matches = project['model'].get('family') == 'resonator'
            rows.append(_row(case, 'BLOCKED' if matches else 'NOT_APPLICABLE',
                             ('Select two verified native Palace CPW runs in Expert cross-run comparison'
                              if matches else 'This reference belongs to another device family')))
        else:
            family = project['model'].get('family')
            matches = case['family'] == family
            rows.append(_row(case, 'BLOCKED' if matches else 'NOT_APPLICABLE',
                             ('Published-device/method reference is catalogued; required identical geometry, native bridge or physical review not established'
                              if matches else 'This reference belongs to another device family')))
    return {'schema': SCHEMA,
            'provenance': {'revision_id': manifest['revision_id'],
                           'project_digest': manifest['project_digest'],
                           'study_id': manifest['study_id'],
                           'artifact_type': manifest['artifact_type']},
            'evaluations': rows,
            'numeric_pass_not_scientific_approval': True,
            'scientific_qualification': 'NOT_ESTABLISHED',
            'fabrication': 'HOLD'}
