"""Registered derivations: numbers are recomputed, never asserted (amendment A8).

A ``derived`` claim names a ``method`` at a ``method_version`` and the ordered claims it reads.
The validator recomputes the value from those claims' :class:`NumericFact` values and accepts
the claim only when the recomputation reproduces it at the claim's stated precision.

Everything here is pure ``Decimal`` arithmetic: no I/O, no clock, no floats (M1 constitution
articles 4 and 6). A published method version is immutable; a change is a new version.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, DivisionByZero, InvalidOperation
from types import MappingProxyType

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import Derivation, NumericFact

RATIO_UNIT = "ratio"

# One fixed arithmetic context, so a caller's decimal settings can never change a result.
_CONTEXT = Context(prec=34, rounding=ROUND_HALF_EVEN, traps=[DivisionByZero, InvalidOperation])
_TWO = Decimal(2)


class DerivationError(EpisAlphaError):
    """A derivation that cannot be recomputed under its method's rules."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INVALID_OUTPUT, message)


@dataclass(frozen=True)
class Method:
    """One registered computation. ``compute`` receives the input facts in declared order."""

    name: str
    version: str
    arity: int
    output_unit_rule: str
    """``"input"`` (the inputs' common unit) or ``"ratio"``."""
    same_period: bool
    same_basis: bool
    compute: Callable[[tuple[Decimal, ...]], Decimal]


# --- compatibility -------------------------------------------------------------------------


def _same_unit(facts: Sequence[NumericFact]) -> None:
    units = sorted({item.unit for item in facts})
    if len(units) > 1:
        raise DerivationError(f"input units differ {units}; nothing is converted")


def _same_basis(facts: Sequence[NumericFact]) -> None:
    bases = sorted({item.accounting_basis for item in facts})
    if len(bases) > 1:
        raise DerivationError(f"input accounting bases differ {bases}")


def _same_period(facts: Sequence[NumericFact]) -> None:
    periods = {(item.period_start, item.period_end) for item in facts}
    if len(periods) > 1:
        shown = sorted(f"{start.date()}..{end.date()}" for start, end in periods)
        raise DerivationError(f"input periods differ {shown}")


# --- the computations ----------------------------------------------------------------------


def _divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator.is_zero():
        raise DerivationError("division by zero: the divisor input is 0")
    return _CONTEXT.divide(numerator, denominator)


def _ordered(low: Decimal, high: Decimal) -> None:
    if low > high:
        raise DerivationError(f"range low {low} exceeds high {high}")


def _difference(values: tuple[Decimal, ...]) -> Decimal:
    first, second = values
    return _CONTEXT.subtract(second, first)


def _pct_change(values: tuple[Decimal, ...]) -> Decimal:
    old, new = values
    return _divide(_CONTEXT.subtract(new, old), old)


def _ratio(values: tuple[Decimal, ...]) -> Decimal:
    numerator, denominator = values
    return _divide(numerator, denominator)


def _midpoint(low: Decimal, high: Decimal) -> Decimal:
    _ordered(low, high)
    return _CONTEXT.divide(_CONTEXT.add(low, high), _TWO)


def _range_midpoint(values: tuple[Decimal, ...]) -> Decimal:
    low, high = values
    return _midpoint(low, high)


def _guidance_revision(values: tuple[Decimal, ...]) -> Decimal:
    prior_low, prior_high, new_low, new_high = values
    return _CONTEXT.subtract(_midpoint(new_low, new_high), _midpoint(prior_low, prior_high))


def _registry(*methods: Method) -> Mapping[tuple[str, str], Method]:
    return MappingProxyType({(method.name, method.version): method for method in methods})


REGISTRY: Mapping[tuple[str, str], Method] = _registry(
    Method("difference", "1", 2, "input", False, True, _difference),
    Method("pct_change", "1", 2, RATIO_UNIT, False, True, _pct_change),
    Method("ratio", "1", 2, RATIO_UNIT, True, False, _ratio),
    Method("margin", "1", 2, RATIO_UNIT, True, True, _ratio),
    Method("range_midpoint", "1", 2, "input", True, False, _range_midpoint),
    Method("guidance_revision", "1", 4, "input", True, False, _guidance_revision),
)


# --- public API ----------------------------------------------------------------------------


def lookup(derivation: Derivation) -> Method:
    method = REGISTRY.get((derivation.method, derivation.method_version))
    if method is not None:
        return method
    if any(name == derivation.method for name, _ in REGISTRY):
        raise DerivationError(
            f"unknown version {derivation.method_version!r} of method {derivation.method!r}"
        )
    raise DerivationError(
        f"unknown method {derivation.method!r}; registered: {sorted({n for n, _ in REGISTRY})}"
    )


def recompute(derivation: Derivation, inputs: Sequence[NumericFact]) -> tuple[Decimal, str]:
    """The value and unit the named method produces from ``inputs``, in declared order."""
    method = lookup(derivation)
    if len(inputs) != method.arity:
        raise DerivationError(
            f"method {method.name}@{method.version} takes {method.arity} inputs, got {len(inputs)}"
        )
    _same_unit(inputs)
    if method.same_basis:
        _same_basis(inputs)
    if method.same_period:
        _same_period(inputs)
    try:
        value = method.compute(tuple(item.value for item in inputs))
    except (DivisionByZero, InvalidOperation) as error:
        raise DerivationError(f"arithmetic error in {method.name}: {error!r}") from None
    unit = inputs[0].unit if method.output_unit_rule == "input" else RATIO_UNIT
    return value, unit


def matches(claimed: Decimal, computed: Decimal) -> bool:
    """Does ``computed``, rounded half-even to the claim's stated digits, equal ``claimed``?"""
    # ponytail: precision follows the claim's stated digits; add a minimum-precision rule if
    # coarse claims ("0.05" for 0.0523) become a problem.
    exponent = claimed.as_tuple().exponent
    if not isinstance(exponent, int):
        return False
    try:
        rounded = computed.quantize(Decimal(1).scaleb(exponent, _CONTEXT), context=_CONTEXT)
    except InvalidOperation:
        return False
    return rounded == claimed
