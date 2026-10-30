"""Exact, explicitly dimensioned quantities for interoperability metadata.

Conversions are SI prefix rescalings, never physics derivations. A frequency
and an E/h Hamiltonian energy parameter are deliberately different dimensions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum


class Dimension(str, Enum):
    FREQUENCY = 'frequency'
    ENERGY_OVER_H = 'energy_over_h'
    CAPACITANCE = 'capacitance'
    INDUCTANCE = 'inductance'
    LENGTH = 'length'
    RESISTANCE = 'resistance'
    CONDUCTANCE = 'conductance'
    DIMENSIONLESS = 'dimensionless'


# All factors are exact decimals. No angle-frequency or E -> E/h conversion.
_UNIT_FACTORS: dict[Dimension, dict[str, Decimal]] = {
    Dimension.FREQUENCY: {'Hz': Decimal('1'), 'kHz': Decimal('1e3'), 'MHz': Decimal('1e6'), 'GHz': Decimal('1e9')},
    Dimension.ENERGY_OVER_H: {'Hz': Decimal('1'), 'MHz': Decimal('1e6'), 'GHz': Decimal('1e9')},
    Dimension.CAPACITANCE: {'F': Decimal('1'), 'pF': Decimal('1e-12'), 'fF': Decimal('1e-15')},
    Dimension.INDUCTANCE: {'H': Decimal('1'), 'nH': Decimal('1e-9')},
    Dimension.LENGTH: {'m': Decimal('1'), 'mm': Decimal('1e-3'), 'um': Decimal('1e-6'), 'nm': Decimal('1e-9')},
    Dimension.RESISTANCE: {'ohm': Decimal('1'), 'kohm': Decimal('1e3')},
    Dimension.CONDUCTANCE: {'S': Decimal('1'), 'mS': Decimal('1e-3')},
    Dimension.DIMENSIONLESS: {'1': Decimal('1')},
}
_BASE_UNITS = {d: next(iter(units)) for d, units in _UNIT_FACTORS.items()}


class InteropValidationError(ValueError):
    """A typed scientific metadata object violates its declared contract."""


def decimal_number(number: Decimal | int | float | str) -> Decimal:
    if isinstance(number, bool) or not isinstance(number, (Decimal, int, float, str)):
        raise InteropValidationError('Quantity requires a finite decimal-compatible number (not bool)')
    try:
        value = Decimal(str(number))
    except (InvalidOperation, ValueError):
        raise InteropValidationError('Quantity is not numeric') from None
    if not value.is_finite() or (value and abs(value.adjusted()) > 60):
        raise InteropValidationError('Quantity must be finite and within a bounded decimal exponent')
    return value


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal | int | float | str
    unit: str
    dimension: Dimension
    schema_version: str = 'sqe.quantity.v1'

    def __post_init__(self) -> None:
        if self.schema_version != 'sqe.quantity.v1':
            raise InteropValidationError('Unsupported quantity schema version')
        if not isinstance(self.dimension, Dimension) or not isinstance(self.unit, str):
            raise InteropValidationError('Quantity requires an explicit supported dimension and unit')
        if self.unit not in _UNIT_FACTORS[self.dimension]:
            raise InteropValidationError(f'Unit {self.unit!r} invalid for {self.dimension.value}')
        object.__setattr__(self, 'value', decimal_number(self.value))

    def as_unit(self, target_unit: str) -> 'Quantity':
        factors = _UNIT_FACTORS[self.dimension]
        if target_unit not in factors:
            raise InteropValidationError(f'Cannot convert {self.dimension.value} to {target_unit!r}')
        return Quantity(self.value * factors[self.unit] / factors[target_unit], target_unit, self.dimension)

    def si(self) -> 'Quantity':
        return self.as_unit(_BASE_UNITS[self.dimension])

    def require(self, dimension: Dimension, *, strictly_positive: bool = False, nonnegative: bool = False) -> 'Quantity':
        if self.dimension != dimension:
            raise InteropValidationError(f'Expected {dimension.value}, got {self.dimension.value}')
        if strictly_positive and self.value <= 0:
            raise InteropValidationError(f'{dimension.value} must be positive')
        if nonnegative and self.value < 0:
            raise InteropValidationError(f'{dimension.value} must be nonnegative')
        return self

    def portable(self) -> dict[str, str]:
        """Deterministic JSON-friendly representation retaining decimal precision."""
        return {'schema_version': self.schema_version, 'value': str(self.value),
                'unit': self.unit, 'dimension': self.dimension.value}


@dataclass(frozen=True, slots=True)
class ComplexQuantity:
    real: Quantity
    imag: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.real, Quantity) or not isinstance(self.imag, Quantity):
            raise InteropValidationError('Complex value needs explicit real and imaginary quantities')
        if (self.real.dimension, self.real.unit) != (self.imag.dimension, self.imag.unit):
            raise InteropValidationError('Complex real and imaginary units/dimensions must agree')

    def as_unit(self, unit: str) -> 'ComplexQuantity':
        return ComplexQuantity(self.real.as_unit(unit), self.imag.as_unit(unit))
