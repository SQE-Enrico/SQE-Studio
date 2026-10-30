"""Deterministic re-encoding only. No S<->Y<->Z physics, mesh or quantum inference."""
from __future__ import annotations

from .models import NetworkNormalization, NetworkObservation, NetworkSample, SolverPort
from .preflight import UnsafeMapping
from .quantities import Dimension, Quantity


def frequency_as(value: Quantity, unit: str = 'Hz') -> Quantity:
    return value.require(Dimension.FREQUENCY).as_unit(unit)


def capacitance_as(value: Quantity, unit: str = 'F') -> Quantity:
    return value.require(Dimension.CAPACITANCE).as_unit(unit)


def convert_network_frequency_units(observation: NetworkObservation, unit: str) -> NetworkObservation:
    """Re-encode frequencies only; preserve native complex matrix measurements."""
    if not isinstance(observation, NetworkObservation):
        raise UnsafeMapping('A typed source network observation is required')
    return NetworkObservation(
        observation.normalization,
        tuple(NetworkSample(s.frequency.as_unit(unit), s.values) for s in observation.samples),
        observation.source,
    )


def reorder_network_ports(observation: NetworkObservation, old_ports_in_new_order: tuple[int, ...]) -> NetworkObservation:
    """Explicit matrix permutation with new contiguous one-based indices.

    Ports are never guessed from geometrical order. Signals/returns and matrix
    row *and* column order are permuted together. No reference renormalization.
    """
    if not isinstance(observation, NetworkObservation):
        raise UnsafeMapping('A typed source network observation is required')
    n = len(observation.normalization.ports)
    if (not isinstance(old_ports_in_new_order, tuple) or len(old_ports_in_new_order) != n or
            set(old_ports_in_new_order) != set(range(1, n + 1)) or any(type(p) is not int for p in old_ports_in_new_order)):
        raise UnsafeMapping('Explicit complete port permutation of 1..N is required')
    old = {p.index: i for i, p in enumerate(observation.normalization.ports)}
    indices = tuple(old[p] for p in old_ports_in_new_order)
    oldnorm = observation.normalization
    newports = tuple(SolverPort(i + 1, oldnorm.ports[j].signal_boundary,
                                oldnorm.ports[j].return_boundary,
                                oldnorm.ports[j].circuit_port, oldnorm.ports[j].reference_impedance)
                     for i, j in enumerate(indices))
    newnorm = NetworkNormalization(oldnorm.kind, newports,
                                   tuple(oldnorm.reference_planes[j] for j in indices), oldnorm.convention)
    samples = tuple(NetworkSample(s.frequency, tuple(tuple(s.values[i][j] for j in indices) for i in indices))
                    for s in observation.samples)
    return NetworkObservation(newnorm, samples, observation.source)
