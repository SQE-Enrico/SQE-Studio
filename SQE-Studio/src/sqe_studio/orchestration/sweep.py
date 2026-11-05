"""Bounded declarative sweep plans: no optimizer, arbitrary code or solver."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from itertools import product
import math
import re
from typing import Mapping
from ..contracts import digest

MAX_SWEEP_POINTS = 24
_AXIS = re.compile(r'^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*){0,3}$')


@dataclass(frozen=True)
class Point:
    index: int
    study: dict
    options_digest: str
    coordinates: tuple[tuple[str, float], ...]


def plan_sweep(study: Mapping, axes: Mapping, *, mode: str = 'manual',
               selected: int | None = None) -> tuple[Point, ...]:
    """Enumerate numeric substitutions of *existing* saved study fields.

    The complete modified study, coordinates and option digest are preserved
    in the immutable run snapshot. Manual mode runs exactly one selected point;
    automatic mode runs sequentially within one bounded native job.
    """
    if mode not in ('manual', 'automatic') or not isinstance(axes, dict) or not 1 <= len(axes) <= 3:
        raise ValueError('Sweep requires 1-3 numeric axes and manual/automatic mode')
    if not isinstance(study, dict) or not isinstance(study.get('inputs'), dict):
        raise ValueError('Sweep requires a saved declarative study')
    keys = sorted(axes)
    grid = []
    for axis in keys:
        values = axes[axis]
        if not isinstance(axis, str) or not _AXIS.fullmatch(axis) or not isinstance(values, list) or not 1 <= len(values) <= MAX_SWEEP_POINTS:
            raise ValueError('Sweep axis/values invalid')
        target = study['inputs']
        for segment in axis.split('.'):
            if not isinstance(target, dict) or segment not in target:
                raise ValueError('Sweep axis must reference an existing study input: ' + axis)
            target = target[segment]
        if type(target) not in (float, int) or type(target) is bool:
            raise ValueError('Sweep axis requires a numeric saved input: ' + axis)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError('Sweep points must be finite numeric values')
        grid.append(values)
    count = math.prod(map(len, grid))
    if count > MAX_SWEEP_POINTS:
        raise ValueError('Sweep exceeds laptop point limit')
    if mode == 'manual' and (type(selected) is not int or not 0 <= selected < count):
        raise ValueError('Manual sweep requires one selected point index')
    if mode == 'automatic' and selected is not None:
        raise ValueError('Automatic sweep does not accept a point selection')
    points = []
    for index, values in enumerate(product(*grid)):
        if mode == 'manual' and index != selected:
            continue
        new_study = deepcopy(study)
        for axis, value in zip(keys, values):
            target = new_study['inputs']
            path = axis.split('.')
            for segment in path[:-1]:
                target = target[segment]
            target[path[-1]] = value
        coordinates = tuple(zip(keys, values))
        points.append(Point(index, new_study, digest({'study': new_study, 'coordinates': coordinates}), coordinates))
    return tuple(points)


# Geometry is a project revision, not a per-study option.  The production
# native runner must be called only *after* each candidate is committed.
@dataclass(frozen=True)
class GeometryPoint:
    index: int
    source_revision: str
    source_project_digest: str
    project: dict
    project_digest: str
    geometry_digest: str
    coordinates: tuple[tuple[str, float], ...]
    candidate_digest: str


def _geometry_target(model: dict, path: str) -> tuple[dict, str, str]:
    """Resolve a named, existing QDesign dimension; never use list indices/code."""
    segments = path.split('.')
    if segments[:2] == ['layout', 'chip'] and len(segments) == 3:
        node = model['layout']['chip']
        field = segments[2]
        if field not in ('width_mm', 'height_mm', 'thickness_um'):
            raise ValueError('Only physical chip dimensions may be varied')
    elif (len(segments) in (4, 5) and segments[:2] == ['layout', 'components']
          and _AXIS.fullmatch(segments[2]) and segments[2] != 'options'):
        matches = [c for c in model['layout']['components']
                   if isinstance(c, dict) and c.get('name') == segments[2]]
        if len(matches) != 1:
            raise ValueError('Geometry parameter requires one uniquely named component')
        node = matches[0]
        if len(segments) == 5:
            if segments[3] != 'options' or not isinstance(node.get('options'), dict):
                raise ValueError('Only existing dimension options can be varied')
            node = node['options']
        elif segments[3] in ('name', 'kind'):
            raise ValueError('Component identity is not a geometry dimension')
        field = segments[-1]
        if not field.endswith(('_mm', '_um', '_nm')):
            raise ValueError('Only explicit unit-bearing component dimensions are supported')
    else:
        raise ValueError('Geometry axis must target a named layout dimension')
    if field not in node or type(node[field]) not in (int, float) or not math.isfinite(node[field]):
        raise ValueError('Geometry dimension must already be a finite numeric value')
    unit = field.rsplit('_', 1)[-1]
    return node, field, unit


def plan_geometry_sweep(project: Mapping, source_revision: str, axes: Mapping, *,
                        mode: str = 'manual', selected: int | None = None) -> tuple[GeometryPoint, ...]:
    """Prepare distinct, bounded full-project geometry snapshots, *not* solver results.

    Axis example: {'layout.components.R1.options.trace_width_um':
                   {'unit':'um','lower':5,'upper':20,'values':[8,10]}}.
    The caller must save each snapshot as a new immutable revision, then force
    a native solve for that revision. No scientific score is generated here.
    """
    from ..contracts import validate_project

    if (type(source_revision) is not str or not source_revision.strip() or
        type(project) is not dict):
        raise ValueError('Saved project and source revision required')
    validate_project(project)
    if mode not in ('manual', 'automatic') or type(axes) is not dict or not 1 <= len(axes) <= 3:
        raise ValueError('Geometry sweep requires 1-3 axes and manual/automatic mode')
    keys = sorted(axes)
    grid = []
    for path in keys:
        if type(path) is not str or len(path) > 180:
            raise ValueError('Invalid geometry dimension path')
        _, field, expected_unit = _geometry_target(project, path)
        entry = axes[path]
        if type(entry) is not dict or set(entry) != {'unit', 'lower', 'upper', 'values'}:
            raise ValueError('Geometry axis requires explicit unit, bounds and values')
        lower, upper, values = entry['lower'], entry['upper'], entry['values']
        if (entry['unit'] != expected_unit or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in (lower, upper)) or
            lower > upper or type(values) is not list or not 1 <= len(values) <= MAX_SWEEP_POINTS or
            any(type(v) not in (int, float) or not math.isfinite(v) or not lower <= v <= upper for v in values) or
            len({float(v) for v in values}) != len(values)):
            raise ValueError('Invalid unit, finite bounds or distinct geometry values')
        if field not in ('x_mm', 'y_mm') and (lower <= 0 or any(v <= 0 for v in values)):
            raise ValueError('Physical length dimensions must remain positive')
        grid.append(values)
    count = math.prod(map(len, grid))
    if count > MAX_SWEEP_POINTS:
        raise ValueError('Geometry sweep exceeds laptop point budget')
    if mode == 'manual' and (type(selected) is not int or not 0 <= selected < count):
        raise ValueError('Manual geometry sweep requires selected point')
    if mode == 'automatic' and selected is not None:
        raise ValueError('Automatic geometry sweep does not accept point selection')
    original_digest = digest(project)
    original_geometry = digest({'layout': project['layout'], 'process': project['process']})
    points, seen = [], set()
    for index, values in enumerate(product(*grid)):
        if mode == 'manual' and index != selected:
            continue
        candidate = deepcopy(project)
        for path, value in zip(keys, values):
            node, field, _ = _geometry_target(candidate, path)
            node[field] = value
        validate_project(candidate)
        geometry_digest = digest({'layout': candidate['layout'], 'process': candidate['process']})
        if geometry_digest == original_geometry or geometry_digest in seen:
            raise ValueError('Geometry candidate must change the saved layout uniquely')
        seen.add(geometry_digest)
        project_digest = digest(candidate)
        coords = tuple(zip(keys, values))
        points.append(GeometryPoint(index, source_revision, original_digest, candidate,
                                    project_digest, geometry_digest, coords,
                                    digest({'source_revision': source_revision,
                                            'source_project_digest': original_digest,
                                            'project_digest': project_digest,
                                            'coordinates': coords})))
    return tuple(points)
