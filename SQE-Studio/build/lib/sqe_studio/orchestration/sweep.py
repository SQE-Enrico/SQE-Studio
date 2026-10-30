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
